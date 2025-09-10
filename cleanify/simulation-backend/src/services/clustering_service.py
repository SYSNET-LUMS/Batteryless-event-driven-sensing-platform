import numpy as np
from sklearn.cluster import DBSCAN
from typing import Dict, List
from config.settings import Config
from services.external.osrm_service import OSRMService

class ClusteringService:
    """Waste collection bin clustering service using OSRM for distances"""
    
    def __init__(self, config: Config = None, osrm_service: OSRMService = None):
        self.config = config or Config()
        self.osrm_service = osrm_service or OSRMService()
    
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
                              eps_meters: int = 300, min_samples: int = 2) -> Dict:
        """Create clusters using DBSCAN on distance matrix"""
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

        return clusters
    
    def get_cluster_info(self, clusters: Dict) -> Dict:
        """Get summary information about clusters"""
        cluster_info = {}
        
        for cluster_id, cluster_bins in clusters.items():
            center_lat = sum(bin_data['lat'] for bin_data in cluster_bins) / len(cluster_bins)
            center_lng = sum(bin_data['lng'] for bin_data in cluster_bins) / len(cluster_bins)
            
            total_waste = sum((bin_data['fillLevel'] / 100) * bin_data['capacity']
                            for bin_data in cluster_bins)
            
            cluster_info[cluster_id] = {
                'bin_count': len(cluster_bins),
                'bin_ids': [bin_data['id'] for bin_data in cluster_bins],
                'center_lat': center_lat,
                'center_lng': center_lng,
                'total_waste': total_waste,
                'bins': cluster_bins
            }
        
        return cluster_info