from typing import Dict, List, Any, Optional
from services.routing.optimization_service import OptimizationService
from services.external.vroom_service import VROOMService

class DecisionService:
    """AI decision making service using VROOM for optimal routing"""
    
    def __init__(self, optimization_service: OptimizationService = None, 
                 vroom_service: VROOMService = None):
        self.vroom_service = vroom_service or VROOMService()
        self.optimization_service = optimization_service or OptimizationService(self.vroom_service)
        
        # Note: No more manual assignment tracking - VROOM handles this
    
    def get_routing_decision(self, data: Dict, current_time: float = None) -> List[Dict]:
        """
        Main routing decision using VROOM + Knapsack + Clustering workflow
        
        New workflow:
        1. Get clusters (DBSCAN)
        2. Select bins using knapsack (capacity optimization)
        3. Use VROOM for vehicle routing (travel optimization)
        """
        bins_data = data.get('bins_data', [])
        trucks_data = data.get('trucks_data', [])
        depot_data = data.get('depots_data', [{}])[0] if data.get('depots_data') else None
        
        if not bins_data or not trucks_data:
            return []
        
        # Get clusters for the workflow
        clusters = self._get_clusters(bins_data)
        
        if not clusters:
            clusters = {i: [bin_data] for i, bin_data in enumerate(bins_data)}
        
        # Use VROOM + Knapsack optimization
        optimization_result = self.optimization_service.optimize_truck_routes_with_vroom(
            trucks_data, clusters, depot_data, current_time,
            preferred_bin_ids=data.get('preferred_bin_ids')
        )
        
        routes = optimization_result.get('routes', [])
  
        return routes
    
    def get_cluster_collection_decision(self, target_bin: Dict, cluster_bins: List[Dict],
                                     truck_capacity: float, current_load: float,
                                     simulation_time: float = None,
                                     all_bins: List[Dict] = None,
                                     collection_queue: List[str] = None) -> List[Dict]:
        """
        Get optimal bin collection from cluster using knapsack
        (This method still used for individual truck's cluster collection)
        """
        remaining_capacity = truck_capacity - current_load
        
        # Build augmented candidate set:
        # - bins that already need collection
        # - bins near target that are about to reach DT soon (<= 1h) or within 5% of DT
        def needs_collection(b: Dict) -> bool:
            try:
                return self.optimization_service._needs_collection(b, simulation_time)
            except Exception:
                return False

        def time_to_threshold_hours(b: Dict) -> float:
            try:
                fill_level = b.get('fillLevel', 0)
                capacity = b.get('capacity', 500)
                fill_rate = b.get('fillRate', 0)
                threshold = b.get('dynamic_threshold', b.get('threshold', 80))
                if fill_level >= threshold:
                    return 0.0
                if fill_rate <= 0:
                    return float('inf')
                liters_needed = max(0.0, ((threshold - fill_level) / 100.0) * capacity)
                return liters_needed / fill_rate
            except Exception:
                return float('inf')

        def is_nearby(b: Dict, radius_km: float = 0.5) -> bool:
            try:
                d = self._calculate_distance(
                    target_bin['lat'], target_bin['lng'], b['lat'], b['lng']
                )
                return d <= radius_km
            except Exception:
                return False

        threshold_slack = 5.0  # percent
        soon_hours = 1.0
        radius_km = 0.5

        # Build candidate set: all bins in the collection queue (if provided) that are nearby and need collection
        expanded_candidates = []
        seen = set()
        # Use all_bins and collection_queue if provided, else fallback to cluster_bins
        candidate_bins = cluster_bins or []
        if all_bins and collection_queue:
            candidate_bins = [b for b in all_bins if b.get('id') in collection_queue]

        for b in candidate_bins:
            if b.get('id') in seen:
                continue
            # Only consider bins within radius of target_bin
            if is_nearby(b, radius_km):
                if needs_collection(b):
                    expanded_candidates.append(b)
                    seen.add(b.get('id'))
                    continue
                # Consider near-threshold, nearby bins
                th = b.get('dynamic_threshold', b.get('threshold', 80))
                fl = b.get('fillLevel', 0)
                if fl >= (th - threshold_slack) or time_to_threshold_hours(b) <= soon_hours:
                    expanded_candidates.append(b)
                    seen.add(b.get('id'))

        # Ensure target_bin is included in candidates for ordering context
        if target_bin and target_bin.get('id') not in seen:
            expanded_candidates.insert(0, target_bin)

        # Use optimization service for knapsack selection on expanded set
        selected_bins = self.optimization_service._select_optimal_bins_from_cluster(
            expanded_candidates, remaining_capacity, simulation_time, bypass_needs_check=True
        )

        # Include target bin if not already selected
        result_bins = [target_bin]
        for bin_data in selected_bins:
            if bin_data['id'] != target_bin['id']:
                result_bins.append(bin_data)

        return result_bins
    
    def check_vroom_availability(self) -> Dict:
        """Check if VROOM service is available"""
        is_available = self.vroom_service.is_service_available()
        
        return {
            "vroom_available": is_available,
            "fallback_mode": not is_available,
            "optimization_method": "VROOM" if is_available else "Simple Assignment"
        }
    
    def _get_clusters(self, bins_data: List[Dict]) -> Dict:
        """
        Get bin clusters - this would integrate with clustering service
        For now, create simple geographic clusters as placeholder
        """
        try:
            # This should call the clustering service
            # For now, create a simple mock cluster based on coordinates
            
            if len(bins_data) < 2:
                return {0: bins_data}
            
            # Simple clustering by proximity (placeholder)
            clusters = {}
            cluster_id = 0
            processed_bins = set()
            
            for i, bin_data in enumerate(bins_data):
                if bin_data['id'] in processed_bins:
                    continue
                
                # Start new cluster
                cluster_bins = [bin_data]
                processed_bins.add(bin_data['id'])
                
                # Find nearby bins (within ~500m)
                for j, other_bin in enumerate(bins_data):
                    if i != j and other_bin['id'] not in processed_bins:
                        distance = self._calculate_distance(
                            bin_data['lat'], bin_data['lng'],
                            other_bin['lat'], other_bin['lng']
                        )
                        
                        if distance < 0.5:  # 500m threshold
                            cluster_bins.append(other_bin)
                            processed_bins.add(other_bin['id'])
                
                clusters[cluster_id] = cluster_bins
                cluster_id += 1
            
            return clusters
            
        except Exception as e:
            print(f"⚠️ Clustering error: {e}")
            # Fallback: each bin is its own cluster
            return {i: [bin_data] for i, bin_data in enumerate(bins_data)}
    
    def _calculate_distance(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Calculate distance in km (simple haversine)"""
        import math
        
        R = 6371  # Earth radius in km
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)
        a = (math.sin(dlat/2) * math.sin(dlat/2) + 
            math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * 
            math.sin(dlng/2) * math.sin(dlng/2))
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c
    
    # Legacy compatibility methods (simplified)
    def reset_assignments(self):
        """Legacy method - VROOM handles assignments, no manual tracking needed"""
        print("ℹ️ Assignment reset not needed - VROOM handles optimization")
        pass
    
    def is_bin_assigned(self, bin_id: str) -> bool:
        """Legacy method - always return False since VROOM handles assignments"""
        return False
    
    def mark_bin_assigned(self, bin_id: str):
        """Legacy method - VROOM handles assignments"""
        pass
    
    def reserve_bin(self, bin_id: str, truck_id: str, dispatch_time: float):
        """Legacy method - VROOM handles assignments"""
        pass
    
    def release_reservation(self, bin_id: str, truck_id: str):
        """Legacy method - VROOM handles assignments"""
        pass
    
    @property
    def reserved_bins(self):
        """Legacy property - return empty set since VROOM handles assignments"""
        return set()
    
    @property
    def waiting_assignments(self):
        """Legacy property - return empty dict since VROOM handles assignments"""
        return {}
    
    def process_waiting_trucks(self, current_simulation_time: float) -> List[Dict]:
        """Legacy method - VROOM handles all routing, return empty list"""
        return []