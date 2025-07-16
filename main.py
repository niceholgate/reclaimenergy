import boto3
import botocore
import os, sys
import logging
import asyncio
import uvicorn
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

    # TODO: Connect to the DB

    yield

    # Disconnect from the Reclaim HWS
    await app.state.reclaimv2.disconnect()

    # TODO: Disconnect from the DB

app = FastAPI(lifespan=lifespan)

@app.get('/state')
async def state(request: Request) -> ReclaimStateResponse:
    return await _get_latest_state()

@app.post('/boost/on')
async def boost_on(request: Request, response: Response) -> str:
    error_response = await _validate_boost_on(BoostStatus.OFF)
    if error_response:
        return error_response

    return await _perform_boost_toggle(BoostStatus.OFF)

@app.post('/boost/off')
async def boost_off(request: Request) -> str:
    error_response = await _validate_boost_toggle(BoostStatus.ON)
    if error_response:
        return error_response

    return await _perform_boost_toggle(BoostStatus.ON)

async def _get_latest_state() -> Optional[ReclaimStateResponse]:
    if (await app.state.reclaimv2.request_update()):
        return ReclaimStateResponse.from_state(app.state.listener.state)

async def _validate_boost_toggle(expected_initial_status: BoostStatus) -> Optional[ReclaimBoostResponse]:
    if expected_initial_status == BoostStatus.UNKNOWN:
        raise ValueError(f'Expected initial status is {expected_initial_status}')
    desired_final_status = BoostStatus.OFF if expected_initial_status == BoostStatus.ON else BoostStatus.ON

    state: Optional[ReclaimStateResponse] = await _get_latest_state()
    if state is None:
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
    await app.state.reclaimv2.set_value("boost", initial_status == BoostStatus.OFF)
    state = await _get_latest_state()

    if state is None:
        return ReclaimBoostResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    initial_status=initial_status,
                                    final_status=BoostStatus.UNKNOWN,
                                    detail='Failed to get updated state; boost status uncertain.')

    if state.boost is not boost_on:
        return ReclaimBoostResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    initial_status=initial_status,
                                    final_status=initial_status,
                                    detail=f'Failed to turn {desired_final_status} boost.')

    return ReclaimBoostResponse(status_code=status.HTTP_200_OK,
                                initial_status=initial_status,
                                final_status=desired_final_status,
                                detail=f'Turned {desired_final_status} boost.')


if __name__ == "__main__":
    if sys.platform.lower() == "win32" or os.name.lower() == "nt":
        from asyncio import set_event_loop_policy, WindowsSelectorEventLoopPolicy
        set_event_loop_policy(WindowsSelectorEventLoopPolicy())

    # app.openapi()
    # http://localhost:8003/openapi.json
    # uvicorn main:app --host=0.0.0.0 --port=8003 --reload
    uvicorn.run(app, host="0.0.0.0", port=8003)

