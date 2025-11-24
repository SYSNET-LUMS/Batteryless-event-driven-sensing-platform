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
        return self._bins

    def get_depots(self):
        return self._depots

    def get_trucks(self):
        return self._trucks


class _DummyOptimization:
    def calculate_urgency_score(self, bin_data, context_bins=None):
        return {"total": bin_data.get("fillLevel", 0)}


def _planner(truck_load: float = 0.0) -> DispatchPlannerService:
    bins = [
        {"id": "BIN_A", "lat": 33.0, "lng": 73.0, "fillLevel": 90, "capacity": 500},
        {"id": "BIN_B", "lat": 33.0007, "lng": 73.0003, "fillLevel": 80, "capacity": 500},
    ]
    trucks = [
        {
            "id": "TRUCK_1",
            "status": "idle",
            "capacity": 1000,
            "currentLoad": truck_load,
        }
    ]
    depots = [{"id": "DEPOT_1", "lat": 32.999, "lng": 73.0}]

    cfg = Config()
    cfg.DISPATCH_NEARBY_RADIUS_M = 1500
    cfg.DISPATCH_CAPACITY_BUFFER_PERCENT = 0
    cfg.DISPATCH_MAX_ROUTE_BINS = 3
    cfg.DISPATCH_SPEED_KMH = 30

    return DispatchPlannerService(
        cfg,
        DistanceCacheService(),
        _StubRepository(bins, depots, trucks),
        _DummyOptimization(),
    )


def test_repeated_dispatches_return_identical_plan():
    planner = _planner()
    first = planner.plan_dispatch_for_bin("BIN_A", current_time=0)
    second = planner.plan_dispatch_for_bin("BIN_A", current_time=60)

    assert first["status"] == "success"
    assert second["status"] == "success"
    assert first["selected_bins"] == second["selected_bins"]
    assert first["route"] == second["route"]


def test_planner_honors_truck_load_between_calls():
    empty_plan = _planner(truck_load=0).plan_dispatch_for_bin("BIN_A", 0)
    capped_plan = _planner(truck_load=800).plan_dispatch_for_bin("BIN_A", 0)

    assert empty_plan["status"] == "success"
    assert capped_plan["status"] == "success"
    assert len(empty_plan["selected_bins"]) > len(capped_plan["selected_bins"])
