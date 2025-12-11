"""Distance matrix caching for depots and bins.

This service precomputes depot→bin, bin→depot, and bin↔bin road distances using
OSRM (with haversine fallback). Future services can request cached distances
instead of repeatedly calling OSRM.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

from services.external.osrm_service import OSRMService
from utils.distance import calculate_haversine_distance


class DistanceMatrixService:
    """Precompute and cache pairwise distances for depots/bins."""

    def __init__(self, osrm_service: Optional[OSRMService] = None):
        self.osrm_service = osrm_service or OSRMService()
        self.depot_to_bin: Dict[str, Dict[str, float]] = {}
        self.bin_to_depot: Dict[str, Dict[str, float]] = {}
        self.bin_to_bin: Dict[str, Dict[str, float]] = {}
        self.last_build_summary: Dict[str, float] = {}
        self._last_signature: Optional[Tuple[Tuple[str, float, float], ...]] = None

    def clear(self) -> None:
        """Reset cached matrices."""
        self.depot_to_bin.clear()
        self.bin_to_depot.clear()
        self.bin_to_bin.clear()
        self.last_build_summary = {
            "status": "cleared",
            "timestamp": time.time(),
        }
        self._last_signature = None

    def build_matrices(
        self,
        bins: List[Dict],
        depots: List[Dict],
        force: bool = False,
    ) -> Dict[str, float]:
        """Build matrices if locations changed or force is True.

        Returns summary dict with build duration and counts.
        """
        signature = self._compute_signature(bins, depots)
        if not force and signature == self._last_signature:
            self.last_build_summary = {
                "status": "cached",
                "timestamp": time.time(),
                "bins": len(bins),
                "depots": len(depots),
            }
            return self.last_build_summary

        start = time.time()
        self.depot_to_bin = self._compute_depot_to_bin(depots, bins)
        self.bin_to_depot = self._compute_bin_to_depot(bins, depots)
        self.bin_to_bin = self._compute_bin_to_bin(bins)
        duration = time.time() - start

        self._last_signature = signature
        self.last_build_summary = {
            "status": "rebuilt",
            "timestamp": time.time(),
            "build_seconds": duration,
            "bins": len(bins),
            "depots": len(depots),
            "total_entries": sum(
                len(v) for v in self.depot_to_bin.values()
            ) + sum(len(v) for v in self.bin_to_bin.values()),
        }
        return self.last_build_summary

    def get_depot_to_bin_distance(self, depot_id: str, bin_id: str) -> Optional[float]:
        return self.depot_to_bin.get(depot_id, {}).get(bin_id)

    def get_bin_to_depot_distance(self, bin_id: str, depot_id: str) -> Optional[float]:
        return self.bin_to_depot.get(bin_id, {}).get(depot_id)

    def get_bin_to_bin_distance(self, bin_a: str, bin_b: str) -> Optional[float]:
        if bin_a == bin_b:
            return 0.0
        return self.bin_to_bin.get(bin_a, {}).get(bin_b)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _compute_signature(
        self, bins: List[Dict], depots: List[Dict]
    ) -> Optional[Tuple[Tuple[str, float, float], ...]]:
        if not bins and not depots:
            return None
        entries = []
        for entity in (*depots, *bins):
            entity_id = entity.get("id")
            if not entity_id:
                continue
            entries.append(
                (
                    entity_id,
                    round(entity.get("lat", 0.0), 6),
                    round(entity.get("lng", 0.0), 6),
                )
            )
        return tuple(sorted(entries)) if entries else None

    def _compute_depot_to_bin(
        self, depots: List[Dict], bins: List[Dict]
    ) -> Dict[str, Dict[str, float]]:
        matrix: Dict[str, Dict[str, float]] = {}
        for depot in depots:
            depot_id = depot.get("id")
            if not depot_id:
                continue
            matrix[depot_id] = {}
            for bin_data in bins:
                bin_id = bin_data.get("id")
                if not bin_id:
                    continue
                dist = self._get_distance(
                    depot.get("lat"),
                    depot.get("lng"),
                    bin_data.get("lat"),
                    bin_data.get("lng"),
                )
                matrix[depot_id][bin_id] = dist
        return matrix

    def _compute_bin_to_depot(
        self, bins: List[Dict], depots: List[Dict]
    ) -> Dict[str, Dict[str, float]]:
        matrix: Dict[str, Dict[str, float]] = {}
        for bin_data in bins:
            bin_id = bin_data.get("id")
            if not bin_id:
                continue
            matrix[bin_id] = {}
            for depot in depots:
                depot_id = depot.get("id")
                if not depot_id:
                    continue
                dist = self._get_distance(
                    bin_data.get("lat"),
                    bin_data.get("lng"),
                    depot.get("lat"),
                    depot.get("lng"),
                )
                matrix[bin_id][depot_id] = dist
        return matrix

    def _compute_bin_to_bin(self, bins: List[Dict]) -> Dict[str, Dict[str, float]]:
        matrix: Dict[str, Dict[str, float]] = {
            bin_data.get("id"): {}
            for bin_data in bins
            if bin_data.get("id")
        }
        bin_list = [b for b in bins if b.get("id")]
        for i, bin_a in enumerate(bin_list):
            for j in range(i + 1, len(bin_list)):
                bin_b = bin_list[j]
                dist = self._get_distance(
                    bin_a.get("lat"),
                    bin_a.get("lng"),
                    bin_b.get("lat"),
                    bin_b.get("lng"),
                )
                matrix[bin_a["id"]][bin_b["id"]] = dist
                matrix[bin_b["id"]][bin_a["id"]] = dist
        return matrix

    def _get_distance(
        self,
        lat1: Optional[float],
        lng1: Optional[float],
        lat2: Optional[float],
        lng2: Optional[float],
    ) -> float:
        if None in (lat1, lng1, lat2, lng2):
            return 0.0
        try:
            return self.osrm_service.get_distance_between_points(lat1, lng1, lat2, lng2)
        except Exception:
            return calculate_haversine_distance(lat1, lng1, lat2, lng2)