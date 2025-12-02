import os
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class Config:
    """Minimalist configuration for Cleanify v2.0"""
    
    # Server settings
    HOST: str = os.getenv('HOST', '0.0.0.0')
    PORT: int = int(os.getenv('PORT', 5001))
    DEBUG: bool = False
    
    # External routing services
    OSRM_URL: str = os.getenv('OSRM_URL', 'http://localhost:5000')
    VROOM_URL: str = os.getenv('VROOM_URL', 'http://localhost:3000')
    
    # File storage
    SAVES_DIR: str = os.getenv('SAVES_DIR', 'saved_systems')
    
    # Simulation settings
    SIMULATION_START_HOUR: int = 7
    DEFAULT_BIN_CAPACITY: int = 500
    DEFAULT_TRUCK_CAPACITY: int = 1000
    DEFAULT_FILL_RATE: float = 3.5
    
    # Traffic Configuration
    TRAFFIC_HEAVY_HOURS: Optional[List[int]] = None
    TRAFFIC_MULTIPLIER: float = float(os.getenv('TRAFFIC_MULTIPLIER', '1.5'))
    TRAFFIC_BUFFER_HOURS: float = float(os.getenv('TRAFFIC_BUFFER_HOURS', '1.0'))
    
    # VROOM optimization settings
    VROOM_TIMEOUT: int = int(os.getenv('VROOM_TIMEOUT', '10'))
    
    def __post_init__(self):
        """Parse traffic hours from environment variable"""
        if self.TRAFFIC_HEAVY_HOURS is None:
            heavy_hours_str = os.getenv('TRAFFIC_HEAVY_HOURS', '8,9,17,18')
            self.TRAFFIC_HEAVY_HOURS = [int(h.strip()) for h in heavy_hours_str.split(',') if h.strip()]