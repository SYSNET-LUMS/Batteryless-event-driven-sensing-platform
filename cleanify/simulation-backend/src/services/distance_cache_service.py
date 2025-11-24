from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import threading

from utils.distance import calculate_haversine_distance


class DistanceCacheService:
    """Thread-safe index of bin/depot coordinates with helper queries."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._bins_by_id: Dict[str, Dict] = {}
        self._depots_by_id: Dict[str, Dict] = {}
        self._signature: Optional[Tuple] = None

    # ------------------------------------------------------------------
    # Cache lifecycle
    # ------------------------------------------------------------------
    def warm_cache(self, bins: List[Dict], depots: List[Dict]) -> None:
        """Rebuild cached coordinate maps from provided records."""
        with self._lock:
            self._bins_by_id = {
                b['id']: b.copy()
                for b in bins
                if b.get('id') and 'lat' in b and 'lng' in b
            }
            self._depots_by_id = {
                d['id']: d.copy()
                for d in depots
                if d.get('id') and 'lat' in d and 'lng' in d
            }
            self._signature = self._build_signature(bins, depots)

    def ensure_cache(self, bins: List[Dict], depots: List[Dict]) -> None:
        """Warm the cache only when system data changes."""
        signature = self._build_signature(bins, depots)
        with self._lock:
            if signature == self._signature:
                return
        self.warm_cache(bins, depots)

    @staticmethod
    def _build_signature(bins: List[Dict], depots: List[Dict]) -> Tuple:
        def _sig(items: List[Dict]) -> Tuple:
            return tuple(
                sorted(
                    (
                        item.get('id'),
                        round(float(item.get('lat', 0.0)), 6),
                        round(float(item.get('lng', 0.0)), 6)
                    )
                    for item in items if item.get('id')
                )
            )
        return (_sig(bins), _sig(depots))

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------
    def get_bin(self, bin_id: str) -> Optional[Dict]:
        with self._lock:
            record = self._bins_by_id.get(bin_id)
            return record.copy() if record else None

    def get_depot(self, depot_id: str) -> Optional[Dict]:
        with self._lock:
            record = self._depots_by_id.get(depot_id)
            return record.copy() if record else None

    def get_bin_neighbors(self, bin_id: str, radius_m: Optional[float] = None,
                           limit: Optional[int] = None) -> List[Dict]:
        """Return neighbor bins sorted by distance."""
        with self._lock:
            origin = self._bins_by_id.get(bin_id)
            if not origin:
                return []
            neighbors = []
            for other_id, other in self._bins_by_id.items():
                if other_id == bin_id:
                    continue
                dist = calculate_haversine_distance(
                    origin['lat'], origin['lng'], other['lat'], other['lng']
                )
                if radius_m is not None and dist > radius_m:
                    continue
                neighbors.append({
                    'bin': other.copy(),
                    'distance_m': dist
                })
            neighbors.sort(key=lambda item: item['distance_m'])
        if limit:
            neighbors = neighbors[:limit]
        return neighbors

    def get_nearest_depot_for_bin(self, bin_id: str) -> Optional[Dict]:
        with self._lock:
            bin_record = self._bins_by_id.get(bin_id)
            if not bin_record or not self._depots_by_id:
                return None
            nearest = None
            nearest_distance = float('inf')
            for depot in self._depots_by_id.values():
                dist = calculate_haversine_distance(
                    bin_record['lat'], bin_record['lng'], depot['lat'], depot['lng']
                )
                if dist < nearest_distance:
                    nearest_distance = dist
                    nearest = depot
        return nearest.copy() if nearest else None

    def get_distance_between_bins(self, bin_a_id: str, bin_b_id: str) -> Optional[float]:
        with self._lock:
            a = self._bins_by_id.get(bin_a_id)
            b = self._bins_by_id.get(bin_b_id)
            if not a or not b:
                return None
        return calculate_haversine_distance(a['lat'], a['lng'], b['lat'], b['lng'])

    def get_distance_bin_to_depot(self, bin_id: str, depot_id: str) -> Optional[float]:
        with self._lock:
            bin_record = self._bins_by_id.get(bin_id)
            depot_record = self._depots_by_id.get(depot_id)
            if not bin_record or not depot_record:
                return None
        return calculate_haversine_distance(
            bin_record['lat'], bin_record['lng'], depot_record['lat'], depot_record['lng']
        )

    def list_bins(self) -> List[Dict]:
        with self._lock:
            return [b.copy() for b in self._bins_by_id.values()]

    def list_depots(self) -> List[Dict]:
        with self._lock:
            return [d.copy() for d in self._depots_by_id.values()]