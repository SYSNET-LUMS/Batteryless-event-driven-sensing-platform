from typing import Dict, List, Optional
from services.external.osrm_service import OSRMService
from services.traffic_service import TrafficManager

class SimulationService:
    """Manages simulation state and coordinates updates"""
    
    def __init__(self, osrm_service: OSRMService = None):
        self.osrm_service = osrm_service or OSRMService()
        self.traffic_manager = TrafficManager()
        self.simulation_start_hour = 7

        self.travel_time_cache = {}
    
    def calculate_dynamic_thresholds(self, bins_data: List[Dict], 
                                   simulation_time_seconds: float,
                                   depot_data: Optional[Dict] = None) -> List[Dict]:
        """Calculate dynamic thresholds for all bins"""
        updated_bins = []
        
        for bin_data in bins_data:
            try:
                if depot_data:
                    threshold = self._calculate_single_dynamic_threshold(
                        bin_data, simulation_time_seconds, depot_data
                    )
                    bin_data['dynamic_threshold'] = threshold
                else:
                    bin_data['dynamic_threshold'] = bin_data.get('threshold', 80)
                
                updated_bins.append(bin_data)
                
            except Exception as e:
                print(f"Error calculating threshold for {bin_data.get('id')}: {e}")
                bin_data['dynamic_threshold'] = bin_data.get('threshold', 80)
                updated_bins.append(bin_data)
                
        
        return updated_bins
    
    def update_bin_fill_levels(self, bins_data: List[Dict], 
                             time_delta_seconds: float) -> tuple:
        """Update bin fill levels and return bins that hit thresholds"""
        bins_that_hit_threshold = []
        updated_bins = []
        
        for bin_data in bins_data:
            try:
                old_fill = bin_data['fillLevel']
                old_threshold = bin_data.get('dynamic_threshold', bin_data.get('threshold', 80))
                
                # Update fill level
                hours_passed = time_delta_seconds / 3600
                increase = bin_data['fillRate'] * hours_passed
                bin_data['fillLevel'] = min(100, bin_data['fillLevel'] + increase)
                
                # Check if bin crossed threshold
                if old_fill < old_threshold and bin_data['fillLevel'] >= old_threshold:
                    bins_that_hit_threshold.append(bin_data['id'])
                
                updated_bins.append(bin_data)
                
            except Exception as e:
                print(f"⚠️ Error updating bin {bin_data.get('id', 'unknown')}: {e}")
                updated_bins.append(bin_data)  # Add unchanged bin
        
        return updated_bins, bins_that_hit_threshold
    
    def get_traffic_info(self, simulation_time_seconds: float) -> Dict:
        """Get current traffic information"""
        try:
            start_hour = self.simulation_start_hour
            current_time_min = (start_hour * 60) + (simulation_time_seconds // 60)
            current_hour = (current_time_min // 60) % 24
            
            current_density = self.traffic_manager.get_density_at_time(current_time_min)
            
            return {
                'current_density': current_density,
                'current_hour': current_hour,
                'time_of_day': f"{current_hour:02d}:{(current_time_min % 60):02d}",
                'traffic_level': self._get_traffic_level_description(current_density)
            }
        except Exception as e:
            print(f"⚠️ Error getting traffic info: {e}")
            return {
                'current_density': 1.0,
                'current_hour': 7,
                'time_of_day': "07:00",
                'traffic_level': 'Unknown'
            }
    
    def generate_cluster_data(self, bins_data: List[Dict], clusters: Dict) -> Dict:
        """Generate cluster assignment data"""
        clusters_data = {}
        
        try:
            for cluster_id, cluster_bins in clusters.items():
                for bin_data in cluster_bins:
                    clusters_data[bin_data['id']] = [b['id'] for b in cluster_bins]
        except Exception as e:
            print(f"⚠️ Error generating cluster data: {e}")
        
        return clusters_data
    
    def _calculate_single_dynamic_threshold(self, bin_data: Dict, 
                                          simulation_time_seconds: float,
                                          depot_data: Dict) -> float:
        """Calculate dynamic threshold for a single bin"""
        try:
            C = bin_data['capacity']
            r = bin_data['fillRate']
            
            # Get travel time to depot
            base_travel_hours = self._get_travel_time_to_depot(bin_data, depot_data)
            
            # Apply traffic multiplier
            current_time_min = simulation_time_seconds // 60
            traffic_density = self.traffic_manager.get_density_at_time(current_time_min)
            travel_with_traffic = base_travel_hours * traffic_density
            
            # Add collection time and safety buffer
            collection_hours = 5 / 60  # 5 minutes
            
            # Adaptive safety buffer based on fill rate
            if r > 30:
                safety_buffer = 0.90
            elif r > 20:
                safety_buffer = 0.80
            else:
                safety_buffer = 0.50
            
            T_min = travel_with_traffic + collection_hours + safety_buffer
            
            # Calculate threshold
            threshold = 100 * (1 - (r * T_min / C))
            return max(50, min(95, threshold))  # Clamp between 50-95%
            
        except Exception as e:
            print(f"⚠️ Dynamic threshold calculation error: {e}")
            return bin_data.get('threshold', 80)
  
    def _get_travel_time_to_depot(self, bin_data: Dict, depot_data: Dict) -> float:
        """Get travel time from bin to depot in hours (cached)"""
        # Create cache key from coordinates
        cache_key = f"{bin_data['lat']},{bin_data['lng']}->{depot_data['lat']},{depot_data['lng']}"
        
        # Return cached value if exists
        if cache_key in self.travel_time_cache:
            return self.travel_time_cache[cache_key]
        
        try:
            # Try OSRM first (only called once per bin-depot pair)
            travel_time_min = self.osrm_service.get_travel_time_with_traffic(
                bin_data['lat'], bin_data['lng'],
                depot_data['lat'], depot_data['lng'],
                traffic_multiplier=1.0
            )
            travel_time_hours = travel_time_min / 60
            
        except:
            # Fallback calculation
            from utils.distance import calculate_distance_km
            distance_km = calculate_distance_km(
                bin_data['lat'], bin_data['lng'],
                depot_data['lat'], depot_data['lng']
            )
            travel_time_hours = distance_km / 30  # 30 km/h average in city
        
        # Cache the result
        self.travel_time_cache[cache_key] = travel_time_hours
        return travel_time_hours
    
    def _get_traffic_level_description(self, density: float) -> str:
        """Convert traffic density to human-readable description"""
        if density > 5:
            return 'Heavy'
        elif density > 2:
            return 'Moderate'
        else:
            return 'Light'