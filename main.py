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

    yield

    await app.state.reclaimv2.disconnect()

app = FastAPI(lifespan=lifespan)

# def log_state_attr(attr: str,  state: ReclaimState) -> None:
#     _LOGGER.warning(f'{attr}, {state.__getattr__(attr)}')
#
# def log_all(state: ReclaimState):
#     log_state_attr('pump', state)
#     log_state_attr('case', state)
#     log_state_attr('water', state)
#     log_state_attr('inlet', state)
#     log_state_attr('outlet', state)
#     log_state_attr('ambient', state)
#     log_state_attr('suction', state)
#     log_state_attr('evaporator', state)
#     log_state_attr('discharge', state)
#     log_state_attr('waterspeed', state)
#     log_state_attr('power', state)
#     log_state_attr('boost', state)

@app.get('/state')
async def state(request: Request) -> ReclaimStateResponse:
    return await _get_latest_state()

async def _validate_boost_on(state: Optional[ReclaimStateResponse]) -> Optional[ReclaimBoostResponse]:
    if state is None:
        return ReclaimBoostResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    initial_status=BoostStatus.UNKNOWN,
                                    final_status=BoostStatus.UNKNOWN,
                                    detail='Failed to get current state; will not turn on boost.')

    if state.boost:
        return ReclaimBoostResponse(status_code=status.HTTP_409_CONFLICT,
                                    initial_status=BoostStatus.ON,
                                    final_status=BoostStatus.ON,
                                    detail='Boost was already on; will not turn on boost.')
    elif state.pump or state.water > 55:
        return ReclaimBoostResponse(status_code=status.HTTP_409_CONFLICT,
                                    initial_status=BoostStatus.OFF,
                                    final_status=BoostStatus.OFF,
                                    detail='Heater is already running (non-boost); will not turn on boost.'
                                        if state.pump else 'Water temperature was over 55C; will not turn on boost.')
    return None

async def _perform_boost_on() -> ReclaimBoostResponse:
    await app.state.reclaimv2.set_value("boost", True)
    state = await _get_latest_state()
    if state is None or not state.boost:
        return ReclaimBoostResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    initial_status=BoostStatus.OFF,
                                    final_status=BoostStatus.UNKNOWN if state is None else BoostStatus.OFF,
                                    detail='Failed to get updated state; boost status uncertain.'
                                        if state is None else 'Failed to turn on boost.')
    return ReclaimBoostResponse(status_code=status.HTTP_200_OK,
                                initial_status=BoostStatus.OFF,
                                final_status=BoostStatus.ON,
                                detail='Turned on boost.')

async def _perform_boost_off() -> ReclaimBoostResponse:
    await app.state.reclaimv2.set_value("boost", False)
    state = await _get_latest_state()
    if state is None or state.boost:
        return ReclaimBoostResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    initial_status=BoostStatus.ON,
                                    final_status=BoostStatus.UNKNOWN if state is None else BoostStatus.ON,
                                    detail='Failed to get updated state; boost status uncertain.'
                                    if state is None else 'Failed to turn off boost.')
    return ReclaimBoostResponse(status_code=status.HTTP_200_OK,
                                initial_status=BoostStatus.ON,
                                final_status=BoostStatus.OFF,
                                detail='Turned off boost.')

@app.post('/boost/on')
async def boost_on(request: Request, response: Response) -> str:
    state: Optional[ReclaimStateResponse] = await _get_latest_state()
    
    error_response = await _validate_boost_on(state)
    if error_response:
        return error_response

    return await _perform_boost_on(request)

async def _validate_boost_off(state: Optional[ReclaimStateResponse]) -> Optional[ReclaimBoostResponse]:
    if state is None:
        return ReclaimBoostResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    initial_status=BoostStatus.UNKNOWN,
                                    final_status=BoostStatus.UNKNOWN,
                                    detail='Failed to get current state; will not turn off boost.')

    if not state.boost:
        return ReclaimBoostResponse(status_code=status.HTTP_409_CONFLICT,
                                    initial_status=BoostStatus.OFF,
                                    final_status=BoostStatus.OFF,
                                    detail='Boost was already off; will not turn off boost.')
    return None

@app.post('/boost/off')
async def boost_off(request: Request) -> str:
    state: Optional[ReclaimStateResponse] = await _get_latest_state()

    error_response = await _validate_boost_off(state)
    if error_response:
        return error_response

    return await _perform_boost_off(request)

async def _get_latest_state() -> Optional[ReclaimStateResponse]:
    if (await app.state.reclaimv2.request_update()):
        return ReclaimStateResponse.from_state(app.state.listener.state)

if __name__ == "__main__":
    if sys.platform.lower() == "win32" or os.name.lower() == "nt":
        from asyncio import set_event_loop_policy, WindowsSelectorEventLoopPolicy
        set_event_loop_policy(WindowsSelectorEventLoopPolicy())

    # app.openapi()
    # http://localhost:8003/openapi.json
    # uvicorn main:app --host=0.0.0.0 --port=8003 --reload
    uvicorn.run(app, host="0.0.0.0", port=8003)

