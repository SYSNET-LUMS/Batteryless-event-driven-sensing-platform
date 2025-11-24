import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "cleanify" / "simulation-backend" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from services.distance_cache_service import DistanceCacheService  # type: ignore


def test_distance_cache_neighbors_and_nearest_depot():
    bins = [
        {"id": "BIN_1", "lat": 33.0, "lng": 73.0, "fillLevel": 80, "capacity": 500},
        {"id": "BIN_2", "lat": 33.0005, "lng": 73.0005, "fillLevel": 70, "capacity": 500},
        {"id": "BIN_3", "lat": 33.01, "lng": 73.01, "fillLevel": 55, "capacity": 500},
    ]
    depots = [{"id": "DEPOT_1", "lat": 33.0, "lng": 73.005}]

    cache = DistanceCacheService()
    cache.ensure_cache(bins, depots)

    neighbors = cache.get_bin_neighbors("BIN_1", radius_m=1000)
    assert neighbors
    assert neighbors[0]['bin']['id'] == "BIN_2"
    assert all(entry['distance_m'] <= 1000 for entry in neighbors)

    nearest_depot = cache.get_nearest_depot_for_bin("BIN_1")
    assert nearest_depot
    assert nearest_depot['id'] == "DEPOT_1"

    dist = cache.get_distance_between_bins("BIN_1", "BIN_2")
    assert dist is not None and dist > 0
