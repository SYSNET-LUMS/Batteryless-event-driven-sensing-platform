# src/models/base.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class BaseModel:
    """Base model class"""
    id: str
    lat: float
    lng: float