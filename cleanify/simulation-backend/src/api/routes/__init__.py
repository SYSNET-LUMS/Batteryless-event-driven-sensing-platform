"""
API Routes Package
Minimalist routing endpoints
"""

from . import (
    system_routes,
    item_routes,
    simulation_routes,
    dispatch_routes,
    file_routes,
    config_routes,
    schedule_routes,
    batch_sync_routes
)

__all__ = [
    'system_routes',
    'item_routes',
    'simulation_routes',
    'dispatch_routes',
    'file_routes',
    'config_routes',
    'schedule_routes',
    'batch_sync_routes'
]