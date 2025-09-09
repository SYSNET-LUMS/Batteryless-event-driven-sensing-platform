# src/models/route.py
from dataclasses import dataclass
from typing import List

@dataclass
class Waypoint:
    """Represents a waypoint along a route"""
    lat: float
    lng: float
    distance_from_start: float

@dataclass
class RouteInfo:
    """Contains route information"""
    bin_id: str
    distance: float  # meters
    duration: float  # seconds
    waypoints: List[Waypoint]

@dataclass
class RoutingDecision:
    """Routing decision for a truck"""
    truck_id: str
    route: List[str]  # List of bin IDs
    dispatch: str  # 'now' or 'wait'
    delay_min: int = 0
    reason: str = ''