#!/usr/bin/env python3
"""Geo-zone clustering for waste bins.

The previous depot-radius implementation tightly coupled bin grouping to
distance from depots. That logic produced brittle clusters whenever depots
were missing, misconfigured, or geographically skewed. The new approach uses a
grid/zone projection that is independent of depots and focuses on balancing
collection workload.

New behavior at a glance:
• Project every bin into Web Mercator meters and snap it to a configurable
    square zone (default 600 m).
• All bins that fall inside the same zone form the base of a cluster.
• Oversized zones are split into balanced slices capped at a configurable
    number of bins.
• Sparse zones (few bins or very low accumulated fill) are merged into the
    nearest neighboring cluster to avoid under-utilized trips.

This produces predictable, depot-agnostic clusters while still keeping nearby
bins together for routing.
"""

import math
import os
from collections import defaultdict
from statistics import mean
from typing import Dict, List, Optional, Tuple, Union

from config.settings import Config
from services.external.osrm_service import OSRMService
from utils.distance import calculate_haversine_distance

EARTH_RADIUS_M = 6378137.0


class ClusteringService:
    """Zone-based clustering service that balances workload without depot data."""

    def __init__(self, config: Optional[Config] = None, osrm_service: Optional[OSRMService] = None):
        # Store optional services for compatibility with existing call-sites
        self.config = config or Config()
        self.osrm_service = osrm_service

        # Zone/grid parameters (all tunable via environment variables)
        self.zone_size_m = max(50.0, float(os.getenv('CLUSTER_ZONE_SIZE_M', '600')))
        self.max_cluster_bins = max(1, int(os.getenv('CLUSTER_MAX_BIN_COUNT', '12')))
        self.min_cluster_bins = max(1, int(os.getenv('CLUSTER_MIN_BIN_COUNT', '2')))
        if self.min_cluster_bins > self.max_cluster_bins:
            self.min_cluster_bins = self.max_cluster_bins
        self.min_cluster_fill_percent = max(0.0, float(os.getenv('CLUSTER_MIN_FILL_PERCENT', '20')))
        self.merge_distance_multiplier = max(1.0, float(os.getenv('CLUSTER_MERGE_DISTANCE_MULTIPLIER', '1.5')))

        # Legacy fields preserved for backward compatibility (no longer used directly)
        self.depot_distance_percentage = float(os.getenv('DEPOT_DISTANCE_PERCENTAGE', '0.0'))
        self.max_bin_radius_m = self.zone_size_m
        self.min_bin_radius_m = 0
        self.debug_enabled = False

        print("📊 Clustering Configuration (zone-based):")
        print(f"   zone_size_m: {self.zone_size_m}m")
        print(f"   max_cluster_bins: {self.max_cluster_bins}")
        print(f"   min_cluster_bins: {self.min_cluster_bins}")
        print(f"   min_cluster_fill_percent: {self.min_cluster_fill_percent}%")
    
    def create_simple_dynamic_clusters(self, bins_data: List[Dict], depot_data: Optional[Union[Dict, List[Dict]]] = None) -> Dict:
        """Create geo-zone clusters. Depot data is ignored but accepted for compatibility."""

        try:
            normalized_bins = self._normalize_bins(bins_data)

            if len(normalized_bins) <= 1:
                return {0: normalized_bins} if normalized_bins else {}

            zone_map = self._bucket_bins(normalized_bins)
            raw_clusters: List[List[Dict]] = []
            for zone_bins in zone_map.values():
                raw_clusters.extend(self._split_large_cluster(zone_bins))

            balanced_clusters = self._merge_sparse_clusters(raw_clusters)
            cleaned_clusters = {
                idx: [self._strip_internal_fields(bin_data) for bin_data in cluster]
                for idx, cluster in enumerate(balanced_clusters)
            }

            if self.debug_enabled:
                print(f"Created {len(cleaned_clusters)} clusters across {len(zone_map)} zones")

            return cleaned_clusters

        except Exception as exc:  # pragma: no cover - defensive
            print(f"ERROR in create_simple_dynamic_clusters: {exc}")
            import traceback
            print(traceback.format_exc())
            return self._fallback_clustering(bins_data)
    
    # ------------------------------------------------------------------
    # Helper utilities
    # ------------------------------------------------------------------

    def _normalize_bins(self, bins_data: List[Dict]) -> List[Dict]:
        normalized: List[Dict] = []
        for raw in bins_data or []:
            if not isinstance(raw, dict):
                continue
            lat = raw.get('lat') or raw.get('latitude') or raw.get('location', {}).get('latitude')
            lng = raw.get('lng') or raw.get('longitude') or raw.get('location', {}).get('longitude')
            bin_id = raw.get('id') or raw.get('bin_id')
            if lat is None or lng is None or bin_id is None:
                continue
            copy = dict(raw)
            copy['lat'] = lat
            copy['lng'] = lng
            copy['id'] = bin_id
            normalized.append(copy)
        return normalized

    def _bucket_bins(self, bins_data: List[Dict]) -> Dict[Tuple[int, int], List[Dict]]:
        zone_map: Dict[Tuple[int, int], List[Dict]] = defaultdict(list)
        for bin_data in bins_data:
            x_coord, y_coord = self._project_to_xy(bin_data['lat'], bin_data['lng'])
            zone_key = (
                int(math.floor(x_coord / self.zone_size_m)),
                int(math.floor(y_coord / self.zone_size_m))
            )
            enriched = dict(bin_data)
            enriched['_xy'] = (x_coord, y_coord)
            enriched['_zone_key'] = zone_key
            zone_map[zone_key].append(enriched)
        return zone_map

    def _split_large_cluster(self, cluster_bins: List[Dict]) -> List[List[Dict]]:
        if len(cluster_bins) <= self.max_cluster_bins:
            return [cluster_bins]

        # Sort by fill level so that each split remains balanced by urgency
        sorted_bins = sorted(
            cluster_bins,
            key=lambda b: b.get('fillLevel', 0),
            reverse=True
        )
        chunks: List[List[Dict]] = []
        for start in range(0, len(sorted_bins), self.max_cluster_bins):
            chunks.append(sorted_bins[start:start + self.max_cluster_bins])
        return chunks

    def _merge_sparse_clusters(self, clusters: List[List[Dict]]) -> List[List[Dict]]:
        if not clusters:
            return []

        dense: List[List[Dict]] = []
        sparse: List[List[Dict]] = []
        for cluster in clusters:
            if self._is_sparse_cluster(cluster):
                sparse.append(cluster)
            else:
                dense.append(cluster)

        if not dense and sparse:
            dense.append(sparse.pop(0))

        for cluster in sparse:
            target_index = self._nearest_cluster_index(cluster, dense)
            if target_index is None:
                dense.append(cluster)
            else:
                dense[target_index].extend(cluster)

        return dense

    def _is_sparse_cluster(self, cluster: List[Dict]) -> bool:
        if not cluster:
            return True
        if len(cluster) < self.min_cluster_bins:
            return True
        fill_pct = self._cluster_fill_percentage(cluster)
        return fill_pct < self.min_cluster_fill_percent

    def _cluster_fill_percentage(self, cluster: List[Dict]) -> float:
        total_capacity = sum(bin_data.get('capacity', 500) for bin_data in cluster)
        if total_capacity == 0:
            return 0.0
        total_fill = 0.0
        for bin_data in cluster:
            fill_level = bin_data.get('fillLevel')
            if fill_level is None and 'current_fill' in bin_data and bin_data.get('capacity'):
                fill_level = (bin_data['current_fill'] / bin_data['capacity']) * 100
            total_fill += (fill_level or 0) / 100 * bin_data.get('capacity', 500)
        return (total_fill / total_capacity) * 100

    def _nearest_cluster_index(self, source: List[Dict], targets: List[List[Dict]]) -> Optional[int]:
        if not targets:
            return None
        source_center = self._cluster_centroid(source)
        best_idx = None
        best_distance = float('inf')
        for idx, cluster in enumerate(targets):
            target_center = self._cluster_centroid(cluster)
            distance = math.dist(source_center, target_center)
            if distance < best_distance:
                best_distance = distance
                best_idx = idx
        # Require the nearest dense cluster to be within a reasonable distance
        max_distance = self.zone_size_m * self.merge_distance_multiplier
        return best_idx if best_distance <= max_distance else None

    def _cluster_centroid(self, cluster: List[Dict]) -> Tuple[float, float]:
        xs = [bin_data['_xy'][0] for bin_data in cluster]
        ys = [bin_data['_xy'][1] for bin_data in cluster]
        return (mean(xs), mean(ys))

    def _project_to_xy(self, lat: float, lng: float) -> Tuple[float, float]:
        lat_rad = math.radians(lat)
        lng_rad = math.radians(lng)
        x = EARTH_RADIUS_M * lng_rad
        y = EARTH_RADIUS_M * math.log(math.tan(math.pi / 4 + lat_rad / 2))
        return x, y

    def _strip_internal_fields(self, bin_data: Dict) -> Dict:
        clean = dict(bin_data)
        clean.pop('_xy', None)
        clean.pop('_zone_key', None)
        return clean
    
    def _fallback_clustering(self, bins_data: List[Dict]) -> Dict:
        """Simple fallback - each bin becomes its own cluster."""
        print("Using fallback clustering - each bin becomes its own cluster")
        clusters = {}
        for i, bin_data in enumerate(bins_data):
            clusters[i] = [bin_data]
        return clusters

    def get_clustering_info(self, bins_data: List[Dict], depot_data: Optional[Dict] = None) -> Dict:
        """Return descriptive statistics for the current geo-zone strategy."""

        normalized_bins = self._normalize_bins(bins_data)
        zone_map = self._bucket_bins(normalized_bins)
        cluster_sizes = [len(cluster) for cluster in zone_map.values()]

        info = {
            'approach': 'Geo-Zone Workload Clustering',
            'zone_size_m': self.zone_size_m,
            'zone_count': len(zone_map),
            'max_cluster_bins': self.max_cluster_bins,
            'min_cluster_bins': self.min_cluster_bins,
            'min_cluster_fill_percent': self.min_cluster_fill_percent,
            'average_bins_per_zone': (sum(cluster_sizes) / len(cluster_sizes)) if cluster_sizes else 0,
            'has_depot_data': depot_data is not None,
        }

        # Compatibility keys for existing dashboards/logs
        info['dynamic_threshold_m'] = self.zone_size_m
        info['min_threshold_m'] = self.zone_size_m
        info['max_threshold_m'] = self.zone_size_m
        info['depot_distance_percentage'] = 0.0
        info['per_bin_radius_m'] = None
        info['depot_distances'] = None

        return info
    
    def get_cluster_info(self, clusters: Dict) -> Dict:
        """Summaries plus quality metrics for each cluster."""

        cluster_info: Dict = {}
        for cluster_id, cluster_bins in clusters.items():
            if not cluster_bins:
                continue

            center_lat = sum(bin_data['lat'] for bin_data in cluster_bins) / len(cluster_bins)
            center_lng = sum(bin_data['lng'] for bin_data in cluster_bins) / len(cluster_bins)
            max_distance = 0.0
            avg_distance = 0.0
            pair_count = 0

            for bin_data in cluster_bins:
                distance = calculate_haversine_distance(
                    center_lat,
                    center_lng,
                    bin_data['lat'],
                    bin_data['lng']
                )
                max_distance = max(max_distance, distance)

            # Compute average pairwise distance for a simple compactness proxy
            if len(cluster_bins) > 1:
                total = 0.0
                for i in range(len(cluster_bins)):
                    for j in range(i + 1, len(cluster_bins)):
                        total += calculate_haversine_distance(
                            cluster_bins[i]['lat'], cluster_bins[i]['lng'],
                            cluster_bins[j]['lat'], cluster_bins[j]['lng']
                        )
                        pair_count += 1
                avg_distance = total / pair_count if pair_count else 0.0

            quality_metrics = self._build_quality_metrics(cluster_bins, max_distance, avg_distance)

            cluster_info[cluster_id] = {
                'size': len(cluster_bins),
                'center': {'lat': center_lat, 'lng': center_lng},
                'radius_m': max_distance,
                'bin_ids': [bin_data['id'] for bin_data in cluster_bins],
                'quality_metrics': quality_metrics
            }

        return cluster_info

    def _build_quality_metrics(self, cluster_bins: List[Dict], radius_m: float, avg_distance: float) -> Dict:
        if not cluster_bins:
            return {'quality_rating': 'unknown'}

        compactness_denominator = max(self.zone_size_m * self.merge_distance_multiplier, 1.0)
        compactness_score = max(0.0, 1.0 - (radius_m / compactness_denominator))
        load_balance_score = min(1.0, len(cluster_bins) / self.max_cluster_bins)
        coverage_score = min(1.0, len(cluster_bins) / max(1, self.min_cluster_bins))
        efficiency = max(0.0, 1.0 - (avg_distance / (self.zone_size_m * 2 or 1))) if avg_distance else 1.0

        composite = (compactness_score * 0.5) + (load_balance_score * 0.3) + (efficiency * 0.2)
        if composite >= 0.8:
            rating = 'excellent'
        elif composite >= 0.6:
            rating = 'good'
        elif composite >= 0.4:
            rating = 'fair'
        else:
            rating = 'sparse'

        return {
            'quality_rating': rating,
            'compactness_score': round(compactness_score, 2),
            'load_balance_score': round(load_balance_score, 2),
            'coverage_score': round(coverage_score, 2),
            'collection_efficiency': round(efficiency, 2)
        }

    # Main public method
    def create_clusters(self, bins_data: List[Dict], depot_data: Optional[Dict] = None) -> Dict:
        return self.create_simple_dynamic_clusters(bins_data, depot_data)

    # Legacy method names for backward compatibility
    def create_adaptive_clusters(self, bins_data: List[Dict]) -> Dict:
        return self.create_simple_dynamic_clusters(bins_data, None)