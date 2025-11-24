import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "cleanify" / "simulation-backend" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from config.settings import Config  # type: ignore
from services.distance_cache_service import DistanceCacheService  # type: ignore
from services.dispatch_planner_service import DispatchPlannerService  # type: ignore


class _StubRepository:
    def __init__(self, bins, depots, trucks):
        self._bins = bins
        self._depots = depots
        self._trucks = trucks

    def get_bins(self):
        return list(self._bins)

    def get_depots(self):
        return list(self._depots)

    def get_trucks(self):
        return list(self._trucks)


class _DummyOptimization:
    def calculate_urgency_score(self, bin_data, context_bins=None):
        return {"total": bin_data.get("fillLevel", 0)}


def _base_config():
    config = Config()
    config.DISPATCH_NEARBY_RADIUS_M = 2000
    config.DISPATCH_MAX_ROUTE_BINS = 3
    config.DISPATCH_CAPACITY_BUFFER_PERCENT = 0
    config.DISPATCH_SPEED_KMH = 30
    return config


def test_dispatch_planner_selects_neighbor_bins():
    bins = [
        {"id": "BIN_A", "lat": 33.0, "lng": 73.0, "fillLevel": 95, "capacity": 500},
        {"id": "BIN_B", "lat": 33.0008, "lng": 73.0008, "fillLevel": 85, "capacity": 500},
        {"id": "BIN_C", "lat": 33.02, "lng": 73.02, "fillLevel": 40, "capacity": 500},
    ]
    trucks = [{"id": "TRUCK_1", "status": "idle", "capacity": 1000, "currentLoad": 0}]
    depots = [{"id": "DEPOT_1", "lat": 32.999, "lng": 73.0}]

    repo = _StubRepository(bins, depots, trucks)
    planner = DispatchPlannerService(
        _base_config(),
        DistanceCacheService(),
        repo,
        _DummyOptimization(),
    )

    plan = planner.plan_dispatch_for_bin("BIN_A", current_time=0)

    assert plan["status"] == "success"
    assert plan["selected_bins"][0] == "BIN_A"
    assert "BIN_B" in plan["selected_bins"], "Nearby eligible bin should be included"
    assert plan["distance_km"] > 0
    assert plan["route"][0]["type"] == "depot"
    assert plan["route"][-1]["type"] == "depot"


def test_dispatch_planner_errors_when_no_idle_trucks():
    bins = [
        {"id": "BIN_A", "lat": 33.0, "lng": 73.0, "fillLevel": 95, "capacity": 500},
    ]
    trucks = [{"id": "TRUCK_1", "status": "en_route", "capacity": 1000, "currentLoad": 0}]
    depots = [{"id": "DEPOT_1", "lat": 32.999, "lng": 73.0}]

    repo = _StubRepository(bins, depots, trucks)
    planner = DispatchPlannerService(
        _base_config(),
        DistanceCacheService(),
        repo,
        _DummyOptimization(),
    )

    plan = planner.plan_dispatch_for_bin("BIN_A", current_time=0)

    assert plan["status"] == "error"
    assert plan.get("reason") == "no_idle_trucks"
