import boto3
import botocore
import os, sys
import logging
import asyncio
import uvicorn
import asyncpg

# Set environment variables for local PostgreSQL connection
os.environ["DB_USER"] = "user"
os.environ["DB_PASSWORD"] = "password"
os.environ["DB_HOST"] = "localhost"
os.environ["DB_PORT"] = "5433"
os.environ["DB_NAME"] = "reclaim_energy"
from fastapi import FastAPI, Request, Response, status
from contextlib import asynccontextmanager
from typing import Optional

from custom_components.reclaimenergy.const import (AWS_IOT_ROOT_CERT,
                                                   AWS_REGION_NAME,
                                                   AWS_IDENTITY_POOL,
                                                   AWS_HOSTNAME,
                                                   AWS_PORT,
                                                   CACERT_FILENAME,
                                                   CERT_FILENAME,
                                                   KEY_FILENAME,
                                                   UNIQUE_ID_FILENAME,)
from custom_components.reclaimenergy.reclaimv2 import ReclaimV2, ReclaimState
from custom_components.reclaimenergy.config_flow import obtain_and_save_aws_keys
from model import ReclaimStateResponse, ReclaimBoostResponse, BoostStatus

BASEPATH = os.getcwd()

CACERT_PATH = os.path.join(BASEPATH, CACERT_FILENAME)
CERT_PATH = os.path.join(BASEPATH, CERT_FILENAME)
KEY_PATH = os.path.join(BASEPATH, KEY_FILENAME)
UNIQUE_ID_PATH = os.path.join(BASEPATH, UNIQUE_ID_FILENAME)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
_LOGGER = logging.getLogger(__name__)


class MessageListener:
    """Message Listener."""
    state: ReclaimState = ReclaimState({})

    def on_message(self, state: ReclaimState) -> None:
        """Process device state updates."""
        self.state = state

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Connect to the Reclaim HWS
    obtain_and_save_aws_keys(CACERT_PATH, CERT_PATH, KEY_PATH)
    with open(UNIQUE_ID_PATH, 'r') as f:
        unique_id = int(f.readline().strip())
    app.state.reclaimv2 = ReclaimV2(
        unique_id,
        CACERT_PATH,
        CERT_PATH,
        KEY_PATH,
    )
    app.state.listener = MessageListener()
    await app.state.reclaimv2.connect(app.state.listener)

    _LOGGER.info("Connecting to database...")
    db_user = os.environ.get("DB_USER")
    db_password = os.environ.get("DB_PASSWORD")
    db_host = os.environ.get("DB_HOST")
    db_port = os.environ.get("DB_PORT")
    db_name = os.environ.get("DB_NAME")

    _LOGGER.info(f"Attempting to connect with: User={db_user}, Host={db_host}, Port={db_port}, DB={db_name}")
    # WARNING: Do NOT log the password in a production environment!
    _LOGGER.info(f"Password length: {len(db_password) if db_password else 0}")

    try:
        app.state.pool = await asyncpg.create_pool(
            user=db_user,
            password=db_password,
            host=db_host,
            port=int(db_port),
            database=db_name,
        )
        _LOGGER.info("Database connected.")

        # Create table if it doesn't exist
        async with app.state.pool.acquire() as connection:
            await connection.execute("""
                CREATE TABLE IF NOT EXISTS reclaim_state_history (
                    id SERIAL PRIMARY KEY,
                    timestamp_ms BIGINT DEFAULT (EXTRACT(EPOCH FROM NOW()) * 1000),
                    mode TEXT,
                    pump BOOLEAN,
                    "case" REAL,
                    water REAL,
                    outlet REAL,
                    inlet REAL,
                    discharge REAL,
                    suction REAL,
                    evaporator REAL,
                    ambient REAL,
                    compspeed INTEGER,
                    waterspeed INTEGER,
                    fanspeed INTEGER,
                    power INTEGER,
                    current REAL,
                    hours REAL,
                    starts REAL,
                    boost BOOLEAN
                )
            """)
        _LOGGER.info("Table 'reclaim_state_history' ensured to exist.")
    except Exception as e:
        _LOGGER.error(f"Failed to connect to database or create table: {e}")
        app.state.pool = None

    yield

    # Disconnect from the Reclaim HWS
    await app.state.reclaimv2.disconnect()

    _LOGGER.info("Disconnecting from database...")
    if app.state.pool:
        await app.state.pool.close()
        app.state.pool = None
    _LOGGER.info("Database disconnected.")

