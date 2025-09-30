import numpy as np
from typing import Dict, List, Tuple, Optional, Union
from config.settings import Config
from services.external.osrm_service import OSRMService
from utils.distance import calculate_haversine_distance
import logging

logger = logging.getLogger(__name__)

class ImprovedClusteringService:
    """
    Enhanced waste collection bin clustering service that creates logical clusters 
    based on geographical proximity and distance from depot.
    
    This improved version addresses over-clustering issues by:
    1. Using depot-aware clustering that considers distance from depot
    2. Implementing connectivity-based clustering for natural groupings
    3. Using optimal distance thresholds based on data analysis
    4. Providing quality metrics for cluster evaluation
    """
    
    def __init__(self, config: Optional[Config] = None, osrm_service: Optional[OSRMService] = None):
        self.config = config or Config()
        self.osrm_service = osrm_service or OSRMService()
        
        # Improved clustering parameters based on analysis
        self.optimal_distance_threshold = 600  # Meters - creates 3 logical clusters
        self.min_cluster_size = 1  # Allow single-bin clusters for efficiency
        self.max_cluster_size = 6  # Prevent overly large clusters
        self.depot_weight = 0.3  # Weight for depot distance consideration
        
        # Quality thresholds
        self.max_internal_distance = 700  # Maximum distance within cluster
        self.depot_proximity_bonus = 200  # Bonus for clusters close to depot
    
    def create_optimal_clusters(self, bins_data: List[Dict], depot_data: Optional[Dict] = None) -> Dict:
        """
        Create optimal clusters using improved connectivity-based algorithm.
        
        Args:
            bins_data: List of bin dictionaries with lat, lng, etc.
            depot_data: Depot dictionary with lat, lng (optional)
            
        Returns:
            Dictionary of clusters with cluster_id as key and list of bins as value
        """
        try:
            logger.info(f"Creating optimal clusters for {len(bins_data)} bins")
            
            if len(bins_data) <= 1:
                return {0: bins_data}
            
            # Use connectivity-based clustering for natural groupings
            clusters = self._connectivity_based_clustering(bins_data, self.optimal_distance_threshold)
            
            # Post-process clusters considering depot if available
            if depot_data:
                clusters = self._optimize_clusters_with_depot(clusters, bins_data, depot_data)
            
            # Validate and improve cluster quality
            clusters = self._validate_cluster_quality(clusters, bins_data)
            
            logger.info(f"Created {len(clusters)} optimal clusters")
            return clusters
            
        except Exception as e:
            logger.error(f"Error creating optimal clusters: {e}")
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
    
    def _optimize_clusters_with_depot(self, clusters: Dict, bins_data: List[Dict], 
                                    depot_data: Dict) -> Dict:
        """
        Optimize clusters considering depot location and routing efficiency.
        """
        try:
            optimized_clusters = {}
            
            for cluster_id, cluster_bins in clusters.items():
                # Check if cluster should be split based on depot considerations
                if len(cluster_bins) > self.max_cluster_size:
                    # Split large clusters
                    sub_clusters = self._split_cluster_by_depot_distance(cluster_bins, depot_data)
                    for i, sub_cluster in enumerate(sub_clusters):
                        optimized_clusters[len(optimized_clusters)] = sub_cluster
                else:
                    optimized_clusters[cluster_id] = cluster_bins
            
            return optimized_clusters
            
        except Exception as e:
            logger.warning(f"Error optimizing clusters with depot: {e}")
            return clusters
    
    def _split_cluster_by_depot_distance(self, cluster_bins: List[Dict], 
                                       depot_data: Dict) -> List[List[Dict]]:
        """
        Split a large cluster based on depot distance zones.
        """
        try:
            # Calculate depot distances for cluster bins
            bin_depot_distances = []
            for bin_data in cluster_bins:
                dist = calculate_haversine_distance(
                    depot_data['lat'], depot_data['lng'],
                    bin_data['lat'], bin_data['lng']
                )
                bin_depot_distances.append((bin_data, dist))
            
            # Sort by depot distance
            bin_depot_distances.sort(key=lambda x: x[1])
            
            # Split into sub-clusters of reasonable size
            sub_clusters = []
            current_cluster = []
            
            for bin_data, depot_dist in bin_depot_distances:
                current_cluster.append(bin_data)
                
                # Create new sub-cluster when reaching max size
                if len(current_cluster) >= self.max_cluster_size:
                    sub_clusters.append(current_cluster)
                    current_cluster = []
            
            # Add remaining bins
            if current_cluster:
                sub_clusters.append(current_cluster)
            
            return sub_clusters
            
        except Exception as e:
            logger.error(f"Error splitting cluster: {e}")
            return [cluster_bins]
    
    def _validate_cluster_quality(self, clusters: Dict, bins_data: List[Dict]) -> Dict:
        """
        Validate and improve cluster quality by checking internal distances.
        """
        try:
            validated_clusters = {}
            
            for cluster_id, cluster_bins in clusters.items():
                if len(cluster_bins) <= 1:
                    # Single bin clusters are always valid
                    validated_clusters[cluster_id] = cluster_bins
                    continue
                
                # Check internal cluster distances
                max_internal_dist = self._get_max_internal_distance(cluster_bins)
                
                if max_internal_dist <= self.max_internal_distance:
                    # Cluster is good quality
                    validated_clusters[cluster_id] = cluster_bins
                else:
                    # Split cluster due to poor quality
                    logger.info(f"Splitting cluster {cluster_id} due to large internal distance: {max_internal_dist:.0f}m")
                    sub_clusters = self._split_cluster_by_proximity(cluster_bins)
                    
                    for sub_cluster in sub_clusters:
                        validated_clusters[len(validated_clusters)] = sub_cluster
            
            return validated_clusters
            
        except Exception as e:
            logger.error(f"Error validating cluster quality: {e}")
            return clusters
    
    def _split_cluster_by_proximity(self, cluster_bins: List[Dict]) -> List[List[Dict]]:
        """
        Split a cluster into smaller sub-clusters based on proximity.
        """
        try:
            if len(cluster_bins) <= 2:
                return [cluster_bins]
            
            # Use smaller threshold for splitting
            smaller_threshold = self.optimal_distance_threshold * 0.7
            return list(self._connectivity_based_clustering(cluster_bins, smaller_threshold).values())
            
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
        
        Returns:
            Dictionary with cluster analysis including efficiency metrics
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
        
        # Quality rating
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
        """Rate the quality of a cluster."""
        score = 0
        
        # Size score (2-4 bins is optimal)
        if 2 <= bin_count <= 4:
            score += 30
        elif bin_count == 1:
            score += 20  # Single bins are okay
        elif bin_count == 5:
            score += 15
        else:
            score += 5  # Very large clusters are not ideal
        
        # Internal distance score
        if max_internal_dist <= 400:
            score += 40
        elif max_internal_dist <= 600:
            score += 30
        elif max_internal_dist <= 800:
            score += 20
        else:
            score += 10
        
        # Depot distance score (if available)
        if depot_distance is not None:
            if depot_distance <= 1000:
                score += 30  # Close to depot
            elif depot_distance <= 1500:
                score += 20
            elif depot_distance <= 2000:
                score += 15
            else:
                score += 10
        else:
            score += 15  # Neutral score if no depot data
        
        # Convert to rating
        if score >= 80:
            return 'excellent'
        elif score >= 60:
            return 'good'
        elif score >= 40:
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
                # Cluster size efficiency (prefer 2-4 bins per cluster)
                size_efficiency = self._get_size_efficiency(len(cluster_bins))
                
                # Internal distance efficiency
                max_internal = self._get_max_internal_distance(cluster_bins)
                distance_efficiency = max(0, 1 - (max_internal / 1000))  # Normalize to 1km
                
                # Depot efficiency (if available)
                depot_efficiency = 0.5  # Neutral if no depot
                if depot_data and cluster_bins:
                    center_lat = sum(b['lat'] for b in cluster_bins) / len(cluster_bins)
                    center_lng = sum(b['lng'] for b in cluster_bins) / len(cluster_bins)
                    depot_dist = calculate_haversine_distance(
                        depot_data['lat'], depot_data['lng'], center_lat, center_lng
                    )
                    depot_efficiency = max(0, 1 - (depot_dist / 3000))  # Normalize to 3km
                
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
        """Get efficiency score for cluster size."""
        if cluster_size == 1:
            return 0.6  # Single bins are okay but not optimal
        elif 2 <= cluster_size <= 4:
            return 1.0  # Optimal size
        elif cluster_size == 5:
            return 0.8
        elif cluster_size == 6:
            return 0.6
        else:
            return 0.3  # Too large
    
    def _fallback_clustering(self, bins_data: List[Dict]) -> Dict:
        """Simple fallback clustering when advanced methods fail."""
        logger.warning("Using fallback clustering - each bin becomes its own cluster")
        clusters = {}
        for i, bin_data in enumerate(bins_data):
            clusters[i] = [bin_data]
        return clusters

    # Compatibility methods with existing ClusteringService interface
    def create_bin_distance_matrix(self, bins_data: List[Dict]) -> np.ndarray:
        """Compatibility method - create distance matrix."""
        return self._create_distance_matrix(bins_data)
    
    def create_clusters_dbscan(self, bins_data: List[Dict], distance_matrix: Optional[np.ndarray] = None,
                              eps_meters: Optional[int] = None, min_samples: Optional[int] = None) -> Dict:
        """Compatibility method - use improved clustering instead of DBSCAN."""
        logger.info("Using improved clustering instead of DBSCAN")
        return self.create_optimal_clusters(bins_data)
    
    def get_cluster_info(self, clusters: Dict) -> Dict:
        """Compatibility method - get cluster information."""
        return self.get_cluster_analysis(clusters)
    
    def create_adaptive_clusters(self, bins_data: List[Dict]) -> Dict:
        """Compatibility method - use improved clustering."""
        return self.create_optimal_clusters(bins_data)