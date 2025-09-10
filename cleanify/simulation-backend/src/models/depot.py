from dataclasses import dataclass
from .base import BaseModel

@dataclass
class Depot(BaseModel):
    """Represents a waste collection depot"""
    name: str = 'Default Depot'