app = FastAPI(lifespan=lifespan)

@app.get('/state')
async def state(request: Request) -> ReclaimStateResponse:
    return await _get_latest_state()

@app.post('/boost/on')
async def boost_on(request: Request, response: Response) -> ReclaimBoostResponse:
    error_response = await _validate_boost_toggle(BoostStatus.OFF)
    if error_response:
        response.status_code = error_response.status_code
        return error_response

    toggle_response = await _perform_boost_toggle(BoostStatus.OFF)
    response.status_code = toggle_response.status_code
    return toggle_response

@app.post('/boost/off')
async def boost_off(request: Request, response: Response) -> ReclaimBoostResponse:
    error_response = await _validate_boost_toggle(BoostStatus.ON)
    if error_response:
        response.status_code = error_response.status_code
        return error_response

    toggle_response = await _perform_boost_toggle(BoostStatus.ON)
    response.status_code = toggle_response.status_code
    return toggle_response

@app.get('/tables')
async def get_tables(request: Request):
    if not app.state.pool:
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content="Database not connected")

    async with app.state.pool.acquire() as connection:
        tables = await connection.fetch("""
            SELECT tablename
            FROM pg_catalog.pg_tables
            WHERE schemaname != 'pg_catalog' AND schemaname != 'information_schema'
        """)
        
        response = {}
        for table in tables:
            table_name = table['tablename']
            columns = await connection.fetch(f"""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = '{table_name}'
            """)
            response[table_name] = {col['column_name']: col['data_type'] for col in columns}
            
        return response

@app.get('/history/{start_timestamp_ms}/{end_timestamp_ms}')
async def get_history(request: Request, start_timestamp_ms: int, end_timestamp_ms: int, sample_rate: Optional[int] = None):
    if not app.state.pool:
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content="Database not connected")

    query = """
        SELECT * FROM reclaim_state_history
        WHERE timestamp_ms >= $1 AND timestamp_ms <= $2
    """
    params = [start_timestamp_ms, end_timestamp_ms]

    if sample_rate and sample_rate > 0:
        query += f" AND id % {sample_rate} = 0"

    query += " ORDER BY timestamp_ms"

    async with app.state.pool.acquire() as connection:
        records = await connection.fetch(query, *params)
        if not records:
            return {}
        
        result = {key: [] for key in records[0].keys()}
        for record in records:
            for key, value in record.items():
                result[key].append(value)
        return result

@app.post('/test_data/add')
async def add_test_data(request: Request):
    if not app.state.pool:
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content="Database not connected")

    async with app.state.pool.acquire() as connection:
        # Insert a sample row of data
        await connection.execute("""
            INSERT INTO reclaim_state_history (mode, pump, "case", water, outlet, inlet, discharge, suction, evaporator, ambient, compspeed, waterspeed, fanspeed, power, current, hours, starts, boost)
            VALUES ('heating', true, 45.1, 50.2, 55.3, 40.1, 60.5, 35.2, 5.1, 25.6, 3000, 100, 500, 1500, 6.5, 1234.5, 123, false)
        """)
        return Response(status_code=status.HTTP_201_CREATED, content="Test data added.")

