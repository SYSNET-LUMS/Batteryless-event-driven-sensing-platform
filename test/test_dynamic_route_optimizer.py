import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'cleanify', 'simulation-backend', 'src'))

from services.routing.dynamic_route_optimizer import DynamicRouteOptimizer


class DummyVroomService:
    def __init__(self):
        self.received_trucks = None
        self.received_bins = None

    def optimize_vehicle_routes(self, trucks_data, selected_bins, depot_data):
        self.received_trucks = trucks_data
        self.received_bins = selected_bins
        return {'success': True, 'routes': []}


def test_optimize_new_routes_uses_available_truck_structure():
    optimizer = DynamicRouteOptimizer(vroom_service=DummyVroomService())

    assigned_bin = {
        'id': 'BIN_1',
        'lat': 33.6100,
        'lng': 73.0500,
        'fillLevel': 90,
        'capacity': 500,
    }

    new_dispatches = [{
        'truck_id': 'TRUCK_1',
        'assigned_bins': [assigned_bin],
        'route': ['BIN_1'],
        'total_load': 450,
        'reason': 'Test dispatch'
    }]

    available_trucks = [{
        'truck': {
            'id': 'TRUCK_1',
            'status': 'idle',
            'lat': 33.6050,
            'lng': 73.0450,
            'capacity': 1000,
            'currentLoad': 0
        },
        'availability_info': {'status': 'available'}
    }]

    depot_data = {
        'id': 'DEPOT_1',
        'lat': 33.6000,
        'lng': 73.0400
    }

    result = optimizer._optimize_new_routes_vroom(
        new_dispatches,
        available_trucks,
        [assigned_bin],
        depot_data,
        current_time_seconds=0
    )

    assert result == []
    assert optimizer.vroom_service.received_trucks[0]['id'] == 'TRUCK_1'
    assert optimizer.vroom_service.received_bins[0]['id'] == 'BIN_1'
