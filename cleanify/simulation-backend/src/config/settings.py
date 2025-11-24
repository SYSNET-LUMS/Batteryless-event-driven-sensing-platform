import os
from dataclasses import dataclass

@dataclass
class Config:
    # Urgency score weights (tunable)
    URGENCY_WEIGHT_FILL: float = float(os.getenv('URGENCY_WEIGHT_FILL', 0.5))
    URGENCY_WEIGHT_RATE: float = float(os.getenv('URGENCY_WEIGHT_RATE', 0.3))
    URGENCY_WEIGHT_TIME: float = float(os.getenv('URGENCY_WEIGHT_TIME', 0.2))
    """Application configuration with VROOM support"""
    # Server settings
    HOST: str = os.getenv('HOST', '0.0.0.0')
    PORT: int = int(os.getenv('PORT', 5001))
    DEBUG: bool = False
    
    # External routing services
    OSRM_URL: str = os.getenv('OSRM_URL', 'http://localhost:5000')
    VROOM_URL: str = os.getenv('VROOM_URL', 'http://localhost:3000')
    
    # File storage
    SAVES_DIR: str = os.getenv('SAVES_DIR', 'saved_systems')
    
    # Agent settings
    OPENAI_API_KEY: str = os.getenv('OPENAI_API_KEY', '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')
    
    # Simulation settings
    SIMULATION_START_HOUR: int = 7
    DEFAULT_BIN_CAPACITY: int = 500
    DEFAULT_TRUCK_CAPACITY: int = 1000
    DEFAULT_FILL_RATE: float = 3.5
    
    # VROOM optimization settings
    VROOM_TIMEOUT: int = int(os.getenv('VROOM_TIMEOUT', '10'))
    VROOM_FALLBACK_ENABLED: bool = os.getenv('VROOM_FALLBACK_ENABLED', 'True').lower() == 'true'
    
    # Distance-based dispatch settings
    USE_DISTANCE_DISPATCH: bool = os.getenv('USE_DISTANCE_DISPATCH', 'True').lower() == 'true'
    DISPATCH_NEARBY_RADIUS_M: int = int(os.getenv('DISPATCH_NEARBY_RADIUS_M', '1500'))
    DISPATCH_COOLDOWN_MIN: int = int(os.getenv('DISPATCH_COOLDOWN_MIN', '30'))
    DISPATCH_MAX_ROUTE_BINS: int = int(os.getenv('DISPATCH_MAX_ROUTE_BINS', '10'))
    DISPATCH_CAPACITY_BUFFER_PERCENT: float = float(os.getenv('DISPATCH_CAPACITY_BUFFER_PERCENT', '5'))
    DISPATCH_SPEED_KMH: float = float(os.getenv('DISPATCH_SPEED_KMH', '28'))