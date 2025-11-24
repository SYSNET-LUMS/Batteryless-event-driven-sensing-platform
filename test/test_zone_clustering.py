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


def _config(max_bins=3, cooldown=0):
    cfg = Config()
    cfg.DISPATCH_NEARBY_RADIUS_M = 2000
    cfg.DISPATCH_MAX_ROUTE_BINS = max_bins
    cfg.DISPATCH_COOLDOWN_MIN = cooldown
    cfg.DISPATCH_CAPACITY_BUFFER_PERCENT = 0
    cfg.DISPATCH_SPEED_KMH = 40
    return cfg


def test_planner_limits_number_of_bins():
    bins = [
        {"id": "BIN_1", "lat": 33.0, "lng": 73.0, "fillLevel": 95, "capacity": 500},
        {"id": "BIN_2", "lat": 33.0005, "lng": 73.0005, "fillLevel": 80, "capacity": 500},
        {"id": "BIN_3", "lat": 33.0007, "lng": 73.0007, "fillLevel": 85, "capacity": 500},
    ]
    trucks = [{"id": "TRUCK_1", "status": "idle", "capacity": 1200, "currentLoad": 0}]
    depots = [{"id": "DEPOT_1", "lat": 32.999, "lng": 73.0}]

    repo = _StubRepository(bins, depots, trucks)
    planner = DispatchPlannerService(
        _config(max_bins=2),
        DistanceCacheService(),
        repo,
        _DummyOptimization(),
    )

    plan = planner.plan_dispatch_for_bin("BIN_1", current_time=0)

    assert plan["status"] == "success"
    assert plan["selected_bins"] == ["BIN_1", "BIN_2"], "Planner should respect max route bins"


def test_planner_skips_bins_in_cooldown():
    bins = [
        {"id": "BIN_1", "lat": 33.0, "lng": 73.0, "fillLevel": 95, "capacity": 500},
        {"id": "BIN_2", "lat": 33.0005, "lng": 73.0005, "fillLevel": 85, "capacity": 500, "lastCollection": 50},
    ]
    trucks = [{"id": "TRUCK_1", "status": "idle", "capacity": 1000, "currentLoad": 0}]
    depots = [{"id": "DEPOT_1", "lat": 32.999, "lng": 73.0}]

    repo = _StubRepository(bins, depots, trucks)
    planner = DispatchPlannerService(
        _config(max_bins=3, cooldown=120),
        DistanceCacheService(),
        repo,
        _DummyOptimization(),
    )

    plan = planner.plan_dispatch_for_bin("BIN_1", current_time=60)

    assert plan["status"] == "success"
    assert plan["selected_bins"] == ["BIN_1"], "Bins inside cooldown window must be skipped"
