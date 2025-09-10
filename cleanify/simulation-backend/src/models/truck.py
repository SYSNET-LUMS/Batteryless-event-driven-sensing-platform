from dataclasses import dataclass
from typing import Optional, List
from .base import BaseModel

@dataclass
class Truck(BaseModel):
    """Represents a waste collection truck"""
    capacity: float = 1000.0
    current_load: float = 0.0
    status: str = 'idle'  # idle, traveling, collecting, returning_to_depot, waiting
    speed: float = 50.0   # km/h
    target_bin_id: Optional[str] = None
    target_depot_id: Optional[str] = None
    route: List = None
    route_index: int = 0
    waiting_until: Optional[float] = None
    wait_reason: Optional[str] = None
    pending_route: Optional[List[str]] = None
    has_assignment: bool = False
    
    def __post_init__(self):
        if self.route is None:
            self.route = []