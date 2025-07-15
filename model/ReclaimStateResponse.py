from pydantic import BaseModel
from typing import Optional
from custom_components.reclaimenergy.reclaimv2 import ReclaimState

class ReclaimStateResponse(BaseModel):
    mode: str
    pump: bool
    case: float
    water: float
    outlet: float
    inlet: float
    discharge: float
    suction: float
    evaporator: float
    ambient: float
    compspeed: int
    waterspeed: int
    fanspeed: int
    power: int
    current: float
    hours: float
    starts: float
    boost: bool

    @staticmethod
    def from_state(state: ReclaimState) -> Optional['ReclaimStateResponse']:
        return ReclaimStateResponse(
            mode=state.mode,
            pump=state.pump==1,
            case=state.case,
            water=state.water,
            outlet=state.outlet,
            inlet=state.inlet,
            discharge=state.discharge,
            suction=state.suction,
            evaporator=state.evaporator,
            ambient=state.ambient,
            compspeed=state.compspeed,
            waterspeed=state.waterspeed,
            fanspeed=state.fanspeed,
            power=state.power,
            current=state.current,
            hours=state.hours,
            starts=state.starts,
            boost=state.boost)