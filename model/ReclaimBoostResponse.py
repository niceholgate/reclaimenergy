from fastapi.responses import ORJSONResponse
from enum import Enum

class BoostStatus(str, Enum):
    ON = 'ON'
    OFF = 'OFF'
    UNKNOWN = 'UNKNOWN'

class ReclaimBoostResponse(ORJSONResponse):

    def __init__(self,
                 status_code: int,
                 initial_status: BoostStatus,
                 final_status: BoostStatus,
                 detail: str):
        content = {
            'initial_status': initial_status,
            'final_status': final_status,
            'detail': detail,
        }
        super().__init__(content=content, status_code=status_code)

