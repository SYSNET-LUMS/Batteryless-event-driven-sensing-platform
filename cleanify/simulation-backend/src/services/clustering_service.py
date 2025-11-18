#!/usr/bin/env python3
"""
Proximity-based clustering for waste bins.

Desired logic (as specified):
- For each bin, compute distance to the nearest depot (supports multiple depots)
- Per-bin radius = min(percentage * nearest-depot-distance, upper_cap)
    • No lower cap
    • If no depots exist, use a default radius for all bins
- Connect two bins if either lies within the other's radius
    • i.e., distance(i,j) <= max(radius_i, radius_j)
- Clusters are connected components of this graph

Creates geographically sensible clusters based on bin proximity.
"""

import os
from typing import Dict, List, Optional, Tuple, Union
from config.settings import Config
from services.external.osrm_service import OSRMService
from utils.distance import calculate_haversine_distance


class ClusteringService:
    """
    Proximity-based clustering service that creates geographically sensible clusters.
    
    Algorithm:
    1. Calculate dynamic bin service radius based on depot proximity (requires at least one depot)
    2. For each bin, find all nearby bins within its service radius
    3. Group them into connected components (clusters)
    4. Merge overlapping clusters automatically
    
    Each bin has a configurable service radius (1000-2000m range). Bins within
    each other's service radius get clustered together. Clusters can grow to any size
    as long as bins are connected through their service areas.
    
    This creates clusters where bins that are close to each other end up together,
    which is much more intuitive than mathematical clustering approaches.
    
    Note: If no depots are provided, clustering will raise a ValueError.
    """
    
    def __init__(self, config: Optional[Config] = None, osrm_service: Optional[OSRMService] = None):
        # Store optional services
        self.config = config or Config()
        self.osrm_service = osrm_service
        # Clustering parameters - read from environment variables with defaults
        self.depot_distance_percentage = float(os.getenv('DEPOT_DISTANCE_PERCENTAGE', '0.35'))
        # No lower bound; keep field for reference but do not apply
        self.min_bin_radius_m = 0
        self.max_bin_radius_m = float(os.getenv('MAX_BIN_RADIUS_M', '2000'))
        self.debug_enabled = False  # Control debug output
        # Log clustering configuration on initialization
        print(f"📊 Clustering Configuration (from environment):")
        print(f"   DEPOT_DISTANCE_PERCENTAGE: {self.depot_distance_percentage} ({self.depot_distance_percentage * 100}%)")
        print(f"   MAX_BIN_RADIUS_M: {self.max_bin_radius_m}m")
    
    def create_simple_dynamic_clusters(self, bins_data: List[Dict], depot_data: Optional[Union[Dict, List[Dict]]] = None) -> Dict:
        """
        Create clusters using simple proximity logic:
        1. For each bin, check if there's a nearby bin within radius
        2. If yes, add to the same cluster 
        3. If not, create new cluster for that bin
        4. Handle edge cases and merge overlapping clusters
        
        Args:
            bins_data: List of bin dictionaries with lat, lng, etc.
            depot_data: Depot dictionary with lat, lng (optional)
            
        Returns:
            Dictionary of clusters with cluster_id as key and list of bins as value
        """
        try:
            if self.debug_enabled:
                print("="*60)
                print("CLUSTERING DEBUG START")
                print("="*60)
                
                print(f"Input validation:")
                print(f"  bins_data type: {type(bins_data)}")
                print(f"  bins_data length: {len(bins_data) if bins_data else 'None'}")
                print(f"  depot_data type: {type(depot_data)}")
                print(f"  depot_data: {depot_data}")
                
                if bins_data:
                    print(f"  First bin structure: {bins_data[0]}")
                    print(f"  All bin IDs: {[b.get('id', 'NO_ID') for b in bins_data]}")
                    
                    # Validate bin data structure
                    for i, bin_data in enumerate(bins_data):
                        if not isinstance(bin_data, dict):
                            print(f"ERROR: Bin {i} is not a dictionary: {type(bin_data)}")
                        elif 'lat' not in bin_data or 'lng' not in bin_data or 'id' not in bin_data:
                            print(f"ERROR: Bin {i} missing required fields: {bin_data}")
            
            if len(bins_data) <= 1:
                if self.debug_enabled:
                    print("Only 0-1 bins, returning simple clustering")
                return {0: bins_data}
            
            # Calculate per-bin radii
            if self.debug_enabled:
                print("\nCALCULATING PER-BIN SERVICE RADII:")
            bin_radii = self._compute_per_bin_radii(bins_data, depot_data)
            if self.debug_enabled:
                radii_values = list(bin_radii.values())
                if radii_values:
                    print(f"  Radii stats (m): min={min(radii_values):.1f}, max={max(radii_values):.1f}, avg={sum(radii_values)/len(radii_values):.1f}")
            
            # Proximity clustering using per-bin radii
            if self.debug_enabled:
                print("\nSTARTING PROXIMITY CLUSTERING:")
            clusters = self._cluster_by_proximity_per_bin(bins_data, bin_radii)
            
            print(f"\nCLUSTERING RESULTS:")
            print(f"  Created {len(clusters)} clusters")
            
            for cluster_id, cluster_bins in clusters.items():
                bin_ids = [b['id'] for b in cluster_bins]
                print(f"  Cluster {cluster_id}: {len(cluster_bins)} bins - {bin_ids}")
                
                if len(cluster_bins) > 1:
                    # Calculate and log internal distances
                    print(f"    Internal distances:")
                    max_dist = 0
                    for i in range(len(cluster_bins)):
                        for j in range(i + 1, len(cluster_bins)):
                            dist = calculate_haversine_distance(
                                cluster_bins[i]['lat'], cluster_bins[i]['lng'],
                                cluster_bins[j]['lat'], cluster_bins[j]['lng']
                            )
                            max_dist = max(max_dist, dist)
                            print(f"      {cluster_bins[i]['id']} to {cluster_bins[j]['id']}: {dist:.1f}m")
                    print(f"    Max internal distance: {max_dist:.1f}m")
            
            print("="*60)
            print("CLUSTERING DEBUG END")
            print("="*60)
            
            return clusters
            
        except Exception as e:
            print(f"ERROR in create_simple_dynamic_clusters: {e}")
            print(f"Exception type: {type(e)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return self._fallback_clustering(bins_data)
    
    def _compute_per_bin_radii(self, bins_data: List[Dict], depot_data: Optional[Union[Dict, List[Dict]]]) -> Dict[str, float]:
        """
        Compute per-bin service radii based on nearest depot distance.
        - Supports multiple depots; uses nearest.
        - radius_i = min(percentage * nearest_distance_i, max_cap)
        - No lower bound.
        - If no depots, raises ValueError.
        Returns dict: bin_id -> radius_m
        """
        # Normalize depot list
        depots: List[Dict] = []
        if depot_data:
            if isinstance(depot_data, dict):
                depots = [depot_data]
            elif isinstance(depot_data, list):
                depots = [d for d in depot_data if isinstance(d, dict) and 'lat' in d and 'lng' in d]
        
        if not depots:
            raise ValueError("No depots provided. At least one depot is required for clustering.")
        radii: Dict[str, float] = {}
        
        # Compute nearest depot distance per bin
        for b in bins_data:
            min_dist = float('inf')
            for d in depots:
                dist = calculate_haversine_distance(d['lat'], d['lng'], b['lat'], b['lng'])
                if dist < min_dist:
                    min_dist = dist
            # Apply percentage and cap (no lower bound)
            base = min_dist * self.depot_distance_percentage
            r = min(base, float(self.max_bin_radius_m))
            radii[b['id']] = r
            if self.debug_enabled:
                print(f"  Bin {b['id']}: nearest_depot={min_dist:.1f}m -> radius={r:.1f}m")
        return radii
    
    def _cluster_by_proximity_per_bin(self, bins_data: List[Dict], bin_radii: Dict[str, float]) -> Dict:
        """
        Proximity clustering using per-bin radii.
        Edge between i and j if distance(i,j) <= max(radius_i, radius_j).
        Clusters are connected components.
        """
        n = len(bins_data)
        if n == 0:
            return {}
        # Map id to index and back
        id_to_idx: Dict[str, int] = {b['id']: i for i, b in enumerate(bins_data)}
        idx_to_id: List[str] = [b['id'] for b in bins_data]
        # Adjacency list
        adj: List[List[int]] = [[] for _ in range(n)]
        # Build edges (O(n^2))
        for i in range(n):
            bi = bins_data[i]
            if bi['id'] not in bin_radii:
                raise ValueError(f"Missing radius for bin {bi['id']}. Ensure depot data is provided and radii are computed.")
            ri = bin_radii[bi['id']]
            for j in range(i+1, n):
                bj = bins_data[j]
                if bj['id'] not in bin_radii:
                    raise ValueError(f"Missing radius for bin {bj['id']}. Ensure depot data is provided and radii are computed.")
                rj = bin_radii[bj['id']]
                dist = calculate_haversine_distance(bi['lat'], bi['lng'], bj['lat'], bj['lng'])
                if dist <= max(ri, rj):
                    adj[i].append(j)
                    adj[j].append(i)
        # BFS/DFS to get components
        visited = [False]*n
        clusters: Dict[int, List[Dict]] = {}
        cid = 0
        for i in range(n):
            if visited[i]:
                continue
            # Start new component
            queue = [i]
            visited[i] = True
            comp_indices = []
            while queue:
                u = queue.pop()
                comp_indices.append(u)
                for v in adj[u]:
                    if not visited[v]:
                        visited[v] = True
                        queue.append(v)
            clusters[cid] = [bins_data[k] for k in comp_indices]
            cid += 1
        return clusters
    
    def _fallback_clustering(self, bins_data: List[Dict]) -> Dict:
        """Simple fallback - each bin becomes its own cluster."""
        print("Using fallback clustering - each bin becomes its own cluster")
        clusters = {}
        for i, bin_data in enumerate(bins_data):
            clusters[i] = [bin_data]
        return clusters

    def get_clustering_info(self, bins_data: List[Dict], depot_data: Optional[Dict] = None) -> Dict:
        """Get information about the clustering approach for this data."""
        radii = self._compute_per_bin_radii(bins_data, depot_data)
        radii_list = list(radii.values())
        depot_distances: List[float] = []
        depots: List[Dict] = []
        if depot_data:
            if isinstance(depot_data, dict):
                depots = [depot_data]
            elif isinstance(depot_data, list):
                depots = depot_data
        if depots:
            for b in bins_data:
                nearest = min(calculate_haversine_distance(d['lat'], d['lng'], b['lat'], b['lng']) for d in depots)
                depot_distances.append(nearest)
        info = {
            'approach': 'Per-bin Proximity Clustering',
            'per_bin_radius_m': {
                'min_m': min(radii_list) if radii_list else None,
                'max_m': max(radii_list) if radii_list else None,
                'avg_m': sum(radii_list)/len(radii_list) if radii_list else None,
            },
            'depot_distance_percentage': self.depot_distance_percentage * 100,
            'max_bin_radius_m': self.max_bin_radius_m,
            'depot_distances': {
                'min_m': min(depot_distances) if depot_distances else None,
                'max_m': max(depot_distances) if depot_distances else None,
                'avg_m': sum(depot_distances) / len(depot_distances) if depot_distances else None
            },
            'has_depot_data': bool(depots)
        }
        # Backward-compatibility for callers expecting old keys
        if radii_list:
            info['dynamic_threshold_m'] = info['per_bin_radius_m']['avg_m']
            info['min_threshold_m'] = info['per_bin_radius_m']['min_m']
            info['max_threshold_m'] = info['per_bin_radius_m']['max_m']
        else:
            info['dynamic_threshold_m'] = None
            info['min_threshold_m'] = None
            info['max_threshold_m'] = None
        return info
    
    def get_cluster_info(self, clusters: Dict) -> Dict:
        """Get cluster information in expected format."""
        cluster_info = {}
        
        for cluster_id, cluster_bins in clusters.items():
            if not cluster_bins:
                continue
                
            # Calculate cluster center
            center_lat = sum(bin_data['lat'] for bin_data in cluster_bins) / len(cluster_bins)
            center_lng = sum(bin_data['lng'] for bin_data in cluster_bins) / len(cluster_bins)
            
            # Calculate cluster radius (max distance from center)
            max_distance = 0
            for bin_data in cluster_bins:
                distance = calculate_haversine_distance(
                    center_lat, center_lng,
                    bin_data['lat'], bin_data['lng']
                )
                max_distance = max(max_distance, distance)
            
            cluster_info[cluster_id] = {
                'size': len(cluster_bins),
                'center': {'lat': center_lat, 'lng': center_lng},
                'radius_m': max_distance,
                'bin_ids': [bin_data['id'] for bin_data in cluster_bins]
            }
        
        return cluster_info

    # Main public method
    def create_clusters(self, bins_data: List[Dict], depot_data: Optional[Dict] = None) -> Dict:
        """
        Create clusters using proximity-based logic.
        
        Args:
            bins_data: List of bin dictionaries with lat, lng, etc.
            depot_data: Depot dictionary with lat, lng (optional)
            
        Returns:
            Dictionary of clusters with cluster_id as key and list of bins as value
        """
        return self.create_simple_dynamic_clusters(bins_data, depot_data)

    # Legacy method names for backward compatibility
    def create_adaptive_clusters(self, bins_data: List[Dict]) -> Dict:
        """Legacy method - uses proximity clustering."""
        return self.create_simple_dynamic_clusters(bins_data, None)