"""
Dynamic Route Optimizer

Enhances VROOM integration with dynamic route management:
1. Route extension for trucks already on the road
2. Real-time capacity and availability tracking
3. Intelligent truck assignment optimization
"""

from typing import Dict, List, Optional, Tuple, Any
from services.external.vroom_service import VROOMService
from services.routing.enhanced_truck_availability_service import EnhancedTruckAvailabilityService
from services.external.osrm_service import OSRMService
import logging
import json
import time

logger = logging.getLogger(__name__)

class DynamicRouteOptimizer:
    """Enhanced route optimization with dynamic capabilities"""
    
    def __init__(self, vroom_service: VROOMService = None, 
                 availability_service: EnhancedTruckAvailabilityService = None,
                 osrm_service: OSRMService = None):
        self.vroom_service = vroom_service or VROOMService()
        self.availability_service = availability_service or EnhancedTruckAvailabilityService()
        self.osrm_service = osrm_service or OSRMService()
        
        # Configuration
        self.max_route_duration_minutes = 480  # 8 hours max route
        self.min_efficiency_threshold = 0.7    # 70% efficiency minimum
        self.dynamic_reoptimization_interval = 15  # 15 minutes
        
    def optimize_routes_with_dynamic_availability(self, trucks_data: List[Dict], bins_data: List[Dict],
                                                schedules: List[Dict], depot_data: Dict,
                                                current_time_seconds: float) -> Dict:
        """
        Main optimization method that considers dynamic truck availability
        
        Returns comprehensive routing solution with:
        - Route extensions for busy trucks
        - New optimized routes for available trucks  
        - Deferred bins when no trucks available
        """
        try:
            start_time = time.time()
            
            # Step 1: Analyze truck availability comprehensively
            availability_result = self.availability_service.get_available_trucks_enhanced(
                trucks_data, bins_data, schedules, current_time_seconds, depot_data
            )
            
            # Step 2: Identify bins that need collection
            bins_needing_collection = self._identify_bins_needing_collection(
                bins_data, current_time_seconds
            )
            
            if not bins_needing_collection:
                return {
                    'success': True,
                    'message': 'No bins require collection at this time',
                    'optimization_result': {
                        'route_extensions': [],
                        'new_routes': [],
                        'critical_overrides': [],
                        'deferred_collections': []
                    },
                    'availability_analysis': availability_result
                }
            
            # Step 3: Get optimal assignments considering all truck states
            optimal_assignments = self.availability_service.get_optimal_truck_assignments(
                availability_result, bins_needing_collection, depot_data
            )
            
            if not optimal_assignments:
                optimal_assignments = {
                    'route_extensions': [],
                    'new_dispatches': [],
                    'critical_overrides': [],
                    'deferred_collections': []
                }
            
            # Step 4: Process route extensions (highest priority)
            route_extension_results = self._process_route_extensions(
                optimal_assignments.get('route_extensions', []),
                trucks_data, bins_data, depot_data, current_time_seconds
            )
            
            # Step 5: Optimize new routes for available trucks
            new_route_results = self._optimize_new_routes_vroom(
                optimal_assignments.get('new_dispatches', []),
                availability_result['available_trucks'],
                bins_data, depot_data, current_time_seconds
            )
            
            # Step 6: Handle critical overrides if needed
            override_results = self._handle_critical_overrides(
                optimal_assignments.get('critical_overrides', []),
                trucks_data, bins_data, depot_data, current_time_seconds
            )
            
            # Step 7: Compile comprehensive result
            optimization_result = {
                'optimization_type': 'dynamic_enhanced',
                'execution_time': time.time() - start_time,
                'timestamp': current_time_seconds,
                'availability_analysis': availability_result,
                'route_extensions': route_extension_results,
                'new_routes': new_route_results,
                'critical_overrides': override_results,
                'deferred_collections': optimal_assignments.get('deferred_collections', []),
                'optimization_summary': self._generate_optimization_summary(
                    route_extension_results, new_route_results, override_results,
                    optimal_assignments.get('deferred_collections', [])
                )
            }
            
            return {
                'success': True,
                'message': f'Dynamic optimization completed in {optimization_result["execution_time"]:.2f}s',
                'optimization_result': optimization_result
            }
            
        except Exception as e:
            logger.error(f"Error in dynamic route optimization: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': 'Dynamic optimization failed - falling back to basic routing',
                'fallback_result': self._fallback_basic_optimization(
                    trucks_data, bins_data, depot_data, current_time_seconds
                )
            }
    
    def _identify_bins_needing_collection(self, bins_data: List[Dict], current_time_seconds: float) -> List[Dict]:
        """Identify bins that need immediate or near-future collection"""
        bins_needing_collection = []
        
        for bin_data in bins_data:
            try:
                fill_level = bin_data.get('fillLevel', 0)
                threshold = bin_data.get('dynamic_threshold', bin_data.get('threshold', 80))
                fill_rate = bin_data.get('fillRate', 0)
                capacity = bin_data.get('capacity', 500)
                
                # Immediate collection needed
                if fill_level >= threshold:
                    bin_data['collection_urgency'] = 'immediate'
                    bin_data['collection_reason'] = f'Above threshold ({fill_level}% >= {threshold}%)'
                    bins_needing_collection.append(bin_data)
                    continue
                
                # Predictive collection - will reach threshold soon
                if fill_rate > 0:
                    hours_to_threshold = ((threshold - fill_level) / 100) * capacity / fill_rate
                    
                    if hours_to_threshold <= 4:  # Within 4 hours
                        bin_data['collection_urgency'] = 'soon'
                        bin_data['collection_reason'] = f'Will reach threshold in {hours_to_threshold:.1f}h'
                        bin_data['predicted_threshold_time'] = current_time_seconds + (hours_to_threshold * 3600)
                        bins_needing_collection.append(bin_data)
                        continue
                
                # Check for anomalies or special conditions
                if self._check_special_collection_conditions(bin_data, current_time_seconds):
                    bin_data['collection_urgency'] = 'special'
                    bins_needing_collection.append(bin_data)
                    
            except Exception as e:
                logger.warning(f"Error analyzing bin {bin_data.get('id', 'unknown')}: {e}")
        
        return bins_needing_collection
    
    def _check_special_collection_conditions(self, bin_data: Dict, current_time_seconds: float) -> bool:
        """Check for special conditions requiring collection"""
        # High fill rate indicating rapid filling
        fill_rate = bin_data.get('fillRate', 0)
        if fill_rate > 10:  # Very high fill rate
            bin_data['collection_reason'] = f'High fill rate ({fill_rate:.1f}/hour)'
            return True
        
        # Long time since last collection
        last_collected = bin_data.get('lastCollected', 0)
        hours_since_collection = (current_time_seconds - last_collected) / 3600
        if hours_since_collection > 168:  # More than 1 week
            bin_data['collection_reason'] = f'Not collected for {hours_since_collection:.0f} hours'
            return True
        
        # Sensor anomalies or maintenance needed
        if bin_data.get('sensorStatus') == 'warning':
            bin_data['collection_reason'] = 'Sensor warning - maintenance check needed'
            return True
        
        return False
    
    def _process_route_extensions(self, route_extensions: List[Dict], trucks_data: List[Dict],
                                bins_data: List[Dict], depot_data: Dict, 
                                current_time_seconds: float) -> List[Dict]:
        """Process route extensions for trucks already on the road"""
        extension_results = []
        
        for extension in route_extensions:
            try:
                truck_id = extension['truck_id']
                additional_bins = extension['additional_bins']
                current_route = extension['current_route']
                
                # Find the truck data
                truck_data = next((t for t in trucks_data if t.get('id') == truck_id), None)
                if not truck_data:
                    logger.warning(f"Truck {truck_id} not found for route extension")
                    continue
                
                # Calculate optimal insertion points for new bins
                optimized_extension = self._optimize_route_extension(
                    truck_data, additional_bins, current_route, bins_data, depot_data
                )
                
                if optimized_extension['success']:
                    extension_results.append({
                        'truck_id': truck_id,
                        'extension_type': 'route_extension',
                        'original_route': current_route,
                        'extended_route': optimized_extension['extended_route'],
                        'additional_bins': [b.get('id') for b in additional_bins],
                        'optimization_details': optimized_extension,
                        'estimated_additional_time': optimized_extension.get('additional_time_minutes', 0),
                        'fuel_impact': optimized_extension.get('fuel_impact', 'minimal'),
                        'success': True
                    })
                else:
                    extension_results.append({
                        'truck_id': truck_id,
                        'extension_type': 'failed_extension',
                        'reason': optimized_extension.get('error', 'Optimization failed'),
                        'success': False
                    })
                    
            except Exception as e:
                logger.error(f"Error processing route extension for truck {extension.get('truck_id')}: {e}")
                extension_results.append({
                    'truck_id': extension.get('truck_id'),
                    'extension_type': 'error',
                    'error': str(e),
                    'success': False
                })
        
        return extension_results
    
    def _optimize_route_extension(self, truck_data: Dict, additional_bins: List[Dict],
                                current_route: List[str], bins_data: List[Dict], 
                                depot_data: Dict) -> Dict:
        """Optimize the insertion of additional bins into existing route"""
        try:
            # Get truck's current position and remaining route
            route_index = truck_data.get('routeIndex', 0)
            remaining_route_ids = current_route[route_index:]
            
            if not remaining_route_ids:
                # Truck finished route, create new mini-route
                return self._create_post_route_extension(
                    truck_data, additional_bins, depot_data
                )
            
            # Create bin lookup for easy access
            bin_lookup = {b.get('id'): b for b in bins_data}
            
            # Get positions for remaining route bins
            remaining_bins = []
            for bin_id in remaining_route_ids:
                if bin_id in bin_lookup:
                    remaining_bins.append(bin_lookup[bin_id])
            
            # Use VROOM for optimal insertion if we have enough data
            if len(additional_bins) > 1 and len(remaining_bins) > 1:
                vroom_result = self._use_vroom_for_extension(
                    truck_data, additional_bins, remaining_bins, depot_data
                )
                
                if vroom_result['success']:
                    return vroom_result
            
            # Fall back to simple nearest insertion
            return self._simple_route_insertion(
                truck_data, additional_bins, remaining_bins, depot_data
            )
            
        except Exception as e:
            logger.error(f"Error optimizing route extension: {e}")
            return {'success': False, 'error': str(e)}
    
    def _use_vroom_for_extension(self, truck_data: Dict, additional_bins: List[Dict],
                               remaining_bins: List[Dict], depot_data: Dict) -> Dict:
        """Use VROOM to optimize route extension"""
        try:
            # Prepare VROOM problem for route extension
            all_bins = remaining_bins + additional_bins
            
            # Mark which bins are already committed (remaining route)
            remaining_ids = [b.get('id') for b in remaining_bins]
            
            # Create single truck problem with capacity constraints
            current_load = truck_data.get('currentLoad', 0)
            capacity = truck_data.get('capacity', 1000)
            available_capacity = capacity - current_load
            
            vroom_problem = {
                'vehicles': [{
                    'id': truck_data.get('id'),
                    'start': [truck_data.get('lng', 0), truck_data.get('lat', 0)],
                    'end': [depot_data.get('lng', 0), depot_data.get('lat', 0)],
                    'capacity': [int(available_capacity)],
                    'profile': 'driving'
                }],
                'jobs': [],
                'options': {
                    'g': True  # Return geometry
                }
            }
            
            # Add jobs for all bins
            for bin_data in all_bins:
                bin_load = int((bin_data.get('fillLevel', 0) / 100) * bin_data.get('capacity', 500))
                
                job = {
                    'id': bin_data.get('id'),
                    'location': [bin_data.get('lng', 0), bin_data.get('lat', 0)],
                    'delivery': [bin_load],
                    'service': 300,  # 5 minutes service time
                }
                
                # Add priority for bins already in route
                if bin_data.get('id') in remaining_ids:
                    job['priority'] = 100  # High priority for existing route
                else:
                    urgency = bin_data.get('collection_urgency', 'normal')
                    job['priority'] = 50 if urgency == 'immediate' else 25
                
                vroom_problem['jobs'].append(job)
            
            # Solve with VROOM
            trucks_list = [truck_data]
            vroom_result = self.vroom_service.optimize_vehicle_routes(
                trucks_list, all_bins, depot_data
            )
            
            if vroom_result.get('success', False) and 'routes' in vroom_result:
                route_data = vroom_result['routes'][0]
                optimized_route = [step['id'] for step in route_data.get('steps', []) 
                                 if step.get('type') == 'job']
                
                return {
                    'success': True,
                    'extended_route': optimized_route,
                    'additional_time_minutes': route_data.get('duration', 0) // 60,
                    'total_distance': route_data.get('distance', 0),
                    'optimization_method': 'vroom_extension',
                    'vroom_details': vroom_result
                }
            else:
                raise Exception(f"VROOM optimization failed: {vroom_result.get('error', 'Unknown error')}")
                
        except Exception as e:
            logger.warning(f"VROOM extension failed, using fallback: {e}")
            return {'success': False, 'error': str(e)}
    
    def _simple_route_insertion(self, truck_data: Dict, additional_bins: List[Dict],
                              remaining_bins: List[Dict], depot_data: Dict) -> Dict:
        """Simple nearest insertion for route extension"""
        try:
            # Start with remaining route
            extended_route = [b.get('id') for b in remaining_bins]
            
            # Insert additional bins using nearest insertion
            for new_bin in additional_bins:
                best_position = len(extended_route)
                min_distance_increase = float('inf')
                
                # Try inserting at each position
                for i in range(len(extended_route) + 1):
                    distance_increase = self._calculate_insertion_cost(
                        new_bin, extended_route, i, remaining_bins + additional_bins
                    )
                    
                    if distance_increase < min_distance_increase:
                        min_distance_increase = distance_increase
                        best_position = i
                
                # Insert at best position
                extended_route.insert(best_position, new_bin.get('id'))
            
            # Estimate additional time
            additional_time = len(additional_bins) * 7  # 7 minutes per additional bin (travel + service)
            
            return {
                'success': True,
                'extended_route': extended_route,
                'additional_time_minutes': additional_time,
                'optimization_method': 'nearest_insertion',
                'insertion_quality': 'good' if min_distance_increase < 5 else 'acceptable'
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _calculate_insertion_cost(self, new_bin: Dict, route: List[str], position: int,
                                all_bins: List[Dict]) -> float:
        """Calculate cost of inserting bin at given position"""
        try:
            bin_lookup = {b.get('id'): b for b in all_bins}
            
            if position == 0:
                # Insertion at start
                if len(route) > 0:
                    next_bin = bin_lookup.get(route[0])
                    if next_bin:
                        return self._calculate_distance_km(
                            new_bin.get('lat', 0), new_bin.get('lng', 0),
                            next_bin.get('lat', 0), next_bin.get('lng', 0)
                        )
                return 0
            
            elif position == len(route):
                # Insertion at end
                if len(route) > 0:
                    prev_bin = bin_lookup.get(route[-1])
                    if prev_bin:
                        return self._calculate_distance_km(
                            prev_bin.get('lat', 0), prev_bin.get('lng', 0),
                            new_bin.get('lat', 0), new_bin.get('lng', 0)
                        )
                return 0
            
            else:
                # Insertion in middle
                prev_bin = bin_lookup.get(route[position - 1])
                next_bin = bin_lookup.get(route[position])
                
                if not prev_bin or not next_bin:
                    return float('inf')
                
                # Calculate distance increase
                original_distance = self._calculate_distance_km(
                    prev_bin.get('lat', 0), prev_bin.get('lng', 0),
                    next_bin.get('lat', 0), next_bin.get('lng', 0)
                )
                
                new_distance = (
                    self._calculate_distance_km(
                        prev_bin.get('lat', 0), prev_bin.get('lng', 0),
                        new_bin.get('lat', 0), new_bin.get('lng', 0)
                    ) +
                    self._calculate_distance_km(
                        new_bin.get('lat', 0), new_bin.get('lng', 0),
                        next_bin.get('lat', 0), next_bin.get('lng', 0)
                    )
                )
                
                return new_distance - original_distance
        
        except Exception:
            return float('inf')
    
    def _calculate_distance_km(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Calculate distance between two points"""
        return self.availability_service._calculate_distance_km(lat1, lng1, lat2, lng2)
    
    def _create_post_route_extension(self, truck_data: Dict, additional_bins: List[Dict],
                                   depot_data: Dict) -> Dict:
        """Create extension for truck that finished its route"""
        try:
            # Simple TSP solution for additional bins
            if len(additional_bins) == 1:
                extended_route = [additional_bins[0].get('id')]
            else:
                # Use nearest neighbor for multiple bins
                extended_route = self._solve_simple_tsp(additional_bins)
            
            # Estimate time for extension
            travel_time = len(additional_bins) * 5  # 5 minutes travel between bins
            service_time = len(additional_bins) * 5  # 5 minutes service per bin
            return_time = 15  # 15 minutes return to depot
            
            total_time = travel_time + service_time + return_time
            
            return {
                'success': True,
                'extended_route': extended_route,
                'additional_time_minutes': total_time,
                'optimization_method': 'post_route_extension',
                'route_type': 'new_mini_route'
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _solve_simple_tsp(self, bins: List[Dict]) -> List[str]:
        """Simple TSP solution using nearest neighbor"""
        if not bins:
            return []
        
        route = []
        remaining = bins[:]
        current = remaining.pop(0)
        route.append(current.get('id'))
        
        while remaining:
            nearest_bin = min(remaining, key=lambda b: self._calculate_distance_km(
                current.get('lat', 0), current.get('lng', 0),
                b.get('lat', 0), b.get('lng', 0)
            ))
            
            route.append(nearest_bin.get('id'))
            remaining.remove(nearest_bin)
            current = nearest_bin
        
        return route
    
    def _optimize_new_routes_vroom(self, new_dispatches: List[Dict], available_trucks: List[Dict],
                                 bins_data: List[Dict], depot_data: Dict, 
                                 current_time_seconds: float) -> List[Dict]:
        """Optimize new routes for available trucks using VROOM"""
        if not new_dispatches or not available_trucks:
            return []
        
        try:
            # Collect all bins and trucks for optimization
            all_bins_to_route = []
            vroom_vehicles = []
            
            for dispatch in new_dispatches:
                truck_id = dispatch['truck_id']
                assigned_bins = dispatch['assigned_bins']
                
                # Find truck data
                truck_info = next((t for t in available_trucks if t['truck'].get('id') == truck_id), None)
                if not truck_info:
                    continue
                
                truck_data = truck_info['truck']
                
                # Add vehicle to VROOM
                available_capacity = truck_data.get('capacity', 1000) - truck_data.get('currentLoad', 0)
                
                vroom_vehicles.append({
                    'id': truck_id,
                    'start': [depot_data.get('lng', 0), depot_data.get('lat', 0)],
                    'end': [depot_data.get('lng', 0), depot_data.get('lat', 0)],
                    'capacity': [int(available_capacity)],
                    'profile': 'driving'
                })
                
                all_bins_to_route.extend(assigned_bins)
            
            if not all_bins_to_route:
                return []
            
            # Create VROOM problem
            vroom_problem = {
                'vehicles': vroom_vehicles,
                'jobs': [],
                'options': {
                    'g': True,  # Return geometry
                    'optimize': True
                }
            }
            
            # Add jobs
            for bin_data in all_bins_to_route:
                bin_load = int((bin_data.get('fillLevel', 0) / 100) * bin_data.get('capacity', 500))
                urgency = bin_data.get('collection_urgency', 'normal')
                
                job = {
                    'id': bin_data.get('id'),
                    'location': [bin_data.get('lng', 0), bin_data.get('lat', 0)],
                    'delivery': [bin_load],
                    'service': 300,  # 5 minutes
                    'priority': 100 if urgency == 'immediate' else 50 if urgency == 'soon' else 25
                }
                
                vroom_problem['jobs'].append(job)
            
            # Solve optimization
            truck_list = [d['truck'] for d in new_dispatches]
            bin_list = [d for d in bins_data if d['id'] in [b['id'] for dispatch in new_dispatches for b in dispatch['bins']]]
            vroom_result = self.vroom_service.optimize_vehicle_routes(
                truck_list, bin_list, depot_data
            )
            
            if vroom_result.get('success', False):
                return self._process_vroom_routes_result(vroom_result, new_dispatches, current_time_seconds)
            else:
                logger.warning(f"VROOM optimization failed: {vroom_result.get('error')}")
                return self._fallback_simple_routes(new_dispatches, bins_data, depot_data)
                
        except Exception as e:
            logger.error(f"Error in VROOM route optimization: {e}")
            return self._fallback_simple_routes(new_dispatches, bins_data, depot_data)
    
    def _process_vroom_routes_result(self, vroom_result: Dict, original_dispatches: List[Dict],
                                   current_time_seconds: float) -> List[Dict]:
        """Process VROOM optimization results"""
        route_results = []
        
        try:
            routes = vroom_result.get('routes', [])
            
            for route_data in routes:
                truck_id = route_data.get('vehicle')
                route_steps = route_data.get('steps', [])
                
                # Extract job IDs (bin IDs)
                optimized_route = [step['id'] for step in route_steps if step.get('type') == 'job']
                
                # Find original dispatch data
                original_dispatch = next(
                    (d for d in original_dispatches if d['truck_id'] == truck_id), 
                    None
                )
                
                route_result = {
                    'truck_id': truck_id,
                    'route_type': 'vroom_optimized',
                    'optimized_route': optimized_route,
                    'original_assignment': original_dispatch.get('assigned_bins', []) if original_dispatch else [],
                    'route_metrics': {
                        'total_distance_meters': route_data.get('distance', 0),
                        'estimated_duration_seconds': route_data.get('duration', 0),
                        'estimated_duration_minutes': route_data.get('duration', 0) // 60,
                        'service_time_minutes': len(optimized_route) * 5,
                        'total_bins': len(optimized_route)
                    },
                    'optimization_quality': self._assess_route_quality(route_data),
                    'success': True
                }
                
                route_results.append(route_result)
                
        except Exception as e:
            logger.error(f"Error processing VROOM results: {e}")
            
        return route_results
    
    def _assess_route_quality(self, route_data: Dict) -> str:
        """Assess quality of optimized route"""
        try:
            duration_hours = (route_data.get('duration', 0) // 3600)
            distance_km = (route_data.get('distance', 0) / 1000)
            
            # Simple quality assessment
            if duration_hours <= 4 and distance_km <= 100:
                return 'excellent'
            elif duration_hours <= 6 and distance_km <= 150:
                return 'good'
            elif duration_hours <= 8:
                return 'acceptable'
            else:
                return 'suboptimal'
                
        except Exception:
            return 'unknown'
    
    def _handle_critical_overrides(self, critical_overrides: List[Dict], trucks_data: List[Dict],
                                 bins_data: List[Dict], depot_data: Dict,
                                 current_time_seconds: float) -> List[Dict]:
        """Handle critical overrides for emergency collections"""
        override_results = []
        
        for override in critical_overrides:
            try:
                truck_id = override['truck_id']
                critical_bins = override['critical_bins']
                overridden_schedule = override['overridden_schedule']
                
                # Simple route for critical bins
                route = [bin_data.get('id') for bin_data in critical_bins]
                
                override_result = {
                    'truck_id': truck_id,
                    'override_type': 'critical_emergency',
                    'emergency_route': route,
                    'overridden_schedule_id': overridden_schedule,
                    'critical_bins': [b.get('id') for b in critical_bins],
                    'urgency_reason': 'Emergency collection required',
                    'estimated_completion_minutes': len(critical_bins) * 10 + 30,  # Conservative estimate
                    'success': True
                }
                
                override_results.append(override_result)
                
            except Exception as e:
                logger.error(f"Error processing critical override: {e}")
                override_results.append({
                    'truck_id': override.get('truck_id'),
                    'override_type': 'failed_override',
                    'error': str(e),
                    'success': False
                })
        
        return override_results
    
    def _fallback_simple_routes(self, dispatches: List[Dict], bins_data: List[Dict],
                              depot_data: Dict) -> List[Dict]:
        """Fallback to simple routing when VROOM fails"""
        simple_routes = []
        
        for dispatch in dispatches:
            try:
                truck_id = dispatch['truck_id']
                assigned_bins = dispatch['assigned_bins']
                
                # Simple nearest neighbor route
                route = self._solve_simple_tsp(assigned_bins)
                
                simple_route = {
                    'truck_id': truck_id,
                    'route_type': 'simple_fallback',
                    'optimized_route': route,
                    'route_metrics': {
                        'total_bins': len(route),
                        'estimated_duration_minutes': len(route) * 8  # 8 minutes per bin
                    },
                    'optimization_quality': 'basic',
                    'success': True
                }
                
                simple_routes.append(simple_route)
                
            except Exception as e:
                logger.error(f"Error in simple route fallback: {e}")
                simple_routes.append({
                    'truck_id': dispatch.get('truck_id'),
                    'route_type': 'failed_fallback',
                    'error': str(e),
                    'success': False
                })
        
        return simple_routes
    
    def _generate_optimization_summary(self, route_extensions: List[Dict], new_routes: List[Dict],
                                     overrides: List[Dict], deferred: List[Dict]) -> Dict:
        """Generate comprehensive optimization summary"""
        try:
            total_trucks_used = (
                len([r for r in route_extensions if r.get('success', False)]) +
                len([r for r in new_routes if r.get('success', False)]) +
                len([r for r in overrides if r.get('success', False)])
            )
            
            total_bins_assigned = 0
            total_bins_assigned += sum(len(r.get('additional_bins', [])) for r in route_extensions if r.get('success', False))
            total_bins_assigned += sum(len(r.get('optimized_route', [])) for r in new_routes if r.get('success', False))
            total_bins_assigned += sum(len(r.get('critical_bins', [])) for r in overrides if r.get('success', False))
            
            return {
                'total_trucks_utilized': total_trucks_used,
                'total_bins_assigned': total_bins_assigned,
                'total_bins_deferred': len(deferred),
                'route_extensions': len([r for r in route_extensions if r.get('success', False)]),
                'new_routes_created': len([r for r in new_routes if r.get('success', False)]),
                'critical_overrides': len([r for r in overrides if r.get('success', False)]),
                'optimization_efficiency': total_bins_assigned / (total_bins_assigned + len(deferred)) if (total_bins_assigned + len(deferred)) > 0 else 1.0,
                'strategy_used': 'dynamic_multi_phase',
                'optimization_status': 'completed' if total_bins_assigned > 0 else 'no_assignments_possible'
            }
            
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return {'error': str(e), 'optimization_status': 'summary_failed'}
    
    def _fallback_basic_optimization(self, trucks_data: List[Dict], bins_data: List[Dict],
                                   depot_data: Dict, current_time_seconds: float) -> Dict:
        """Basic fallback optimization when dynamic optimization fails"""
        try:
            # Simple assignment: use idle trucks for bins above threshold
            available_trucks = [t for t in trucks_data if t.get('status') == 'idle']
            urgent_bins = [b for b in bins_data if b.get('fillLevel', 0) >= b.get('threshold', 80)]
            
            if not available_trucks or not urgent_bins:
                return {
                    'fallback_type': 'no_action_needed',
                    'available_trucks': len(available_trucks),
                    'urgent_bins': len(urgent_bins)
                }
            
            # Simple 1:1 assignment
            assignments = []
            for i, truck in enumerate(available_trucks[:len(urgent_bins)]):
                if i < len(urgent_bins):
                    assignments.append({
                        'truck_id': truck.get('id'),
                        'assigned_bins': [urgent_bins[i].get('id')],
                        'route_type': 'emergency_fallback'
                    })
            
            return {
                'fallback_type': 'basic_assignment',
                'assignments': assignments,
                'trucks_used': len(assignments),
                'bins_assigned': len(assignments)
            }
            
        except Exception as e:
            return {
                'fallback_type': 'failed',
                'error': str(e)
            }