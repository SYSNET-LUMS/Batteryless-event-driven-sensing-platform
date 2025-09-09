# src/models/bin.py
from dataclasses import dataclass
from typing import Optional, List
from .base import BaseModel

@dataclass
class Bin(BaseModel):
    """Represents a waste bin"""
    fill_level: float = 20.0  # percentage 0-100
    capacity: float = 500.0    # liters
    fill_rate: float = 3.5     # liters per hour
    threshold: float = 80.0
    dynamic_threshold: Optional[float] = None
    last_collection: Optional[float] = None