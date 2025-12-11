import math
import os
import sys
from pathlib import Path

# Ensure simulation-backend src directory is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "cleanify" / "simulation-backend" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from config.settings import Config  # type: ignore  # noqa: E402
from services.external.vroom_service import VROOMService  # type: ignore  # noqa: E402


def _build_sample_bins():
    return [
        {
            "id": "BIN_A",
            "lat": 31.5,
            "lng": 74.3,
            "fillLevel": 80,
            "capacity": 500,
        },
        {
            "id": "BIN_B",
            "lat": 31.6,
            "lng": 74.4,
            "fillLevel": 55.5,
            "capacity": 750,
        },
    ]


def _build_sample_trucks():
    return [
        {
            "id": "TRUCK_1",
            "lat": 31.5,
            "lng": 74.3,
            "capacity": 1000,
        }
    ]


def _build_depot():
    return {"id": "DEPOT_1", "lat": 31.5, "lng": 74.3}


def test_constraints_payload_uses_liters_for_delivery():
    service = VROOMService(config=Config())
    bins = _build_sample_bins()
    trucks = _build_sample_trucks()
    depot = _build_depot()

    payload, _, _ = service._build_vroom_payload_with_constraints(
        bins=bins,
        trucks=trucks,
        depot=depot,
        critical_bins=[],
        simulation_time=0,
    )

    deliveries = [job["delivery"][0] for job in payload["jobs"]]
    expected = [400, 416]  # 500*0.8, 750*0.555 rounded to ints
    assert deliveries == expected, f"expected liter loads {expected}, got {deliveries}"


def test_legacy_payload_uses_liters_for_delivery():
    service = VROOMService(config=Config())
    bins = _build_sample_bins()
    trucks = _build_sample_trucks()
    depot = _build_depot()

    payload, _, _ = service._build_vroom_payload(bins=bins, trucks=trucks, depot=depot)

    deliveries = [job["delivery"][0] for job in payload["jobs"]]
    expected = [400, 416]
    assert deliveries == expected, f"expected liter loads {expected}, got {deliveries}"
