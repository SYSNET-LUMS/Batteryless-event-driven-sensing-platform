import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "cleanify" / "simulation-backend" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from api.routes.dispatch_routes import (  # type: ignore  # noqa: E402
    _classify_bins_by_urgency,
    _should_dispatch_unified,
    _build_proximity_routes,
    _should_use_proximity_routes,
    _select_active_dispatch_bins,
    _select_trucks_for_active_dispatch,
)


def _make_bin(fill_level: float, threshold: float, *, capacity: float = 500.0) -> dict:
    return {
        "id": "BIN_TEST",
        "fillLevel": fill_level,
        "capacity": capacity,
        "dynamic_threshold": threshold,
        "time_to_overflow": 10.0,
    }


def test_bin_crossing_dynamic_threshold_is_critical():
    bin_data = _make_bin(fill_level=65.0, threshold=60.0)
    critical, near, low = _classify_bins_by_urgency([bin_data], simulation_time=0)

    assert bin_data in critical
    assert not near
    assert not low


def test_near_threshold_bins_dispatch_when_volume_sufficient():
    bins = [
        _make_bin(fill_level=58.0, threshold=60.0),
        _make_bin(fill_level=57.5, threshold=60.0),
    ]
    critical, near, _ = _classify_bins_by_urgency(bins, simulation_time=0)

    trucks = [{"capacity": 600}]

    assert not critical
    assert near  # bins are approaching their DT
    assert _should_dispatch_unified(critical, near, trucks)


def test_proximity_routes_split_bins_by_nearest_truck():
    bins = [
        {
            "id": "BIN_WEST",
            "lat": 31.50,
            "lng": 74.30,
            "fillLevel": 70,
            "capacity": 600,
        },
        {
            "id": "BIN_EAST",
            "lat": 31.60,
            "lng": 74.50,
            "fillLevel": 72,
            "capacity": 600,
        },
    ]
    trucks = [
        {"id": "TRUCK_1", "lat": 31.50, "lng": 74.30, "speed": 50},
        {"id": "TRUCK_2", "lat": 31.60, "lng": 74.50, "speed": 50},
    ]
    depot = {"id": "DEPOT", "lat": 31.55, "lng": 74.40}

    routes = _build_proximity_routes(bins, trucks, depot)
    assignments = {route["truck_id"]: route["bin_ids"] for route in routes}

    assert assignments["TRUCK_1"] == ["BIN_WEST"]
    assert assignments["TRUCK_2"] == ["BIN_EAST"]


def test_proximity_routes_override_single_truck_vroom_result():
    vroom_routes = [{"truck_id": "TRUCK_1", "bin_ids": ["BIN_WEST", "BIN_EAST"]}]
    proximity_routes = [
        {"truck_id": "TRUCK_1", "bin_ids": ["BIN_WEST"]},
        {"truck_id": "TRUCK_2", "bin_ids": ["BIN_EAST"]},
    ]
    trucks = [{"id": "TRUCK_1"}, {"id": "TRUCK_2"}]

    assert _should_use_proximity_routes(vroom_routes, proximity_routes, trucks)


def test_single_critical_bin_limits_cluster_bins():
    depot = {"id": "DEPOT_1", "lat": 31.46877223947863, "lng": 74.41343478865556}
    bins = [
        {
            "id": "BIN_1",
            "lat": 31.49111408991619,
            "lng": 74.40361882388817,
            "fillLevel": 40,
            "dynamic_threshold": 68.8,
        },
        {
            "id": "BIN_2",
            "lat": 31.46425075401612,
            "lng": 74.42559538913389,
            "fillLevel": 30,
            "dynamic_threshold": 78.4,
        },
        {
            "id": "BIN_3",
            "lat": 31.49660300452092,
            "lng": 74.40396532270107,
            "fillLevel": 72,
            "dynamic_threshold": 54.4,
        },
        {
            "id": "BIN_4",
            "lat": 31.46915544106433,
            "lng": 74.38687772122906,
            "fillLevel": 35,
            "dynamic_threshold": 64.0,
        },
    ]

    critical_bins, _, _ = _classify_bins_by_urgency(bins, simulation_time=0)
    assert any(b["id"] == "BIN_3" for b in critical_bins)

    selected = _select_active_dispatch_bins(bins, critical_bins, depot)
    selected_ids = {b["id"] for b in selected}

    assert "BIN_3" in selected_ids
    assert "BIN_1" in selected_ids  # neighbor on the same leg
    assert "BIN_2" not in selected_ids
    assert "BIN_4" not in selected_ids


def test_single_critical_bin_limits_truck_count():
    depot = {"id": "DEPOT_1", "lat": 31.46877223947863, "lng": 74.41343478865556}
    bins = [
        {
            "id": "BIN_3",
            "lat": 31.49660300452092,
            "lng": 74.40396532270107,
            "fillLevel": 72,
            "dynamic_threshold": 54.4,
        }
    ]
    trucks = [
        {"id": "TRUCK_1", "lat": 31.490, "lng": 74.405},
        {"id": "TRUCK_2", "lat": 31.4688, "lng": 74.4134},
    ]

    selected_trucks = _select_trucks_for_active_dispatch(trucks, [bins[0]], depot)
    assert len(selected_trucks) == 1
    assert selected_trucks[0]["id"] == "TRUCK_1"
