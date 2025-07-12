import boto3
import botocore
import os, sys
import logging
import asyncio

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


BASEPATH = os.getcwd()

CACERT_PATH = os.path.join(BASEPATH, CACERT_FILENAME)
CERT_PATH = os.path.join(BASEPATH, CERT_FILENAME)
KEY_PATH = os.path.join(BASEPATH, KEY_FILENAME)
UNIQUE_ID_PATH = os.path.join(BASEPATH, UNIQUE_ID_FILENAME)

_LOGGER = logging.getLogger(__name__)

class MessageListener:
    """Message Listener."""
    state: ReclaimState = ReclaimState({})

    def on_message(self, state: ReclaimState) -> None:
        """Process device state updates."""
        self.state = state

def log_state_attr(attr: str,  state: ReclaimState) -> None:
    _LOGGER.warning(f'{attr}, {state.__getattr__(attr)}')

def log_all(state: ReclaimState):
    log_state_attr('pump', state)
    log_state_attr('case', state)
    log_state_attr('water', state)
    log_state_attr('inlet', state)
    log_state_attr('outlet', state)
    log_state_attr('ambient', state)
    log_state_attr('suction', state)
    log_state_attr('evaporator', state)
    log_state_attr('discharge', state)
    log_state_attr('waterspeed', state)
    log_state_attr('power', state)
    log_state_attr('boost', state)

async def request_update_and_log_state(reclaimv2: ReclaimV2, state:ReclaimState) -> None:
    await reclaimv2.request_update()
    log_all(state)

async def main():

    with open(UNIQUE_ID_PATH, 'r') as f:
        unique_id = int(f.readline().strip())
    reclaimv2 = ReclaimV2(
        unique_id,
        CACERT_PATH,
        CERT_PATH,
        KEY_PATH,
    )
    listener = MessageListener()

    await reclaimv2.connect(listener)

    while True:
        await asyncio.sleep(5)
        await request_update_and_log_state(reclaimv2, listener.state)
        await asyncio.sleep(5)
        # _LOGGER.warning('TURNING BOOST ON!')
        # await reclaimv2.set_value("boost", True)
        await asyncio.sleep(5)
        await request_update_and_log_state(reclaimv2, listener.state)
        await asyncio.sleep(5)
        await request_update_and_log_state(reclaimv2, listener.state)
        await asyncio.sleep(5)
        await request_update_and_log_state(reclaimv2, listener.state)
        await asyncio.sleep(5)
        await request_update_and_log_state(reclaimv2, listener.state)
        # _LOGGER.warning('TURNING BOOST OFF!')
        # await reclaimv2.set_value("boost", False)
        await asyncio.sleep(5)
        await request_update_and_log_state(reclaimv2, listener.state)
        await asyncio.sleep(5)
        await request_update_and_log_state(reclaimv2, listener.state)
        await asyncio.sleep(5)
        await request_update_and_log_state(reclaimv2, listener.state)
        await asyncio.sleep(5)
        await request_update_and_log_state(reclaimv2, listener.state)

if __name__ == "__main__":
    if sys.platform.lower() == "win32" or os.name.lower() == "nt":
        from asyncio import set_event_loop_policy, WindowsSelectorEventLoopPolicy
        set_event_loop_policy(WindowsSelectorEventLoopPolicy())
    obtain_and_save_aws_keys(CACERT_PATH, CERT_PATH, KEY_PATH)
    asyncio.run(main())

