"""Utilities for collecting health metrics for OSRM, VROOM, and distance caches."""
from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from services.distance_matrix_service import DistanceMatrixService
from services.external.osrm_service import OSRMService
from services.external.vroom_service import VROOMService

Coordinate = Tuple[float, float]
SamplePair = Tuple[Coordinate, Coordinate]

DEFAULT_SAMPLE_COORDS: Sequence[SamplePair] = (
    ((24.8607, 67.0011), (24.8615, 67.0100)),
    ((24.8607, 67.0011), (24.8570, 67.0035)),
)


def _mean(values: Iterable[float]) -> Optional[float]:
    values = list(values)
    if not values:
        return None
    try:
        return float(statistics.fmean(values))
    except AttributeError:  # pragma: no cover - older Python fallback
        return float(statistics.mean(values))


def _percentile(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    sorted_vals = sorted(values)
    k = min(len(sorted_vals) - 1, max(0, int(round((len(sorted_vals) - 1) * pct))))
    return float(sorted_vals[k])


@dataclass
class ServiceHealthReporter:
    """Collects latency and cache metrics for critical external services."""

    osrm_service: OSRMService
    vroom_service: VROOMService
    distance_service: DistanceMatrixService
    sample_pairs: Sequence[SamplePair] = DEFAULT_SAMPLE_COORDS

    def collect(
        self,
        bins: Optional[List[Dict]] = None,
        depots: Optional[List[Dict]] = None,
        iterations: int = 1,
    ) -> Dict:
        """Collect a snapshot of service health information."""

        bins = bins or []
        depots = depots or []
        iterations = max(1, iterations)

        osrm_metrics = self._collect_osrm_metrics(bins, depots)
        vroom_metrics = self._collect_vroom_metrics()
        cache_metrics = self._collect_cache_metrics(bins, depots, iterations)

        return {
            "timestamp": time.time(),
            "osrm": osrm_metrics,
            "vroom": vroom_metrics,
            "distance_cache": cache_metrics,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _collect_osrm_metrics(self, bins: List[Dict], depots: List[Dict]) -> Dict:
        available = bool(self.osrm_service.is_service_available())
        pairs = self._resolve_sample_pairs(bins, depots)
        samples: List[Dict] = []
        latencies: List[float] = []

        for (origin_lat, origin_lng), (dest_lat, dest_lng) in pairs:
            start = time.perf_counter()
            distance = self.osrm_service.get_distance_between_points(
                origin_lat,
                origin_lng,
                dest_lat,
                dest_lng,
            )
            duration_ms = (time.perf_counter() - start) * 1000
            latencies.append(duration_ms)
            samples.append(
                {
                    "from": {"lat": origin_lat, "lng": origin_lng},
                    "to": {"lat": dest_lat, "lng": dest_lng},
                    "distance_m": distance,
                    "latency_ms": duration_ms,
                }
            )

        latency_avg = _mean(latencies)
        latency_p95 = _percentile(latencies, 0.95) if latencies else None

        return {
            "available": available,
            "probe_pairs": len(pairs),
            "latency_ms_avg": latency_avg,
            "latency_ms_p95": latency_p95,
            "samples": samples,
            "stats": getattr(self.osrm_service, "stats", {}),
        }

    def _collect_vroom_metrics(self) -> Dict:
        start = time.perf_counter()
        available = bool(self.vroom_service.is_available())
        latency_ms = (time.perf_counter() - start) * 1000
        return {
            "available": available,
            "latency_ms": latency_ms,
            "url": getattr(self.vroom_service, "vroom_url", "unknown"),
        }

    def _collect_cache_metrics(
        self,
        bins: List[Dict],
        depots: List[Dict],
        iterations: int,
    ) -> Dict:
        summary = self.distance_service.last_build_summary or {"status": "empty"}
        cache_sizes = {
            "depots": len(self.distance_service.depot_to_bin),
            "bins": len(self.distance_service.bin_to_depot),
            "depot_to_bin_entries": sum(
                len(v) for v in self.distance_service.depot_to_bin.values()
            ),
            "bin_to_bin_entries": sum(
                len(v) for v in self.distance_service.bin_to_bin.values()
            ),
        }

        performance_runs: List[Dict] = []
        if bins and depots:
            for _ in range(iterations):
                start = time.perf_counter()
                rebuild_summary = self.distance_service.build_matrices(
                    bins,
                    depots,
                    force=True,
                )
                measured = (time.perf_counter() - start)
                performance_runs.append(
                    {
                        "build_seconds_reported": rebuild_summary.get("build_seconds"),
                        "build_seconds_measured": measured,
                        "total_entries": rebuild_summary.get("total_entries"),
                    }
                )

        avg_duration = _mean(
            run["build_seconds_measured"] for run in performance_runs if run
        )

        return {
            "last_build": summary,
            "cache_sizes": cache_sizes,
            "performance": {
                "iterations": len(performance_runs),
                "avg_build_seconds": avg_duration,
                "runs": performance_runs,
            },
        }

    def _resolve_sample_pairs(
        self,
        bins: List[Dict],
        depots: List[Dict],
    ) -> Sequence[SamplePair]:
        pairs: List[SamplePair] = []
        if depots and bins:
            depot = depots[0]
            bin_a = bins[0]
            if self._is_valid_coord(depot) and self._is_valid_coord(bin_a):
                pairs.append(
                    (
                        (float(depot["lat"]), float(depot["lng"])),
                        (float(bin_a["lat"]), float(bin_a["lng"])),
                    )
                )
        if len(bins) >= 2:
            bin_a, bin_b = bins[0], bins[1]
            if self._is_valid_coord(bin_a) and self._is_valid_coord(bin_b):
                pairs.append(
                    (
                        (float(bin_a["lat"]), float(bin_a["lng"])),
                        (float(bin_b["lat"]), float(bin_b["lng"])),
                    )
                )
        return pairs or list(self.sample_pairs)

    @staticmethod
    def _is_valid_coord(entity: Dict) -> bool:
        return all(
            key in entity and isinstance(entity[key], (int, float))
            for key in ("lat", "lng")
        )
