"""
Minimalist Services
Traffic-aware dispatch with VROOM optimization
"""

from .traffic_service import TrafficService
from .routing_service import RoutingService
from .file_service import FileService
from .schedule_service import ScheduleService

# External services
from .external.osrm_service import OSRMService
from .external.vroom_service import VROOMService

# Simulation services
from .simulation.simulation_service import SimulationService

__all__ = [
    # Core services
    'TrafficService',
    'RoutingService',
    'FileService',
    'ScheduleService',
    
    # External services
    'OSRMService',
    'VROOMService',
    
    # Simulation services
    'SimulationService'
]