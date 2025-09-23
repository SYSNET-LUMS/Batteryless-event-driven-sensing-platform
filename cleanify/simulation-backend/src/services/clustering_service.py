import numpy as np
from sklearn.cluster import DBSCAN
from typing import Dict, List
from config.settings import Config
from services.external.osrm_service import OSRMService
import logging

logger = logging.getLogger(__name__)

class ClusteringService:
    """Waste collection bin clustering service using OSRM for distances"""
    
    def __init__(self, config: Config = None, osrm_service: OSRMService = None):
        self.config = config or Config()
        self.osrm_service = osrm_service or OSRMService()
        
        # Enhanced clustering parameters
        self.default_eps_meters = 500  # Increased from 300m to 500m
        self.default_min_samples = 2
        self.adaptive_clustering = True
        self.max_cluster_size = 8  # Prevent overly large clusters
        self.min_cluster_efficiency = 0.7  # Minimum efficiency for clustering
    
    def create_bin_distance_matrix(self, bins_data: List[Dict]) -> np.ndarray:
        """Create distance matrix between all bins using OSRM service"""
        n_bins = len(bins_data)
        distance_matrix = np.zeros((n_bins, n_bins))
        
        for i in range(n_bins):
            for j in range(n_bins):
                if i == j:
                    distance_matrix[i][j] = 0
                elif i < j:
                    # Use centralized OSRM service
                    distance = self.osrm_service.get_distance_between_points(
                        bins_data[i]['lat'], bins_data[i]['lng'],
                        bins_data[j]['lat'], bins_data[j]['lng']
                    )
                    distance_matrix[i][j] = distance
                    distance_matrix[j][i] = distance
        
        return distance_matrix
    
    def create_clusters_dbscan(self, bins_data: List[Dict], distance_matrix: np.ndarray,
                              eps_meters: int = None, min_samples: int = None) -> Dict:
        """Create clusters using DBSCAN on distance matrix with enhanced parameters"""
        
        # Use adaptive parameters if not specified
        if eps_meters is None:
            eps_meters = self._determine_optimal_eps(bins_data, distance_matrix)
        if min_samples is None:
            min_samples = self._determine_optimal_min_samples(len(bins_data))
            
        logger.info(f"Clustering {len(bins_data)} bins with eps={eps_meters}m, min_samples={min_samples}")
        
        clustering = DBSCAN(eps=eps_meters, min_samples=min_samples, metric='precomputed')
        cluster_labels = clustering.fit_predict(distance_matrix)
        
        clusters = {}
        noise_bins = []
        
        for i, label in enumerate(cluster_labels):
            if label == -1:
                noise_bins.append(bins_data[i])
            else:
                if label not in clusters:
                    clusters[label] = []
                clusters[label].append(bins_data[i])
        
        # Add noise bins as individual clusters
        noise_cluster_id = max(clusters.keys()) + 1 if clusters else 0
        for noise_bin in noise_bins:
            clusters[noise_cluster_id] = [noise_bin]
            noise_cluster_id += 1
        
        # Post-process clusters for optimization
        if self.adaptive_clustering:
            clusters = self._optimize_clusters(clusters, distance_matrix, bins_data)
        
        logger.info(f"Created {len(clusters)} clusters from {len(bins_data)} bins")
        return clusters
    
    def _determine_optimal_eps(self, bins_data: List[Dict], distance_matrix: np.ndarray) -> int:
        """Determine optimal eps parameter based on data characteristics"""
        try:
            n_bins = len(bins_data)
            if n_bins <= 2:
                return self.default_eps_meters
            
            # Get all pairwise distances (excluding diagonal)
            distances = []
            for i in range(n_bins):
                for j in range(i + 1, n_bins):
                    distances.append(distance_matrix[i][j])
            
            distances.sort()
            
            # Use percentile-based approach
            if len(distances) <= 3:
                # Small dataset - use median
                optimal_eps = int(distances[len(distances) // 2])
            else:
                # Larger dataset - use 60th percentile to capture local neighborhoods
                percentile_60 = distances[int(0.6 * len(distances))]
                optimal_eps = min(int(percentile_60 * 1.2), 1000)  # Cap at 1km
            
            # Ensure reasonable bounds
            optimal_eps = max(200, min(optimal_eps, 2000))  # Between 200m and 2km
            
            logger.debug(f"Optimal eps determined: {optimal_eps}m (from {len(distances)} distances)")
            return optimal_eps
            
        except Exception as e:
            logger.warning(f"Error determining optimal eps: {e}, using default {self.default_eps_meters}m")
            return self.default_eps_meters
    
    def _determine_optimal_min_samples(self, n_bins: int) -> int:
        """Determine optimal min_samples based on dataset size"""
        if n_bins <= 4:
            return 1  # Small datasets - allow single-point clusters to merge
        elif n_bins <= 10:
            return 2  # Medium datasets
        else:
            return max(2, min(3, n_bins // 5))  # Scale with dataset size
    
    def _optimize_clusters(self, clusters: Dict, distance_matrix: np.ndarray, bins_data: List[Dict]) -> Dict:
        """Post-process clusters to improve quality"""
        try:
            # Split overly large clusters
            optimized_clusters = {}
            cluster_id = 0
            
            for original_id, cluster_bins in clusters.items():
                if len(cluster_bins) <= self.max_cluster_size:
                    # Cluster is appropriately sized
                    optimized_clusters[cluster_id] = cluster_bins
                    cluster_id += 1
                else:
                    # Split large cluster
                    logger.info(f"Splitting large cluster of {len(cluster_bins)} bins")
                    sub_clusters = self._split_large_cluster(cluster_bins, distance_matrix, bins_data)
                    
                    for sub_cluster in sub_clusters:
                        optimized_clusters[cluster_id] = sub_cluster
                        cluster_id += 1
            
            return optimized_clusters
            
        except Exception as e:
            logger.warning(f"Error optimizing clusters: {e}, returning original")
            return clusters
    
    def _split_large_cluster(self, cluster_bins: List[Dict], distance_matrix: np.ndarray, 
                           all_bins: List[Dict]) -> List[List[Dict]]:
        """Split a large cluster into smaller sub-clusters"""
        try:
            if len(cluster_bins) <= self.max_cluster_size:
                return [cluster_bins]
            
            # Get indices of cluster bins in original data
            cluster_indices = []
            for cluster_bin in cluster_bins:
                for i, bin_data in enumerate(all_bins):
                    if bin_data['id'] == cluster_bin['id']:
                        cluster_indices.append(i)
                        break
            
            # Create sub-distance matrix for cluster
            cluster_distances = np.zeros((len(cluster_indices), len(cluster_indices)))
            for i, idx1 in enumerate(cluster_indices):
                for j, idx2 in enumerate(cluster_indices):
                    cluster_distances[i][j] = distance_matrix[idx1][idx2]
            
            # Re-cluster with smaller eps
            smaller_eps = int(self.default_eps_meters * 0.7)  # 70% of default
            sub_clustering = DBSCAN(eps=smaller_eps, min_samples=2, metric='precomputed')
            sub_labels = sub_clustering.fit_predict(cluster_distances)
            
            # Group into sub-clusters
            sub_clusters = {}
            for i, label in enumerate(sub_labels):
                if label not in sub_clusters:
                    sub_clusters[label] = []
                sub_clusters[label].append(cluster_bins[i])
            
            # Convert to list and handle noise (-1 labels)
            result = []
            for label, bins in sub_clusters.items():
                if label == -1:
                    # Add noise points as individual clusters
                    for bin_data in bins:
                        result.append([bin_data])
                else:
                    result.append(bins)
            
            return result if result else [cluster_bins]
            
        except Exception as e:
            logger.warning(f"Error splitting cluster: {e}")
            return [cluster_bins]
    
    def get_cluster_info(self, clusters: Dict) -> Dict:
        """Get summary information about clusters with quality metrics"""
        cluster_info = {}
        
        for cluster_id, cluster_bins in clusters.items():
            center_lat = sum(bin_data['lat'] for bin_data in cluster_bins) / len(cluster_bins)
            center_lng = sum(bin_data['lng'] for bin_data in cluster_bins) / len(cluster_bins)
            
            total_waste = sum((bin_data['fillLevel'] / 100) * bin_data['capacity']
                            for bin_data in cluster_bins)
            
            # Calculate cluster quality metrics
            quality_metrics = self._calculate_cluster_quality(cluster_bins)
            
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
    
    def _calculate_cluster_quality(self, cluster_bins: List[Dict]) -> Dict:
        """Calculate quality metrics for a cluster"""
        try:
            if len(cluster_bins) <= 1:
                return {
                    'diameter_meters': 0,
                    'avg_distance_meters': 0,
                    'compactness_score': 1.0,
                    'collection_efficiency': 1.0,
                    'quality_rating': 'excellent'
                }
            
            # Calculate distances between all pairs
            distances = []
            for i, bin1 in enumerate(cluster_bins):
                for j, bin2 in enumerate(cluster_bins):
                    if i < j:
                        # Use Haversine distance for quality assessment
                        dist = self._haversine_distance(
                            bin1['lat'], bin1['lng'],
                            bin2['lat'], bin2['lng']
                        )
                        distances.append(dist)
            
            if not distances:
                return {
                    'diameter_meters': 0,
                    'avg_distance_meters': 0,
                    'compactness_score': 1.0,
                    'collection_efficiency': 1.0,
                    'quality_rating': 'excellent'
                }
            
            diameter = max(distances)
            avg_distance = sum(distances) / len(distances)
            
            # Compactness score (lower avg distance = more compact)
            compactness_score = max(0, 1 - (avg_distance / 1000))  # Normalize by 1km
            
            # Collection efficiency (based on total waste and proximity)
            total_waste = sum((b['fillLevel'] / 100) * b['capacity'] for b in cluster_bins)
            waste_per_distance = total_waste / max(avg_distance, 1)  # Avoid division by zero
            collection_efficiency = min(1.0, waste_per_distance / 5.0)  # Normalize
            
            # Overall quality rating
            overall_score = (compactness_score + collection_efficiency) / 2
            if overall_score >= 0.8:
                quality_rating = 'excellent'
            elif overall_score >= 0.6:
                quality_rating = 'good'
            elif overall_score >= 0.4:
                quality_rating = 'fair'
            else:
                quality_rating = 'poor'
            
            return {
                'diameter_meters': round(diameter, 1),
                'avg_distance_meters': round(avg_distance, 1),
                'compactness_score': round(compactness_score, 2),
                'collection_efficiency': round(collection_efficiency, 2),
                'quality_rating': quality_rating,
                'total_waste_liters': round(total_waste, 1)
            }
            
        except Exception as e:
            logger.error(f"Error calculating cluster quality: {e}")
            return {
                'error': str(e),
                'quality_rating': 'unknown'
            }
    
    def _haversine_distance(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Calculate Haversine distance between two points in meters"""
        import math
        
        # Convert decimal degrees to radians 
        lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])

        # Haversine formula 
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng/2)**2
        c = 2 * math.asin(math.sqrt(a))
        r = 6371  # Radius of earth in kilometers
        return c * r * 1000  # Convert to meters
    
    def create_adaptive_clusters(self, bins_data: List[Dict]) -> Dict:
        """Create clusters using adaptive parameters and multiple strategies"""
        try:
            logger.info(f"Creating adaptive clusters for {len(bins_data)} bins")
            
            # Create distance matrix
            distance_matrix = self.create_bin_distance_matrix(bins_data)
            
            # Try different clustering strategies and pick the best
            strategies = [
                {'eps': None, 'min_samples': None, 'name': 'adaptive'},
                {'eps': 400, 'min_samples': 2, 'name': 'conservative'},
                {'eps': 600, 'min_samples': 1, 'name': 'aggressive'},
            ]
            
            best_clusters = None
            best_score = -1
            best_strategy = None
            
            for strategy in strategies:
                try:
                    clusters = self.create_clusters_dbscan(
                        bins_data, distance_matrix,
                        strategy['eps'], strategy['min_samples']
                    )
                    
                    # Evaluate clustering quality
                    score = self._evaluate_clustering_quality(clusters, bins_data)
                    
                    logger.debug(f"Strategy '{strategy['name']}': {len(clusters)} clusters, score: {score:.2f}")
                    
                    if score > best_score:
                        best_score = score
                        best_clusters = clusters
                        best_strategy = strategy
                        
                except Exception as e:
                    logger.warning(f"Strategy '{strategy['name']}' failed: {e}")
                    continue
            
            if best_clusters is None:
                # Fallback: simple distance-based clustering
                logger.warning("All strategies failed, using fallback clustering")
                return self._fallback_clustering(bins_data)
            
            logger.info(f"Best strategy: '{best_strategy['name']}' with {len(best_clusters)} clusters (score: {best_score:.2f})")
            return best_clusters
            
        except Exception as e:
            logger.error(f"Error in adaptive clustering: {e}")
            return self._fallback_clustering(bins_data)
    
    def _evaluate_clustering_quality(self, clusters: Dict, bins_data: List[Dict]) -> float:
        """Evaluate overall clustering quality"""
        try:
            if not clusters:
                return 0.0
            
            cluster_info = self.get_cluster_info(clusters)
            
            # Metrics for evaluation
            total_score = 0
            total_bins = 0
            
            for cluster_id, info in cluster_info.items():
                bin_count = info['bin_count']
                quality = info['quality_metrics']
                
                # Weight by cluster size
                cluster_score = (
                    quality.get('compactness_score', 0) * 0.4 +
                    quality.get('collection_efficiency', 0) * 0.6
                )
                
                total_score += cluster_score * bin_count
                total_bins += bin_count
            
            # Penalize excessive fragmentation
            avg_cluster_size = total_bins / len(clusters) if clusters else 0
            fragmentation_penalty = max(0, (3 - avg_cluster_size) * 0.1)
            
            overall_score = (total_score / max(total_bins, 1)) - fragmentation_penalty
            return max(0, min(1, overall_score))
            
        except Exception as e:
            logger.error(f"Error evaluating clustering quality: {e}")
            return 0.0
    
    def _fallback_clustering(self, bins_data: List[Dict]) -> Dict:
        """Simple fallback clustering when advanced methods fail"""
        logger.info("Using simple fallback clustering")
        clusters = {}
        
        # Just put each bin in its own cluster
        for i, bin_data in enumerate(bins_data):
            clusters[i] = [bin_data]
        
        return clusters