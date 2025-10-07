#!/usr/bin/env python3
"""
Fixed clustering service that creates geographically logical clusters.
"""

import numpy as np
from typing import Dict, List, Optional
from config.settings import Config
from services.external.osrm_service import OSRMService
from services.clustering_service import ClusteringService
from utils.distance import calculate_haversine_distance
import logging

logger = logging.getLogger(__name__)

class FixedClusteringService(ClusteringService):
    """
    Fixed clustering service that creates geographically logical clusters.
    
    Key fixes:
    1. Uses appropriate distance thresholds based on actual data analysis
    2. Prevents over-splitting of reasonable clusters  
    3. Creates meaningful geographical groupings
    4. Maintains cluster quality without excessive fragmentation
    
    Inherits from ClusteringService for full compatibility.
    """
    
    def __init__(self, config: Optional[Config] = None, osrm_service: Optional[OSRMService] = None):
        # Initialize parent class
        super().__init__(config, osrm_service)
        
        # Override with fixed clustering parameters based on actual data analysis
        self.optimal_distance_threshold = 1300  # Meters - creates logical geographical clusters
        self.min_cluster_size = 1  # Allow single-bin clusters when needed
        self.max_cluster_size = 5  # Reasonable maximum for routing efficiency
        
        # Quality thresholds - more realistic based on actual distances
        self.max_internal_distance = 1800  # Allow larger clusters for geographical coherence
        self.reasonable_cluster_diameter = 1500  # Clusters up to 1.5km are reasonable
    
    def create_geographical_clusters(self, bins_data: List[Dict], depot_data: Optional[Dict] = None) -> Dict:
        """
        Create clusters that make geographical sense.
        
        Args:
            bins_data: List of bin dictionaries with lat, lng, etc.
            depot_data: Depot dictionary with lat, lng (optional)
            
        Returns:
            Dictionary of clusters with cluster_id as key and list of bins as value
        """
        try:
            logger.info(f"Creating geographical clusters for {len(bins_data)} bins")
            
            if len(bins_data) <= 1:
                return {0: bins_data}
            
            # Use connectivity-based clustering with appropriate threshold
            clusters = self._connectivity_based_clustering(bins_data, self.optimal_distance_threshold)
            
            # Validate cluster quality but don't over-split
            clusters = self._validate_and_improve_clusters(clusters, bins_data)
            
            logger.info(f"Created {len(clusters)} geographical clusters")
            return clusters
            
        except Exception as e:
            logger.error(f"Error creating geographical clusters: {e}")
            return self._fallback_clustering(bins_data)
    
    def _connectivity_based_clustering(self, bins_data: List[Dict], threshold: float) -> Dict:
        """
        Create clusters based on connectivity using breadth-first search.
        This ensures bins are grouped only if they form connected components.
        """
        n = len(bins_data)
        distance_matrix = self._create_distance_matrix(bins_data)
        
        clusters = {}
        visited = [False] * n
        cluster_id = 0
        
        for i in range(n):
            if visited[i]:
                continue
            
            # Start new cluster using BFS
            cluster_indices = []
            queue = [i]
            visited[i] = True
            
            while queue:
                current = queue.pop(0)
                cluster_indices.append(current)
                
                # Find all unvisited neighbors within threshold
                for j in range(n):
                    if not visited[j] and distance_matrix[current][j] <= threshold:
                        visited[j] = True
                        queue.append(j)
            
            # Convert indices to bin data
            clusters[cluster_id] = [bins_data[idx] for idx in cluster_indices]
            cluster_id += 1
        
        return clusters
    
    def _validate_and_improve_clusters(self, clusters: Dict, bins_data: List[Dict]) -> Dict:
        """
        Validate cluster quality but avoid over-splitting geographical clusters.
        """
        try:
            validated_clusters = {}
            
            for cluster_id, cluster_bins in clusters.items():
                if len(cluster_bins) <= 1:
                    # Single bin clusters are always valid
                    validated_clusters[cluster_id] = cluster_bins
                    continue
                
                # Check cluster quality - but be more permissive for geographical coherence
                max_internal_dist = self._get_max_internal_distance(cluster_bins)
                cluster_size = len(cluster_bins)
                
                # Only split if cluster is really problematic
                if cluster_size <= self.max_cluster_size and max_internal_dist <= self.max_internal_distance:
                    # Cluster is acceptable
                    validated_clusters[cluster_id] = cluster_bins
                    logger.info(f"Accepted cluster {cluster_id} with {cluster_size} bins, max distance: {max_internal_dist:.0f}m")
                else:
                    # Cluster needs splitting - but only if it's really too large
                    if cluster_size > self.max_cluster_size:
                        logger.info(f"Splitting cluster {cluster_id} due to size ({cluster_size} > {self.max_cluster_size})")
                        sub_clusters = self._split_cluster_by_size(cluster_bins)
                    elif max_internal_dist > self.max_internal_distance:
                        logger.info(f"Splitting cluster {cluster_id} due to distance ({max_internal_dist:.0f}m > {self.max_internal_distance}m)")
                        sub_clusters = self._split_cluster_by_proximity(cluster_bins)
                    else:
                        sub_clusters = [cluster_bins]
                    
                    for sub_cluster in sub_clusters:
                        validated_clusters[len(validated_clusters)] = sub_cluster
            
            return validated_clusters
            
        except Exception as e:
            logger.error(f"Error validating clusters: {e}")
            return clusters
    
    def _split_cluster_by_size(self, cluster_bins: List[Dict]) -> List[List[Dict]]:
        """
        Split a cluster that's too large into smaller sub-clusters.
        """
        try:
            if len(cluster_bins) <= self.max_cluster_size:
                return [cluster_bins]
            
            # Sort bins by some criteria (e.g., fill level, lat, lng) to maintain geographical coherence
            sorted_bins = sorted(cluster_bins, key=lambda b: (b['lat'], b['lng']))
            
            # Split into chunks of max_cluster_size
            sub_clusters = []
            for i in range(0, len(sorted_bins), self.max_cluster_size):
                sub_cluster = sorted_bins[i:i + self.max_cluster_size]
                sub_clusters.append(sub_cluster)
            
            return sub_clusters
            
        except Exception as e:
            logger.error(f"Error splitting cluster by size: {e}")
            return [cluster_bins]
    
    def _split_cluster_by_proximity(self, cluster_bins: List[Dict]) -> List[List[Dict]]:
        """
        Split a cluster into smaller sub-clusters based on proximity.
        Use a smaller threshold than the original clustering.
        """
        try:
            if len(cluster_bins) <= 2:
                return [cluster_bins]
            
            # Use smaller threshold for splitting (70% of original)
            smaller_threshold = self.optimal_distance_threshold * 0.7
            sub_clusters_dict = self._connectivity_based_clustering(cluster_bins, smaller_threshold)
            
            return list(sub_clusters_dict.values())
            
        except Exception as e:
            logger.error(f"Error splitting cluster by proximity: {e}")
            return [cluster_bins]
    
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
    
    def get_cluster_analysis(self, clusters: Dict, depot_data: Optional[Dict] = None) -> Dict:
        """
        Get comprehensive analysis of clusters including quality metrics.
        """
        analysis = {
            'total_clusters': len(clusters),
            'total_bins': sum(len(cluster) for cluster in clusters.values()),
            'clusters': {},
            'overall_metrics': {}
        }
        
        total_bins = 0
        total_waste = 0.0
        cluster_sizes = []
        depot_distances = []
        
        for cluster_id, cluster_bins in clusters.items():
            cluster_info = self._analyze_single_cluster(cluster_bins, depot_data)
            analysis['clusters'][cluster_id] = cluster_info
            
            # Aggregate metrics
            total_bins += len(cluster_bins)
            total_waste += cluster_info['total_waste']
            cluster_sizes.append(len(cluster_bins))
            if cluster_info['center_to_depot_distance']:
                depot_distances.append(cluster_info['center_to_depot_distance'])
        
        # Calculate overall metrics
        analysis['overall_metrics'] = {
            'average_cluster_size': total_bins / len(clusters) if clusters else 0,
            'min_cluster_size': min(cluster_sizes) if cluster_sizes else 0,
            'max_cluster_size': max(cluster_sizes) if cluster_sizes else 0,
            'total_waste_liters': total_waste,
            'average_depot_distance': sum(depot_distances) / len(depot_distances) if depot_distances else None,
            'clustering_efficiency': self._calculate_clustering_efficiency(clusters, depot_data)
        }
        
        return analysis
    
    def _analyze_single_cluster(self, cluster_bins: List[Dict], depot_data: Optional[Dict] = None) -> Dict:
        """Analyze a single cluster and return metrics."""
        if not cluster_bins:
            return {}
        
        # Calculate cluster center
        center_lat = sum(bin_data['lat'] for bin_data in cluster_bins) / len(cluster_bins)
        center_lng = sum(bin_data['lng'] for bin_data in cluster_bins) / len(cluster_bins)
        
        # Calculate distances
        center_to_depot_distance = None
        if depot_data:
            center_to_depot_distance = calculate_haversine_distance(
                depot_data['lat'], depot_data['lng'], center_lat, center_lng
            )
        
        # Internal cluster metrics
        max_internal_distance = self._get_max_internal_distance(cluster_bins)
        avg_internal_distance = self._get_avg_internal_distance(cluster_bins)
        
        # Waste metrics
        total_waste = sum((bin_data['fillLevel'] / 100) * bin_data['capacity'] 
                         for bin_data in cluster_bins)
        
        # Quality rating - more lenient for geographical clusters
        quality_rating = self._rate_cluster_quality(
            len(cluster_bins), max_internal_distance, center_to_depot_distance
        )
        
        return {
            'bin_count': len(cluster_bins),
            'bin_ids': [bin_data['id'] for bin_data in cluster_bins],
            'center_lat': center_lat,
            'center_lng': center_lng,
            'center_to_depot_distance': center_to_depot_distance,
            'max_internal_distance': max_internal_distance,
            'avg_internal_distance': avg_internal_distance,
            'total_waste': total_waste,
            'quality_rating': quality_rating,
            'bins': cluster_bins
        }
    
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
    
    def _rate_cluster_quality(self, bin_count: int, max_internal_dist: float, 
                            depot_distance: Optional[float]) -> str:
        """Rate the quality of a cluster - more lenient for geographical clusters."""
        score = 0
        
        # Size score (2-5 bins is good for geographical clusters)
        if 2 <= bin_count <= 4:
            score += 35
        elif bin_count == 1:
            score += 25  # Single bins are acceptable
        elif bin_count == 5:
            score += 30  # 5 bins is still good
        else:
            score += 15  # Larger clusters are less ideal but not terrible
        
        # Internal distance score - more lenient for geographical clustering
        if max_internal_dist <= 800:
            score += 35
        elif max_internal_dist <= 1200:
            score += 30
        elif max_internal_dist <= 1600:
            score += 25
        elif max_internal_dist <= 2000:
            score += 20
        else:
            score += 10
        
        # Depot distance score (if available)
        if depot_distance is not None:
            if depot_distance <= 1500:
                score += 30  # Close to depot
            elif depot_distance <= 2500:
                score += 25
            elif depot_distance <= 3500:
                score += 20
            else:
                score += 15
        else:
            score += 20  # Neutral score if no depot data
        
        # Convert to rating
        if score >= 85:
            return 'excellent'
        elif score >= 70:
            return 'good'
        elif score >= 55:
            return 'fair'
        else:
            return 'poor'
    
    def _calculate_clustering_efficiency(self, clusters: Dict, depot_data: Optional[Dict] = None) -> float:
        """Calculate overall clustering efficiency score (0-1)."""
        try:
            if not clusters:
                return 0.0
            
            total_score = 0.0
            total_bins = 0
            
            for cluster_bins in clusters.values():
                # Cluster size efficiency (prefer 2-5 bins per cluster)
                size_efficiency = self._get_size_efficiency(len(cluster_bins))
                
                # Internal distance efficiency - more lenient
                max_internal = self._get_max_internal_distance(cluster_bins)
                distance_efficiency = max(0, 1 - (max_internal / 2000))  # Normalize to 2km
                
                # Depot efficiency (if available)
                depot_efficiency = 0.5  # Neutral if no depot
                if depot_data and cluster_bins:
                    center_lat = sum(b['lat'] for b in cluster_bins) / len(cluster_bins)
                    center_lng = sum(b['lng'] for b in cluster_bins) / len(cluster_bins)
                    depot_dist = calculate_haversine_distance(
                        depot_data['lat'], depot_data['lng'], center_lat, center_lng
                    )
                    depot_efficiency = max(0, 1 - (depot_dist / 4000))  # Normalize to 4km
                
                # Weighted cluster score
                cluster_score = (size_efficiency * 0.3 + 
                               distance_efficiency * 0.4 + 
                               depot_efficiency * 0.3)
                
                total_score += cluster_score * len(cluster_bins)
                total_bins += len(cluster_bins)
            
            return total_score / total_bins if total_bins > 0 else 0.0
            
        except Exception as e:
            logger.error(f"Error calculating clustering efficiency: {e}")
            return 0.0
    
    def _get_size_efficiency(self, cluster_size: int) -> float:
        """Get efficiency score for cluster size - more lenient."""
        if cluster_size == 1:
            return 0.7  # Single bins are okay
        elif 2 <= cluster_size <= 4:
            return 1.0  # Optimal size
        elif cluster_size == 5:
            return 0.9  # Still very good
        elif cluster_size == 6:
            return 0.7  # Acceptable
        else:
            return 0.5  # Large but not terrible
    
    def _fallback_clustering(self, bins_data: List[Dict]) -> Dict:
        """Simple fallback clustering when advanced methods fail."""
        logger.warning("Using fallback clustering - each bin becomes its own cluster")
        clusters = {}
        for i, bin_data in enumerate(bins_data):
            clusters[i] = [bin_data]
        return clusters

    # Override main clustering methods to use fixed logic
    def create_adaptive_clusters(self, bins_data: List[Dict]) -> Dict:
        """Override parent method to use fixed geographical clustering."""
        return self.create_geographical_clusters(bins_data)
    
    def create_clusters_dbscan(self, bins_data: List[Dict], distance_matrix: Optional[np.ndarray] = None,
                              eps_meters: Optional[int] = None, min_samples: Optional[int] = None) -> Dict:
        """Override parent method to use fixed geographical clustering instead of DBSCAN."""
        logger.info("Using fixed geographical clustering instead of DBSCAN")
        return self.create_geographical_clusters(bins_data)
    
    def get_cluster_info(self, clusters: Dict) -> Dict:
        """Override parent method to provide cluster info in expected format."""
        analysis = self.get_cluster_analysis(clusters)
        
        # Convert to expected format with quality_metrics field
        cluster_info = {}
        for cluster_id, cluster_data in analysis['clusters'].items():
            # Create quality_metrics field in the format expected by agent service
            quality_metrics = {
                'quality_rating': cluster_data.get('quality_rating', 'unknown'),
                'compactness_score': 1.0 - (cluster_data.get('max_internal_distance', 0) / 2000),  # Normalize
                'collection_efficiency': self._calculate_simple_efficiency(cluster_data),
                'diameter_meters': cluster_data.get('max_internal_distance', 0),
                'avg_distance_meters': cluster_data.get('avg_internal_distance', 0)
            }
            
            cluster_info[cluster_id] = {
                'bin_count': cluster_data['bin_count'],
                'bin_ids': cluster_data['bin_ids'],
                'center_lat': cluster_data['center_lat'],
                'center_lng': cluster_data['center_lng'],
                'total_waste': cluster_data['total_waste'],
                'bins': cluster_data['bins'],
                'quality_metrics': quality_metrics
            }
        
        return cluster_info
    
    def _calculate_simple_efficiency(self, cluster_data: Dict) -> float:
        """Calculate a simple efficiency score for compatibility."""
        bin_count = cluster_data.get('bin_count', 1)
        max_dist = cluster_data.get('max_internal_distance', 0)
        
        # Simple efficiency based on size and compactness
        size_efficiency = 1.0 if 2 <= bin_count <= 4 else 0.7
        distance_efficiency = max(0, 1.0 - (max_dist / 2000))  # Normalize to 2km
        
        return (size_efficiency + distance_efficiency) / 2