@app.delete('/test_data/delete/{start_id}/{end_id}')
async def delete_test_data(request: Request, start_id: int, end_id: int):
    if not app.state.pool:
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content="Database not connected")

    async with app.state.pool.acquire() as connection:
        result = await connection.execute("DELETE FROM reclaim_state_history WHERE id >= $1 AND id <= $2", start_id, end_id)
        
        # The result format is 'DELETE count'. We parse the count.
        try:
            count = int(result.split(' ')[1])
        except (IndexError, ValueError):
            count = 0

        if count > 0:
            return Response(status_code=status.HTTP_200_OK, content=f"{count} records between id {start_id} and {end_id} deleted.")
        else:
            return Response(status_code=status.HTTP_404_NOT_FOUND, content=f"No records found between id {start_id} and {end_id}.")

async def _get_latest_state() -> Optional[ReclaimStateResponse]:
    if (await app.state.reclaimv2.request_update()):
        return ReclaimStateResponse.from_state(app.state.listener.state)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

async def _validate_boost_toggle(expected_initial_status: BoostStatus) -> Optional[ReclaimBoostResponse]:
    if expected_initial_status == BoostStatus.UNKNOWN:
        raise ValueError(f'Expected initial status is {expected_initial_status}')
    desired_final_status = BoostStatus.OFF if expected_initial_status == BoostStatus.ON else BoostStatus.ON

    state = await _get_latest_state()
    if state is None or isinstance(state, Response):
        return ReclaimBoostResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    initial_status=BoostStatus.UNKNOWN,
                                    final_status=BoostStatus.UNKNOWN,
                                    detail=f'Failed to get current state; will not turn boost {desired_final_status}.')

    initial_status = BoostStatus.ON if state.boost else BoostStatus.OFF

    if initial_status == desired_final_status:
        return ReclaimBoostResponse(status_code=status.HTTP_409_CONFLICT,
                                    initial_status=initial_status,
                                    final_status=initial_status,
                                    detail=f'Boost was already {desired_final_status}; will not turn boost {desired_final_status}.')
    elif desired_final_status == BoostStatus.ON:
        if state.pump or state.water > 55:
            return ReclaimBoostResponse(status_code=status.HTTP_409_CONFLICT,
                                        initial_status=BoostStatus.OFF,
                                        final_status=BoostStatus.OFF,
                                        detail='Heater is already running (non-boost); will not turn on boost.'
                                            if state.pump else 'Water temperature is over 55C; will not turn on boost.')
    return None

async def _perform_boost_toggle(initial_status: BoostStatus) -> ReclaimBoostResponse:
    if initial_status == BoostStatus.UNKNOWN:
        raise Exception('Cannot toggle boost because current state is unknown.')
    desired_final_status = BoostStatus.OFF if initial_status == BoostStatus.ON else BoostStatus.ON
    await app.state.reclaimv2.set_value("boost", desired_final_status == BoostStatus.ON)
    state = await _get_latest_state()

    if state is None or isinstance(state, Response):
        return ReclaimBoostResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    initial_status=initial_status,
                                    final_status=BoostStatus.UNKNOWN,
                                    detail='Failed to get updated state; boost status uncertain.')

    if state.boost is not (desired_final_status == BoostStatus.ON):
        return ReclaimBoostResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    initial_status=initial_status,
                                    final_status=initial_status,
                                    detail=f'Failed to turn {desired_final_status.value} boost.')

    return ReclaimBoostResponse(status_code=status.HTTP_200_OK,
                                initial_status=initial_status,
                                final_status=desired_final_status,
                                detail=f'Turned {desired_final_status.value} boost.')


if __name__ == "__main__":
    if sys.platform.lower() == "win32" or os.name.lower() == "nt":
        from asyncio import set_event_loop_policy, WindowsSelectorEventLoopPolicy
        set_event_loop_policy(WindowsSelectorEventLoopPolicy())

    # app.openapi()
    # http://localhost:8003/openapi.json
    # uvicorn main:app --host=0.0.0.0 --port=8003 --reload
    uvicorn.run(app, host="0.0.0.0", port=8003)

