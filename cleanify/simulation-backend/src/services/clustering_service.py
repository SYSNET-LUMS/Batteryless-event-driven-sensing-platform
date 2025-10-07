#!/usr/bin/env python3
"""
Simple dynamic clustering service based on depot distance.
Much simpler and more intuitive approach.
"""

import numpy as np
from typing import Dict, List, Optional
from config.settings import Config
from services.external.osrm_service import OSRMService
from utils.distance import calculate_haversine_distance
from sklearn.cluster import DBSCAN
import logging

logger = logging.getLogger(__name__)

class ClusteringService:
    """
    Simple dynamic clustering service that:
    1. Calculates dynamic distance threshold based on depot proximity
    2. Uses DBSCAN to group nearby bins
    3. Simple, intuitive, and effective
    """
    
    def __init__(self, config: Optional[Config] = None, osrm_service: Optional[OSRMService] = None):
        # Store optional services
        self.config = config or Config()
        self.osrm_service = osrm_service
        
        # Simple parameters
        self.depot_distance_percentage = 0.15  # 15% of depot distance
        self.min_threshold_m = 200  # Minimum clustering distance (200m)
        self.max_threshold_m = 5000  # Maximum clustering distance (5km)
        self.default_threshold_m = 800  # Default when no depot info
        self.min_samples = 1  # Allow single-bin clusters
    
    def create_simple_dynamic_clusters(self, bins_data: List[Dict], depot_data: Optional[Dict] = None) -> Dict:
        """
        Create clusters using simple dynamic distance based on depot proximity.
        
        Args:
            bins_data: List of bin dictionaries with lat, lng, etc.
            depot_data: Depot dictionary with lat, lng (optional)
            
        Returns:
            Dictionary of clusters with cluster_id as key and list of bins as value
        """
        try:
            logger.info(f"Creating simple dynamic clusters for {len(bins_data)} bins")
            
            if len(bins_data) <= 1:
                return {0: bins_data}
            
            # Calculate dynamic threshold based on depot distance
            threshold = self._calculate_dynamic_threshold(bins_data, depot_data)
            logger.info(f"Using dynamic threshold: {threshold:.0f}m")
            
            # Create distance matrix
            distance_matrix = self._create_distance_matrix(bins_data)
            
            # Use DBSCAN with dynamic threshold
            clusters = self._cluster_with_dbscan(bins_data, distance_matrix, threshold)
            
            logger.info(f"Created {len(clusters)} clusters using simple dynamic approach")
            return clusters
            
        except Exception as e:
            logger.error(f"Error creating simple dynamic clusters: {e}")
            return self._fallback_clustering(bins_data)
    
    def _calculate_dynamic_threshold(self, bins_data: List[Dict], depot_data: Optional[Dict]) -> float:
        """
        Calculate dynamic clustering threshold based on depot distance and data characteristics.
        
        Enhanced logic:
        1. If depot provided: Use percentage of average depot distance
        2. Consider the geographical spread of bins 
        3. Adaptive percentage based on scale
        4. Apply min/max limits
        """
        if not depot_data:
            logger.info(f"No depot data, using default threshold: {self.default_threshold_m}m")
            return self.default_threshold_m
        
        # Calculate distance from each bin to depot
        depot_distances = []
        for bin_data in bins_data:
            dist = calculate_haversine_distance(
                depot_data['lat'], depot_data['lng'],
                bin_data['lat'], bin_data['lng']
            )
            depot_distances.append(dist)
        
        # Calculate geographical characteristics
        avg_depot_distance = sum(depot_distances) / len(depot_distances)
        
        # Calculate the spread of bins (how far apart they are from each other)
        bin_distances = []
        for i in range(len(bins_data)):
            for j in range(i + 1, len(bins_data)):
                dist = calculate_haversine_distance(
                    bins_data[i]['lat'], bins_data[i]['lng'],
                    bins_data[j]['lat'], bins_data[j]['lng']
                )
                bin_distances.append(dist)
        
        if bin_distances:
            min_bin_distance = min(bin_distances)
            median_bin_distance = sorted(bin_distances)[len(bin_distances) // 2]
            max_bin_distance = max(bin_distances)
        else:
            min_bin_distance = median_bin_distance = max_bin_distance = 0
        
        # Adaptive percentage based on scale
        # For smaller depot distances (local scale): use larger percentage
        # For larger depot distances (wide scale): use smaller percentage
        if avg_depot_distance < 2000:  # Local scale (< 2km from depot)
            adaptive_percentage = 0.20  # 20% for local
        elif avg_depot_distance < 5000:  # Area scale (2-5km from depot)
            adaptive_percentage = 0.25  # 25% for area
        else:  # Large scale (> 5km from depot)
            adaptive_percentage = 0.30  # 30% for large scale
        
        # Base threshold from depot distance
        depot_based_threshold = avg_depot_distance * adaptive_percentage
        
        # Alternative threshold based on bin distances (for connectivity)
        # Use median distance between bins as reference
        if median_bin_distance > 0:
            bin_based_threshold = median_bin_distance * 0.6  # 60% of median distance
        else:
            bin_based_threshold = depot_based_threshold
        
        # Choose the larger of the two approaches (more inclusive clustering)
        dynamic_threshold = max(depot_based_threshold, bin_based_threshold)
        
        # Apply bounds
        threshold = max(self.min_threshold_m, min(dynamic_threshold, self.max_threshold_m))
        
        logger.info(f"Scale analysis: depot_avg={avg_depot_distance:.0f}m, "
                   f"bin_median={median_bin_distance:.0f}m")
        logger.info(f"Thresholds: depot_based={depot_based_threshold:.0f}m, "
                   f"bin_based={bin_based_threshold:.0f}m, final={threshold:.0f}m")
        
        return threshold
    
    def _cluster_with_dbscan(self, bins_data: List[Dict], distance_matrix: np.ndarray, threshold: float) -> Dict:
        """
        Use DBSCAN to cluster bins with the dynamic threshold.
        
        Simple approach:
        1. DBSCAN finds connected components within threshold distance
        2. Each connected component becomes a cluster
        3. Noise points become individual clusters
        """
        # Apply DBSCAN
        clustering = DBSCAN(eps=threshold, min_samples=self.min_samples, metric='precomputed')
        cluster_labels = clustering.fit_predict(distance_matrix)
        
        # Convert DBSCAN results to our cluster format
        clusters = {}
        noise_bins = []
        
        for i, label in enumerate(cluster_labels):
            if label == -1:
                # Noise point - will become individual cluster
                noise_bins.append(bins_data[i])
            else:
                # Regular cluster
                if label not in clusters:
                    clusters[label] = []
                clusters[label].append(bins_data[i])
        
        # Add noise bins as individual clusters
        next_cluster_id = max(clusters.keys()) + 1 if clusters else 0
        for noise_bin in noise_bins:
            clusters[next_cluster_id] = [noise_bin]
            next_cluster_id += 1
        
        # Log cluster statistics
        cluster_sizes = [len(cluster) for cluster in clusters.values()]
        logger.info(f"DBSCAN results: {len(clusters)} clusters, "
                   f"sizes: min={min(cluster_sizes)}, max={max(cluster_sizes)}, "
                   f"avg={sum(cluster_sizes)/len(cluster_sizes):.1f}")
        
        return clusters
    
    def _create_distance_matrix(self, bins_data: List[Dict]) -> np.ndarray:
        """Create distance matrix between all bins using Haversine distance."""
        n = len(bins_data)
        distance_matrix = np.zeros((n, n))
        
        for i in range(n):
            for j in range(n):
                if i != j:
                    distance = calculate_haversine_distance(
                        bins_data[i]['lat'], bins_data[i]['lng'],
                        bins_data[j]['lat'], bins_data[j]['lng']
                    )
                    distance_matrix[i][j] = distance
        
        return distance_matrix
    
    def get_clustering_info(self, bins_data: List[Dict], depot_data: Optional[Dict] = None) -> Dict:
        """Get information about the clustering approach for this data."""
        threshold = self._calculate_dynamic_threshold(bins_data, depot_data)
        
        depot_distances = []
        if depot_data:
            for bin_data in bins_data:
                dist = calculate_haversine_distance(
                    depot_data['lat'], depot_data['lng'],
                    bin_data['lat'], bin_data['lng']
                )
                depot_distances.append(dist)
        
        return {
            'approach': 'Simple Dynamic Clustering',
            'dynamic_threshold_m': threshold,
            'depot_distance_percentage': self.depot_distance_percentage * 100,
            'min_threshold_m': self.min_threshold_m,
            'max_threshold_m': self.max_threshold_m,
            'depot_distances': {
                'min_m': min(depot_distances) if depot_distances else None,
                'max_m': max(depot_distances) if depot_distances else None,
                'avg_m': sum(depot_distances) / len(depot_distances) if depot_distances else None
            },
            'has_depot_data': depot_data is not None
        }
    
    def _fallback_clustering(self, bins_data: List[Dict]) -> Dict:
        """Simple fallback - each bin becomes its own cluster."""
        logger.warning("Using fallback clustering - each bin becomes its own cluster")
        clusters = {}
        for i, bin_data in enumerate(bins_data):
            clusters[i] = [bin_data]
        return clusters

    # Override main clustering methods
    def create_adaptive_clusters(self, bins_data: List[Dict]) -> Dict:
        """Override parent method to use simple dynamic clustering."""
        # Try to find depot data from bins or use None
        depot_data = None
        # For now, use without depot data - can be enhanced later
        return self.create_simple_dynamic_clusters(bins_data, depot_data)
    
    def create_clusters_dbscan(self, bins_data: List[Dict], distance_matrix: Optional[np.ndarray] = None,
                              eps_meters: Optional[int] = None, min_samples: Optional[int] = None) -> Dict:
        """Override parent method to use simple dynamic clustering."""
        logger.info("Using simple dynamic clustering instead of fixed DBSCAN")
        return self.create_simple_dynamic_clusters(bins_data, None)
    
    def get_cluster_info(self, clusters: Dict) -> Dict:
        """Override parent method to provide cluster info in expected format."""
        cluster_info = {}
        
        for cluster_id, cluster_bins in clusters.items():
            if not cluster_bins:
                continue
                
            # Calculate cluster center
            center_lat = sum(bin_data['lat'] for bin_data in cluster_bins) / len(cluster_bins)
            center_lng = sum(bin_data['lng'] for bin_data in cluster_bins) / len(cluster_bins)
            
            # Calculate distances
            max_internal_distance = self._get_max_internal_distance(cluster_bins)
            avg_internal_distance = self._get_avg_internal_distance(cluster_bins)
            
            # Calculate waste metrics
            total_waste = sum((bin_data['fillLevel'] / 100) * bin_data['capacity'] 
                             for bin_data in cluster_bins)
            
            # Create quality_metrics field
            quality_metrics = {
                'quality_rating': self._rate_cluster_quality(len(cluster_bins), max_internal_distance),
                'compactness_score': self._calculate_compactness(max_internal_distance),
                'collection_efficiency': self._calculate_efficiency(cluster_bins),
                'diameter_meters': max_internal_distance,
                'avg_distance_meters': avg_internal_distance
            }
            
            cluster_info[cluster_id] = {
                'bin_count': len(cluster_bins),
                'bin_ids': [bin_data['id'] for bin_data in cluster_bins],
                'center_lat': center_lat,
                'center_lng': center_lng,
                'total_waste': total_waste,
                'bins': cluster_bins,
                'quality_metrics': quality_metrics
            }
        
        return cluster_info
    
    def _get_max_internal_distance(self, cluster_bins: List[Dict]) -> float:
        """Calculate maximum internal distance within a cluster."""
        if len(cluster_bins) <= 1:
            return 0.0
        
        max_dist = 0.0
        for i in range(len(cluster_bins)):
            for j in range(i + 1, len(cluster_bins)):
                dist = calculate_haversine_distance(
                    cluster_bins[i]['lat'], cluster_bins[i]['lng'],
                    cluster_bins[j]['lat'], cluster_bins[j]['lng']
                )
                max_dist = max(max_dist, dist)
        
        return max_dist
    
    def _get_avg_internal_distance(self, cluster_bins: List[Dict]) -> float:
        """Calculate average internal distance within a cluster."""
        if len(cluster_bins) <= 1:
            return 0.0
        
        distances = []
        for i in range(len(cluster_bins)):
            for j in range(i + 1, len(cluster_bins)):
                dist = calculate_haversine_distance(
                    cluster_bins[i]['lat'], cluster_bins[i]['lng'],
                    cluster_bins[j]['lat'], cluster_bins[j]['lng']
                )
                distances.append(dist)
        
        return sum(distances) / len(distances) if distances else 0.0
    
    def _calculate_compactness(self, max_internal_distance: float) -> float:
        """Calculate compactness score based on maximum internal distance."""
        # Simple compactness: closer bins = higher score
        return max(0.0, 1.0 - (max_internal_distance / 3000))  # Normalize to 3km
    
    def _calculate_efficiency(self, cluster_bins: List[Dict]) -> float:
        """Calculate collection efficiency."""
        bin_count = len(cluster_bins)
        
        # Size efficiency
        if 2 <= bin_count <= 5:
            size_efficiency = 1.0
        elif bin_count == 1:
            size_efficiency = 0.8
        else:
            size_efficiency = max(0.5, 1.0 - (bin_count - 5) * 0.1)
        
        # Waste density efficiency
        total_waste = sum((b['fillLevel'] / 100) * b['capacity'] for b in cluster_bins)
        avg_waste_per_bin = total_waste / bin_count if bin_count > 0 else 0
        waste_efficiency = min(1.0, avg_waste_per_bin / 400)  # Normalize to 400L
        
        return (size_efficiency + waste_efficiency) / 2
    
    def _rate_cluster_quality(self, bin_count: int, max_internal_dist: float) -> str:
        """Rate the quality of a cluster."""
        score = 0
        
        # Size score
        if 2 <= bin_count <= 4:
            score += 40
        elif bin_count == 1:
            score += 30
        elif bin_count <= 6:
            score += 25
        else:
            score += 15
        
        # Distance score
        if max_internal_dist <= 500:
            score += 40
        elif max_internal_dist <= 1000:
            score += 30
        elif max_internal_dist <= 2000:
            score += 20
        else:
            score += 10
        
        # Convert to rating
        if score >= 70:
            return 'excellent'
        elif score >= 55:
            return 'good'
        elif score >= 40:
            return 'fair'
        else:
            return 'poor'