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


def _planner(bins, trucks, depots, **overrides):
    cfg = Config()
    cfg.DISPATCH_NEARBY_RADIUS_M = overrides.get("radius", 1500)
    cfg.DISPATCH_COOLDOWN_MIN = overrides.get("cooldown", 30)
    cfg.DISPATCH_MAX_ROUTE_BINS = overrides.get("max_bins", 5)
    cfg.DISPATCH_CAPACITY_BUFFER_PERCENT = overrides.get("buffer", 5)
    cfg.DISPATCH_SPEED_KMH = overrides.get("speed", 25)

    return DispatchPlannerService(
        cfg,
        DistanceCacheService(),
        _StubRepository(bins, depots, trucks),
        _DummyOptimization(),
    )


def test_proactive_dispatch_includes_nearby_bins():
    bins = [
        {"id": "BIN_PRIMARY", "lat": 33.0, "lng": 73.0, "fillLevel": 93, "capacity": 600, "threshold": 80},
        {"id": "BIN_SECONDARY", "lat": 33.0006, "lng": 73.0005, "fillLevel": 82, "capacity": 600, "threshold": 78},
        {"id": "BIN_FAR", "lat": 33.02, "lng": 73.02, "fillLevel": 90, "capacity": 600, "threshold": 80},
    ]
    trucks = [
        {"id": "TRUCK_1", "status": "idle", "capacity": 1800, "currentLoad": 200},
    ]
    depots = [{"id": "DEPOT_1", "lat": 33.001, "lng": 73.0}]

    planner = _planner(bins, trucks, depots, radius=2000, buffer=0)

    plan = planner.plan_dispatch_for_bin("BIN_PRIMARY", current_time=3600)

    assert plan["status"] == "success"
    assert plan["selected_bins"][0] == "BIN_PRIMARY"
    assert "BIN_SECONDARY" in plan["selected_bins"], "Nearby bins should be proactively added"
    assert "BIN_FAR" not in plan["selected_bins"], "Bins outside the radius must be ignored"


def test_proactive_dispatch_respects_cooldowns_and_thresholds():
    bins = [
        {"id": "BIN_TRIGGER", "lat": 52.1, "lng": 4.9, "fillLevel": 96, "capacity": 500, "threshold": 80},
        {"id": "BIN_RECENT", "lat": 52.1003, "lng": 4.9003, "fillLevel": 78, "capacity": 500, "threshold": 75, "lastCollection": 700},
        {"id": "BIN_LOW", "lat": 52.1004, "lng": 4.9001, "fillLevel": 20, "capacity": 500, "threshold": 70},
    ]
    trucks = [
        {"id": "TRUCK_A", "status": "idle", "capacity": 1200, "currentLoad": 0},
    ]
    depots = [{"id": "DEPOT_MAIN", "lat": 52.099, "lng": 4.901}]

    planner = _planner(bins, trucks, depots, radius=1000, cooldown=60, buffer=0)

    plan = planner.plan_dispatch_for_bin("BIN_TRIGGER", current_time=720)

    assert plan["status"] == "success"
    assert plan["selected_bins"] == ["BIN_TRIGGER"], "Cooldown/low-fill bins shouldn't be grouped"


def test_proactive_dispatch_requires_idle_truck():
    bins = [
        {"id": "BIN_ONLY", "lat": 40.0, "lng": -3.0, "fillLevel": 97, "capacity": 700, "threshold": 75},
    ]
    trucks = [
        {"id": "TRUCK_BUSY", "status": "active", "capacity": 1500, "currentLoad": 200},
    ]
    depots = [{"id": "DEPOT_W", "lat": 40.0, "lng": -3.0}]

    planner = _planner(bins, trucks, depots)

    plan = planner.plan_dispatch_for_bin("BIN_ONLY", current_time=0)

    assert plan["status"] == "error"
    assert plan["reason"] == "no_idle_trucks"