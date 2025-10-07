#!/usr/bin/env python3
"""
Proximity-based clustering service for waste bins.
Creates geographically sensible clusters based on bin proximity.
"""

from typing import Dict, List, Optional
from config.settings import Config
from services.external.osrm_service import OSRMService
from utils.distance import calculate_haversine_distance


class ClusteringService:
    """
    Proximity-based clustering service that creates geographically sensible clusters.
    
    Algorithm:
    1. Calculate dynamic bin service radius based on depot proximity (if available)
    2. For each bin, find all nearby bins within its service radius
    3. Group them into connected components (clusters)
    4. Merge overlapping clusters automatically
    
    Each bin has a configurable service radius (1000-2000m range). Bins within
    each other's service radius get clustered together. Clusters can grow to any size
    as long as bins are connected through their service areas.
    
    This creates clusters where bins that are close to each other end up together,
    which is much more intuitive than mathematical clustering approaches.
    """
    
    def __init__(self, config: Optional[Config] = None, osrm_service: Optional[OSRMService] = None):
        # Store optional services
        self.config = config or Config()
        self.osrm_service = osrm_service
        
        # Clustering parameters - individual bin radius caps
        self.depot_distance_percentage = 0.3  # 30% of depot distance for bin service radius
        self.min_bin_radius_m = 100   # Minimum service radius per bin
        self.max_bin_radius_m = 2000   # Maximum service radius per bin
        self.default_bin_radius_m = 1400  # Default bin service radius when no depot info
    
    def create_simple_dynamic_clusters(self, bins_data: List[Dict], depot_data: Optional[Dict] = None) -> Dict:
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
                print("Only 0-1 bins, returning simple clustering")
                return {0: bins_data}
            
            # Calculate dynamic threshold
            print("\nCALCULATING BIN SERVICE RADIUS:")
            bin_radius = self._calculate_dynamic_threshold(bins_data, depot_data)
            print(f"Final bin service radius: {bin_radius:.1f}m")
            
            # Use simple proximity clustering
            print("\nSTARTING PROXIMITY CLUSTERING:")
            clusters = self._cluster_by_proximity(bins_data, bin_radius)
            
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
    
    def _calculate_dynamic_threshold(self, bins_data: List[Dict], depot_data: Optional[Dict]) -> float:
        """
        Calculate dynamic bin service radius using depot-based logic.
        
        Each bin gets a service radius - bins within each other's radius
        get clustered together. Clusters can grow to any size.
        """
        print("BIN RADIUS CALCULATION DEBUG:")
        print(f"  depot_data: {depot_data}")
        print(f"  bins_data length: {len(bins_data)}")
        
        if not depot_data:
            print(f"  No depot data, using default bin radius: {self.default_bin_radius_m}m")
            return self.default_bin_radius_m
        
        # Calculate distance from each bin to depot
        depot_distances = []
        print("  Calculating depot distances:")
        for i, bin_data in enumerate(bins_data):
            dist = calculate_haversine_distance(
                depot_data['lat'], depot_data['lng'],
                bin_data['lat'], bin_data['lng']
            )
            depot_distances.append(dist)
            print(f"    {bin_data['id']} to depot: {dist:.1f}m")
        
        avg_depot_distance = sum(depot_distances) / len(depot_distances)
        print(f"  Average depot distance: {avg_depot_distance:.1f}m")
        
        # More generous approach for this specific data pattern
        # Looking at the actual distances, we need around 1000-1800m to cluster nearby bins
        base_threshold = avg_depot_distance * self.depot_distance_percentage  # Use configured percentage
        print(f"  Base bin radius ({self.depot_distance_percentage*100}% of avg depot): {base_threshold:.1f}m")
        
        # Ensure reasonable bounds - each bin's service radius bounds
        # Minimum: 1000m (capture close bin pairs)
        # Maximum: 2000m (don't merge distant neighborhoods) 
        threshold = max(self.min_bin_radius_m, min(base_threshold, self.max_bin_radius_m))
        
        print(f"  Final bin radius (with bounds {self.min_bin_radius_m}-{self.max_bin_radius_m}m): {threshold:.1f}m")
        print(f"  Bounds applied: min={self.min_bin_radius_m}m, max={self.max_bin_radius_m}m")
        
        return threshold
    
    def _cluster_by_proximity(self, bins_data: List[Dict], bin_radius: float) -> Dict:
        """
        Simple proximity-based clustering logic:
        1. For each bin, find all nearby bins within its service radius
        2. Group them into connected components (clusters)
        3. Merge overlapping clusters automatically
        
        Each bin has a service radius (bin_radius), and bins within each other's
        radius get clustered together. Clusters can grow to any size.
        """
        print("PROXIMITY CLUSTERING DEBUG:")
        print(f"  Bin service radius: {bin_radius:.1f}m")
        print(f"  Processing {len(bins_data)} bins")
        
        # Track which bins belong to which cluster
        bin_to_cluster = {}  # bin_id -> cluster_id
        clusters = {}  # cluster_id -> list of bins
        next_cluster_id = 0
        
        # Log all pairwise distances first
        print("  All pairwise distances:")
        for i in range(len(bins_data)):
            for j in range(i + 1, len(bins_data)):
                dist = calculate_haversine_distance(
                    bins_data[i]['lat'], bins_data[i]['lng'],
                    bins_data[j]['lat'], bins_data[j]['lng']
                )
                within_threshold = "✓" if dist <= bin_radius else "✗"
                print(f"    {bins_data[i]['id']} to {bins_data[j]['id']}: {dist:.1f}m {within_threshold}")
        
        # Process each bin
        print("  Processing bins sequentially:")
        for i, current_bin in enumerate(bins_data):
            current_bin_id = current_bin['id']
            print(f"  \n  Processing bin {current_bin_id} (index {i}):")
            
            # Find all nearby bins within threshold
            nearby_bins = []
            nearby_cluster_ids = set()
            
            print(f"    Finding nearby bins within {bin_radius:.1f}m:")
            for j, other_bin in enumerate(bins_data):
                if i == j:  # Skip self
                    continue
                    
                distance = calculate_haversine_distance(
                    current_bin['lat'], current_bin['lng'],
                    other_bin['lat'], other_bin['lng']
                )
                
                if distance <= bin_radius:
                    nearby_bins.append(other_bin)
                    print(f"      {other_bin['id']}: {distance:.1f}m (NEARBY)")
                    # Check if this nearby bin is already in a cluster
                    if other_bin['id'] in bin_to_cluster:
                        nearby_cluster_ids.add(bin_to_cluster[other_bin['id']])
                        print(f"        └─ Already in cluster {bin_to_cluster[other_bin['id']]}")
                else:
                    print(f"      {other_bin['id']}: {distance:.1f}m (too far)")
            
            print(f"    Found {len(nearby_bins)} nearby bins")
            print(f"    Nearby cluster IDs: {nearby_cluster_ids}")
            
            # Decide what to do with current bin
            if not nearby_cluster_ids:
                # No nearby bins are clustered yet
                if nearby_bins:
                    # Create new cluster with current bin and nearby bins
                    cluster_id = next_cluster_id
                    next_cluster_id += 1
                    print(f"    Creating new cluster {cluster_id} with current bin + nearby bins")
                    
                    # Add current bin to cluster
                    clusters[cluster_id] = [current_bin]
                    bin_to_cluster[current_bin_id] = cluster_id
                    print(f"      Added {current_bin_id} to cluster {cluster_id}")
                    
                    # Add nearby bins to same cluster
                    for nearby_bin in nearby_bins:
                        if nearby_bin['id'] not in bin_to_cluster:
                            clusters[cluster_id].append(nearby_bin)
                            bin_to_cluster[nearby_bin['id']] = cluster_id
                            print(f"      Added {nearby_bin['id']} to cluster {cluster_id}")
                        else:
                            print(f"      {nearby_bin['id']} already clustered, skipping")
                else:
                    # No nearby bins - create single-bin cluster
                    if current_bin_id not in bin_to_cluster:
                        cluster_id = next_cluster_id
                        next_cluster_id += 1
                        clusters[cluster_id] = [current_bin]
                        bin_to_cluster[current_bin_id] = cluster_id
                        print(f"    Created single-bin cluster {cluster_id} for {current_bin_id}")
                        
            elif len(nearby_cluster_ids) == 1:
                # All nearby bins belong to one cluster - join that cluster
                cluster_id = list(nearby_cluster_ids)[0]
                if current_bin_id not in bin_to_cluster:
                    clusters[cluster_id].append(current_bin)
                    bin_to_cluster[current_bin_id] = cluster_id
                    print(f"    Joined existing cluster {cluster_id}")
                else:
                    print(f"    Already in cluster {bin_to_cluster[current_bin_id]}")
                    
            else:
                # Multiple nearby clusters - need to merge them
                cluster_id = min(nearby_cluster_ids)  # Keep smallest ID
                print(f"    Merging multiple clusters {nearby_cluster_ids} into {cluster_id}")
                
                # Add current bin to the main cluster
                if current_bin_id not in bin_to_cluster:
                    clusters[cluster_id].append(current_bin)
                    bin_to_cluster[current_bin_id] = cluster_id
                    print(f"      Added {current_bin_id} to main cluster {cluster_id}")
                
                # Merge all other clusters into the main one
                for other_cluster_id in nearby_cluster_ids:
                    if other_cluster_id != cluster_id and other_cluster_id in clusters:
                        print(f"      Merging cluster {other_cluster_id} into {cluster_id}")
                        # Move all bins from other cluster to main cluster
                        for bin_to_move in clusters[other_cluster_id]:
                            clusters[cluster_id].append(bin_to_move)
                            bin_to_cluster[bin_to_move['id']] = cluster_id
                            print(f"        Moved {bin_to_move['id']} from cluster {other_cluster_id} to {cluster_id}")
                        # Remove the merged cluster
                        del clusters[other_cluster_id]
                        print(f"        Deleted empty cluster {other_cluster_id}")
        
        # Clean up: remove any duplicate bins that might have been added
        print("  Cleaning up duplicate bins:")
        for cluster_id in clusters:
            # Remove duplicates while preserving order
            seen_ids = set()
            unique_bins = []
            original_count = len(clusters[cluster_id])
            for bin_data in clusters[cluster_id]:
                if bin_data['id'] not in seen_ids:
                    unique_bins.append(bin_data)
                    seen_ids.add(bin_data['id'])
            clusters[cluster_id] = unique_bins
            if len(unique_bins) != original_count:
                print(f"    Cluster {cluster_id}: removed {original_count - len(unique_bins)} duplicates")
        
        # Log final cluster statistics
        cluster_sizes = [len(cluster) for cluster in clusters.values()]
        print(f"  Final clustering results: {len(clusters)} clusters, sizes: {cluster_sizes}")
        
        # Log detailed cluster info
        for cluster_id, cluster_bins in clusters.items():
            bin_ids = [b['id'] for b in cluster_bins]
            print(f"    Final Cluster {cluster_id}: {bin_ids}")
        
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
        bin_radius = self._calculate_dynamic_threshold(bins_data, depot_data)
        
        depot_distances = []
        if depot_data:
            for bin_data in bins_data:
                dist = calculate_haversine_distance(
                    depot_data['lat'], depot_data['lng'],
                    bin_data['lat'], bin_data['lng']
                )
                depot_distances.append(dist)
        
        return {
            'approach': 'Proximity-Based Clustering',
            'dynamic_bin_radius_m': bin_radius,
            'depot_distance_percentage': self.depot_distance_percentage * 100,
            'min_bin_radius_m': self.min_bin_radius_m,
            'max_bin_radius_m': self.max_bin_radius_m,
            'depot_distances': {
                'min_m': min(depot_distances) if depot_distances else None,
                'max_m': max(depot_distances) if depot_distances else None,
                'avg_m': sum(depot_distances) / len(depot_distances) if depot_distances else None
            },
            'has_depot_data': depot_data is not None
        }
    
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