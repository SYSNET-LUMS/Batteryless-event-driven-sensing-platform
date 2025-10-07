from typing import Dict, List, Any, Optional
from services.routing.optimization_service import OptimizationService
from services.routing.dynamic_route_optimizer import DynamicRouteOptimizer
from services.external.vroom_service import VROOMService

class DecisionService:
    """AI decision making service using VROOM for optimal routing"""
    
    def __init__(self, optimization_service: OptimizationService = None, 
                 vroom_service: VROOMService = None):
        self.vroom_service = vroom_service or VROOMService()
        self.optimization_service = optimization_service or OptimizationService(self.vroom_service)
        self.dynamic_route_optimizer = DynamicRouteOptimizer(self.vroom_service)
        
        # Note: No more manual assignment tracking - VROOM handles this
    
    def get_routing_decision(self, data: Dict, current_time: float = 0.0) -> List[Dict]:
        """
        Main routing decision using collection queue priorities
        
        Workflow:
        1. If preferred_bin_ids (filtered collection queue) is provided, use basic optimization
           to respect the collection queue and traffic dispatch decisions
        2. Otherwise, use dynamic route optimizer for enhanced routing with extensions
        """
        bins_data = data.get('bins_data', [])
        trucks_data = data.get('trucks_data', [])
        depot_data = data.get('depots_data', [{}])[0] if data.get('depots_data') else None
        schedules = data.get('schedules', [])
        preferred_bin_ids = data.get('preferred_bin_ids')
        
        if not bins_data or not trucks_data:
            return []
        
        # Respect collection queue when provided (fuel efficiency + overflow prevention)
        if preferred_bin_ids:
            print(f"🎯 Using collection queue priority routing: {len(preferred_bin_ids)} bins")
            
            # Filter bins to only those in the collection queue
            filtered_bins = [b for b in bins_data if b.get('id') in preferred_bin_ids]
            
            if not filtered_bins:
                print("⚠️ No bins in collection queue need immediate dispatch")
                return []
            
            # Use basic optimization that respects preferred_bin_ids
            clusters = self._get_clusters(filtered_bins)
            if not clusters:
                clusters = {i: [bin_data] for i, bin_data in enumerate(filtered_bins)}
            
            optimization_result = self.optimization_service.optimize_truck_routes_with_vroom(
                trucks_data, clusters, depot_data, current_time, preferred_bin_ids
            )
            
            routes = optimization_result.get('routes', [])
            
            # Add collection queue context to routes
            for route in routes:
                route['collection_source'] = 'priority_queue'
                route['reason'] = f"Collection queue dispatch: {route.get('reason', 'Optimized route')}"
            
            return routes
        
        # Fallback to dynamic optimization when no collection queue filtering
        print("🔄 Using dynamic route optimization (no collection queue filter)")
        try:
            dynamic_result = self.dynamic_route_optimizer.optimize_routes_with_dynamic_availability(
                trucks_data, bins_data, schedules, depot_data or {}, current_time
            )
            
            if dynamic_result and dynamic_result.get('success'):
                optimization_result = dynamic_result.get('optimization_result')
                if not optimization_result:
                    raise ValueError("Optimization result is None")
                    
                routes = []
                
                # Process route extensions (nearby bins collected during return)
                for extension in optimization_result.get('route_extensions', []):
                    if extension.get('success'):
                        route = {
                            'truck_id': extension['truck_id'],
                            'route': extension.get('extended_route', []),
                            'dispatch': 'now',
                            'delay_min': 0,
                            'reason': f"Route extended with {len(extension.get('additional_bins', []))} nearby bins",
                            'route_extensions': [extension],  # Include extension data for agent processing
                            'extension_type': extension.get('extension_type', 'route_extension'),
                            'collection_source': 'dynamic_optimization'
                        }
                        routes.append(route)
                
                # Process new routes  
                for new_route in optimization_result.get('new_routes', []):
                    if new_route.get('success'):
                        route = {
                            'truck_id': new_route['truck_id'],
                            'route': new_route.get('optimized_route', []),
                            'dispatch': 'now',
                            'delay_min': 0,
                            'reason': f"New optimized route with {len(new_route.get('optimized_route', []))} bins",
                            'collection_source': 'dynamic_optimization'
                        }
                        routes.append(route)
                
                # Process critical overrides
                for override in optimization_result.get('critical_overrides', []):
                    if override.get('success'):
                        route = {
                            'truck_id': override['truck_id'],
                            'route': override.get('assigned_bins', []),
                            'dispatch': 'now',
                            'delay_min': 0,
                            'reason': f"Critical override: {override.get('reason', 'Emergency dispatch')}",
                            'collection_source': 'critical_override'
                        }
                        routes.append(route)
                
                return routes
                
        except Exception as e:
            print(f"⚠️ Dynamic optimization failed: {e}, falling back to basic routing")
        
        # Final fallback to basic optimization
        clusters = self._get_clusters(bins_data)
        if not clusters:
            clusters = {i: [bin_data] for i, bin_data in enumerate(bins_data)}
        
        optimization_result = self.optimization_service.optimize_truck_routes_with_vroom(
            trucks_data, clusters, depot_data, current_time, preferred_bin_ids
        )
        
        routes = optimization_result.get('routes', [])
        
        # Add fallback context to routes
        for route in routes:
            route['collection_source'] = 'fallback_basic'
            route['reason'] = f"Fallback routing: {route.get('reason', 'Basic optimization')}"
        
        return routes
    
    def get_cluster_collection_decision(self, target_bin: Dict, cluster_bins: List[Dict],
                                     truck_capacity: float, current_load: float,
                                     simulation_time: float = 0.0,
                                     all_bins: Optional[List[Dict]] = None,
                                     collection_queue: Optional[List[str]] = None) -> List[Dict]:
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

        # FUEL EFFICIENCY OPTIMIZATION: Maximize truck load from same cluster
        current_selection_volume = sum(b.get('current_fill', b.get('fillLevel', 0) * b.get('capacity', 500) / 100) for b in result_bins)
        remaining_space = remaining_capacity - current_selection_volume
        
        if remaining_space > 0 and cluster_bins:
            # Find bins from same cluster that aren't in collection queue but have good fill levels
            selected_ids = {b['id'] for b in result_bins}
            additional_candidates = [b for b in cluster_bins if b['id'] not in selected_ids]
            
            # Sort by fill level (highest first) to maximize efficiency
            additional_candidates.sort(key=lambda x: x.get('current_fill', x.get('fillLevel', 0) * x.get('capacity', 500) / 100), reverse=True)
            
            # Greedily add bins that fit, prioritizing higher fill levels
            for candidate in additional_candidates:
                candidate_volume = candidate.get('current_fill', candidate.get('fillLevel', 0) * candidate.get('capacity', 500) / 100)
                
                # Only collect if bin has meaningful fill level (at least 50L or 20% of capacity)
                min_worthwhile = max(50, candidate.get('capacity', 500) * 0.2)
                
                if candidate_volume >= min_worthwhile and candidate_volume <= remaining_space:
                    result_bins.append(candidate)
                    remaining_space -= candidate_volume
                    
                    # If truck is nearly full (>90%), stop looking for more bins
                    if remaining_space < (truck_capacity * 0.1):
                        break

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