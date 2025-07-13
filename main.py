import boto3
import botocore
import os, sys
import logging
import asyncio
import uvicorn
from fastapi import FastAPI, Request, Response
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
from model import ReclaimStateProcessed

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
async def request_update_and_log_state(request: Request) -> ReclaimStateProcessed:
    return await _get_latest_state()

@app.post('/boost/on')
async def boost_on(request: Request) -> str:
    # Check if boost is already on.
    state: Optional[ReclaimStateProcessed] = await _get_latest_state()
    if state is None:
        return 'Failed to get current state; will not turn on boost'
    elif state.boost:
        return "Boost was already on; will not turn on boost"
    elif state.pump:
        return "Heater is already running (non-boost); will not turn on boost"
    else:
        await request.app.state.reclaimv2.set_value("boost", True)
        state = await _get_latest_state()
        if state is None:
            return 'Failed to get updated state; boost status uncertain'
        return 'TURN ON BOOST: SUCCESS' if state.boost else 'TURN ON BOOST: FAILURE'

@app.post('/boost/off')
async def boost_off(request: Request) -> str:
    state: Optional[ReclaimStateProcessed] = await _get_latest_state()
    if state is None:
        return 'Failed to get current state; will not turn off boost'
    elif not state.boost:
        return "Boost was already off; will not turn off boost"
    else:
        await request.app.state.reclaimv2.set_value("boost", False)
        state = await _get_latest_state()
        if state is None:
            return 'Failed to get updated state; boost status uncertain'
        return 'TURN OFF BOOST: SUCCESS' if not state.boost else 'TURN OFF BOOST: FAILURE'

async def _get_latest_state() -> Optional[ReclaimStateProcessed]:
    if (await app.state.reclaimv2.request_update()):
        return ReclaimStateProcessed.from_unprocessed_state(app.state.listener.state)

if __name__ == "__main__":
    if sys.platform.lower() == "win32" or os.name.lower() == "nt":
        from asyncio import set_event_loop_policy, WindowsSelectorEventLoopPolicy
        set_event_loop_policy(WindowsSelectorEventLoopPolicy())

    # app.openapi()
    # http://localhost:8003/openapi.json
    # uvicorn main:app --host=0.0.0.0 --port=8003 --reload
    uvicorn.run(app, host="0.0.0.0", port=8003)

