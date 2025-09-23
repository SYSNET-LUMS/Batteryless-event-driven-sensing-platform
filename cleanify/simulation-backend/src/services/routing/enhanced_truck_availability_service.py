"""
Enhanced Truck Availability Service

Handles intelligent truck availability considering:
1. Scheduled dispatches and return times
2. Current truck routes and capacity
3. Dynamic route extension for nearby bins
"""

from typing import Dict, List, Optional, Tuple
from services.external.osrm_service import OSRMService
from services.schedule_service import ScheduleService
from models.schedule import Schedule
import logging
import math

logger = logging.getLogger(__name__)

class EnhancedTruckAvailabilityService:
    """Enhanced truck availability checking with route optimization"""
    
    def __init__(self, osrm_service: OSRMService = None, schedule_service: ScheduleService = None):
        self.osrm_service = osrm_service or OSRMService()
        self.schedule_service = schedule_service or ScheduleService()
        
        # Configuration parameters
        self.route_extension_radius_km = 2.0  # Max distance to consider for route extension
        self.schedule_buffer_minutes = 30     # Buffer before scheduled dispatch
        self.capacity_safety_margin = 0.1    # 10% safety margin for capacity
        
    def get_available_trucks_enhanced(self, trucks_data: List[Dict], bins_data: List[Dict], 
                                    schedules: List[Dict], current_time_seconds: float,
                                    depot_data: Optional[Dict] = None) -> Dict:
        """
        Enhanced truck availability analysis
        
        Returns:
            Dict with available, busy, scheduled, and route-extendable trucks
        """
        try:
            result = {
                'available_trucks': [],      # Fully available trucks
                'busy_trucks': [],          # Currently on routes
                'scheduled_trucks': [],     # Reserved for upcoming schedules
                'route_extendable': [],     # Busy trucks that can extend routes
                'availability_summary': {}
            }
            
            current_time_min = current_time_seconds // 60
            
            # Get reserved trucks for upcoming schedules
            reserved_truck_ids = self._get_reserved_truck_ids(schedules, current_time_seconds)
            
            # Analyze each truck
            for truck in trucks_data:
                truck_id = truck.get('id')
                truck_status = truck.get('status', 'idle')
                
                # Check if truck is reserved for upcoming schedule
                if truck_id in reserved_truck_ids:
                    result['scheduled_trucks'].append({
                        'truck': truck,
                        'schedule_info': reserved_truck_ids[truck_id],
                        'available_until': reserved_truck_ids[truck_id]['dispatch_time_min']
                    })
                    continue
                
                # Analyze truck availability based on current status
                availability_info = self._analyze_truck_availability(
                    truck, bins_data, current_time_seconds, depot_data
                )
                
                if availability_info['status'] == 'available':
                    result['available_trucks'].append({
                        'truck': truck,
                        'availability_info': availability_info
                    })
                elif availability_info['status'] == 'busy':
                    result['busy_trucks'].append({
                        'truck': truck,
                        'availability_info': availability_info
                    })
                    
                    # Check if this busy truck can extend its route
                    extension_info = self._check_route_extension_possibility(
                        truck, bins_data, current_time_seconds
                    )
                    if extension_info['can_extend']:
                        result['route_extendable'].append({
                            'truck': truck,
                            'extension_info': extension_info,
                            'current_route': truck.get('route', [])
                        })
            
            # Generate summary
            result['availability_summary'] = {
                'total_trucks': len(trucks_data),
                'available_count': len(result['available_trucks']),
                'busy_count': len(result['busy_trucks']),
                'scheduled_count': len(result['scheduled_trucks']),
                'route_extendable_count': len(result['route_extendable'])
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error in enhanced truck availability analysis: {e}")
            return {
                'available_trucks': [{'truck': t} for t in trucks_data if t.get('status') == 'idle'],
                'busy_trucks': [],
                'scheduled_trucks': [],
                'route_extendable': [],
                'availability_summary': {'total_trucks': len(trucks_data), 'error': str(e)}
            }
    
    def _get_reserved_truck_ids(self, schedules: List[Dict], current_time_seconds: float) -> Dict:
        """Get trucks reserved for upcoming schedules with timing info"""
        reserved_trucks = {}
        
        for schedule_data in schedules:
            if schedule_data.get('status') != 'pending':
                continue
                
            try:
                schedule = Schedule(**schedule_data)
                truck_id = schedule_data['truck_id']
                
                # Check if truck should be reserved for upcoming schedule
                if schedule.should_reserve_truck(current_time_seconds):
                    dispatch_time_min = schedule.scheduled_time // 60 if schedule.scheduled_time else 0
                    time_until_dispatch = dispatch_time_min - (current_time_seconds // 60)
                    
                    reserved_trucks[truck_id] = {
                        'schedule_id': schedule_data['id'],
                        'dispatch_time_min': dispatch_time_min,
                        'time_until_dispatch': time_until_dispatch,
                        'target_bins': schedule_data.get('target_bin_ids', []),
                        'reason': f'Reserved for schedule in {time_until_dispatch:.0f} minutes'
                    }
                    
            except Exception as e:
                logger.warning(f"Error processing schedule {schedule_data.get('id')}: {e}")
                
        return reserved_trucks
    
    def _analyze_truck_availability(self, truck: Dict, bins_data: List[Dict], 
                                  current_time_seconds: float, depot_data: Optional[Dict]) -> Dict:
        """Analyze individual truck availability"""
        truck_status = truck.get('status', 'idle')
        truck_id = truck.get('id')
        
        if truck_status == 'idle':
            return {
                'status': 'available',
                'reason': 'Truck is idle and ready for dispatch',
                'available_capacity': truck.get('capacity', 1000) - truck.get('currentLoad', 0),
                'estimated_availability': 0  # Available now
            }
        
        elif truck_status in ['collecting', 'traveling', 'returning']:
            # Calculate when truck will be available again
            availability_time = self._estimate_truck_availability_time(truck, depot_data)
            
            return {
                'status': 'busy',
                'reason': f'Truck is {truck_status}',
                'current_route': truck.get('route', []),
                'route_index': truck.get('routeIndex', 0),
                'estimated_availability': availability_time,
                'current_capacity': truck.get('capacity', 1000) - truck.get('currentLoad', 0)
            }
        
        else:
            return {
                'status': 'unavailable',
                'reason': f'Truck status: {truck_status}',
                'estimated_availability': float('inf')
            }
    
    def _estimate_truck_availability_time(self, truck: Dict, depot_data: Optional[Dict]) -> float:
        """Estimate when truck will be available (in minutes)"""
        try:
            # Get current route information
            route = truck.get('route', [])
            route_index = truck.get('routeIndex', 0)
            return_route = truck.get('returnRoute', [])
            return_route_index = truck.get('returnRouteIndex', 0)
            
            # Estimate remaining collection time
            remaining_collections = len(route) - route_index
            collection_time_per_bin = 5  # minutes per bin collection
            
            # Estimate return journey time
            return_time = 0
            if return_route:
                # Use return route if available
                remaining_return = len(return_route) - return_route_index
                return_time = remaining_return * 2  # Estimate 2 minutes per route segment
            elif depot_data and route:
                # Estimate return time from current/last bin to depot
                last_bin_pos = route[-1] if route else truck
                return_time = self._estimate_travel_time(last_bin_pos, depot_data)
            
            total_time = (remaining_collections * collection_time_per_bin) + return_time
            return max(0, total_time)
            
        except Exception as e:
            logger.warning(f"Error estimating truck availability: {e}")
            return 60  # Default 1 hour estimate
    
    def _check_route_extension_possibility(self, truck: Dict, bins_data: List[Dict], 
                                         current_time_seconds: float) -> Dict:
        """Check if a busy truck can extend its route to collect additional bins"""
        try:
            # Get truck's current route information
            route = truck.get('route', [])
            current_load = truck.get('currentLoad', 0)
            capacity = truck.get('capacity', 1000)
            route_index = truck.get('routeIndex', 0)
            
            # Calculate remaining capacity with safety margin
            remaining_capacity = (capacity - current_load) * (1 - self.capacity_safety_margin)
            
            if remaining_capacity <= 0 or not route:
                return {'can_extend': False, 'reason': 'No remaining capacity or route'}
            
            # Get truck's current or next bin location
            if route_index < len(route):
                current_target_id = route[route_index]
            else:
                current_target_id = route[-1] if route else None
            
            if not current_target_id:
                return {'can_extend': False, 'reason': 'No valid current target'}
            
            # Find current target bin
            current_target_bin = next(
                (b for b in bins_data if b.get('id') == current_target_id), 
                None
            )
            
            if not current_target_bin:
                return {'can_extend': False, 'reason': 'Current target bin not found'}
            
            # Find nearby bins that need collection and fit in remaining capacity
            nearby_bins = self._find_nearby_bins_for_extension(
                current_target_bin, bins_data, remaining_capacity, 
                set(route), current_time_seconds
            )
            
            if nearby_bins:
                total_additional_load = sum(
                    (bin_data['fillLevel'] / 100) * bin_data['capacity'] 
                    for bin_data in nearby_bins
                )
                
                return {
                    'can_extend': True,
                    'nearby_bins': nearby_bins,
                    'additional_load': total_additional_load,
                    'remaining_capacity_after': remaining_capacity - total_additional_load,
                    'extension_count': len(nearby_bins)
                }
            else:
                return {
                    'can_extend': False, 
                    'reason': 'No suitable nearby bins found'
                }
                
        except Exception as e:
            logger.error(f"Error checking route extension: {e}")
            return {'can_extend': False, 'reason': f'Error: {str(e)}'}
    
    def _find_nearby_bins_for_extension(self, reference_bin: Dict, all_bins: List[Dict], 
                                      remaining_capacity: float, current_route_ids: set,
                                      current_time_seconds: float) -> List[Dict]:
        """Find bins near the reference bin that can be added to the route"""
        nearby_bins = []
        
        ref_lat = reference_bin.get('lat')
        ref_lng = reference_bin.get('lng')
        
        if not ref_lat or not ref_lng:
            return nearby_bins
        
        for bin_data in all_bins:
            # Skip if already in current route
            if bin_data.get('id') in current_route_ids:
                continue
            
            # Check if bin needs collection
            if not self._bin_needs_collection(bin_data, current_time_seconds):
                continue
            
            # Check distance
            distance_km = self._calculate_distance_km(
                ref_lat, ref_lng, 
                bin_data.get('lat', 0), bin_data.get('lng', 0)
            )
            
            if distance_km > self.route_extension_radius_km:
                continue
            
            # Check capacity
            bin_load = (bin_data['fillLevel'] / 100) * bin_data['capacity']
            if bin_load > remaining_capacity:
                continue
            
            nearby_bins.append(bin_data)
            remaining_capacity -= bin_load
            
            # Limit to reasonable number of additional bins
            if len(nearby_bins) >= 3:
                break
        
        return nearby_bins
    
    def _bin_needs_collection(self, bin_data: Dict, current_time_seconds: float) -> bool:
        """Check if bin needs collection based on threshold or urgency"""
        fill_level = bin_data.get('fillLevel', 0)
        threshold = bin_data.get('dynamic_threshold', bin_data.get('threshold', 80))
        
        # Immediate collection if above threshold
        if fill_level >= threshold:
            return True
        
        # Check if bin will reach threshold soon
        fill_rate = bin_data.get('fillRate', 0)
        if fill_rate > 0:
            capacity = bin_data.get('capacity', 500)
            hours_to_threshold = ((threshold - fill_level) / 100) * capacity / fill_rate
            
            # Consider for collection if reaches threshold within 2 hours
            if hours_to_threshold <= 2:
                return True
        
        return False
    
    def _calculate_distance_km(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Calculate distance between two points in kilometers"""
        try:
            # Haversine formula
            R = 6371  # Earth radius in km
            
            dlat = math.radians(lat2 - lat1)
            dlng = math.radians(lng2 - lng1)
            
            a = (math.sin(dlat/2) * math.sin(dlat/2) + 
                 math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * 
                 math.sin(dlng/2) * math.sin(dlng/2))
            
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            
            return R * c
            
        except Exception:
            return float('inf')
    
    def _estimate_travel_time(self, from_location: Dict, to_location: Dict) -> float:
        """Estimate travel time between locations in minutes"""
        try:
            distance_km = self._calculate_distance_km(
                from_location.get('lat', 0), from_location.get('lng', 0),
                to_location.get('lat', 0), to_location.get('lng', 0)
            )
            
            # Assume average speed of 40 km/h in city
            average_speed_kmh = 40
            time_hours = distance_km / average_speed_kmh
            return time_hours * 60  # Convert to minutes
            
        except Exception:
            return 30  # Default 30 minutes
    
    def get_optimal_truck_assignments(self, availability_result: Dict, bins_needing_collection: List[Dict],
                                    depot_data: Optional[Dict] = None) -> Dict:
        """
        Generate optimal truck assignments considering all availability types
        
        Returns assignments prioritizing:
        1. Route extensions for busy trucks (most efficient)
        2. Available trucks for new routes
        3. Avoid using scheduled trucks unless critical
        """
        assignments = {
            'route_extensions': [],     # Extend existing routes
            'new_dispatches': [],      # New routes for available trucks
            'critical_overrides': [],  # Use scheduled trucks for emergencies
            'deferred_collections': [] # Bins that must wait
        }
        
        try:
            # Sort bins by urgency
            sorted_bins = sorted(bins_needing_collection, 
                               key=lambda b: (b.get('fillLevel', 0), -self._time_to_overflow(b)), 
                               reverse=True)
            
            assigned_bins = set()
            
            # Phase 1: Extend existing routes where possible
            for extendable in availability_result['route_extendable']:
                if not sorted_bins:
                    break
                    
                truck = extendable['truck']
                extension_info = extendable['extension_info']
                available_bins = extension_info.get('nearby_bins', [])
                
                # Find intersection of available bins and bins needing collection
                route_extensions = []
                for bin_data in available_bins:
                    if bin_data.get('id') not in assigned_bins:
                        for needed_bin in sorted_bins:
                            if needed_bin.get('id') == bin_data.get('id'):
                                route_extensions.append(needed_bin)
                                assigned_bins.add(needed_bin.get('id'))
                                break
                
                if route_extensions:
                    assignments['route_extensions'].append({
                        'truck_id': truck.get('id'),
                        'additional_bins': route_extensions,
                        'current_route': truck.get('route', []),
                        'reason': f'Route extension - {len(route_extensions)} additional bins'
                    })
            
            # Phase 2: Assign available trucks to remaining bins
            available_trucks = availability_result['available_trucks']
            unassigned_bins = [b for b in sorted_bins if b.get('id') not in assigned_bins]
            
            for truck_info in available_trucks:
                if not unassigned_bins:
                    break
                    
                truck = truck_info['truck']
                truck_capacity = truck.get('capacity', 1000) - truck.get('currentLoad', 0)
                
                # Assign bins to this truck within capacity
                truck_bins = []
                remaining_capacity = truck_capacity
                
                for bin_data in unassigned_bins[:]:  # Copy to allow removal during iteration
                    bin_load = (bin_data['fillLevel'] / 100) * bin_data['capacity']
                    
                    if bin_load <= remaining_capacity:
                        truck_bins.append(bin_data)
                        assigned_bins.add(bin_data.get('id'))
                        unassigned_bins.remove(bin_data)
                        remaining_capacity -= bin_load
                
                if truck_bins:
                    assignments['new_dispatches'].append({
                        'truck_id': truck.get('id'),
                        'assigned_bins': truck_bins,
                        'route': [b.get('id') for b in truck_bins],
                        'total_load': sum((b['fillLevel'] / 100) * b['capacity'] for b in truck_bins),
                        'reason': f'New dispatch - {len(truck_bins)} bins'
                    })
            
            # Phase 3: Check if critical bins need scheduled truck override
            unassigned_bins = [b for b in sorted_bins if b.get('id') not in assigned_bins]
            critical_bins = [b for b in unassigned_bins if b.get('fillLevel', 0) >= 95]
            
            if critical_bins and availability_result['scheduled_trucks']:
                # Consider using scheduled trucks for emergency
                for scheduled_info in availability_result['scheduled_trucks']:
                    if not critical_bins:
                        break
                        
                    truck = scheduled_info['truck']
                    schedule_info = scheduled_info['schedule_info']
                    
                    # Only override if schedule is more than 30 minutes away
                    if schedule_info['time_until_dispatch'] > 30:
                        assignments['critical_overrides'].append({
                            'truck_id': truck.get('id'),
                            'critical_bins': critical_bins[:2],  # Max 2 critical bins
                            'overridden_schedule': schedule_info['schedule_id'],
                            'reason': f'Emergency override - {len(critical_bins[:2])} critical bins'
                        })
                        
                        # Remove assigned critical bins
                        for bin_data in critical_bins[:2]:
                            assigned_bins.add(bin_data.get('id'))
                        critical_bins = critical_bins[2:]
            
            # Phase 4: Mark remaining bins as deferred
            final_unassigned = [b for b in sorted_bins if b.get('id') not in assigned_bins]
            assignments['deferred_collections'] = [{
                'bin_id': b.get('id'),
                'fill_level': b.get('fillLevel', 0),
                'reason': 'No available trucks - will dispatch when truck becomes available',
                'estimated_wait_time': self._estimate_next_truck_availability(availability_result)
            } for b in final_unassigned]
            
            return assignments
            
        except Exception as e:
            logger.error(f"Error in optimal truck assignments: {e}")
            return assignments
    
    def _time_to_overflow(self, bin_data: Dict) -> float:
        """Calculate time to overflow in hours"""
        fill_level = bin_data.get('fillLevel', 0)
        fill_rate = bin_data.get('fillRate', 3.5)
        capacity = bin_data.get('capacity', 500)
        
        if fill_rate <= 0 or fill_level >= 100:
            return 0
            
        remaining_capacity = ((100 - fill_level) / 100) * capacity
        return remaining_capacity / fill_rate
    
    def _estimate_next_truck_availability(self, availability_result: Dict) -> float:
        """Estimate when next truck will become available (minutes)"""
        min_availability = float('inf')
        
        # Check busy trucks
        for busy_info in availability_result['busy_trucks']:
            availability_time = busy_info['availability_info'].get('estimated_availability', float('inf'))
            min_availability = min(min_availability, availability_time)
        
        # Check scheduled trucks
        for scheduled_info in availability_result['scheduled_trucks']:
            # Assume truck available after completing schedule (estimated 2 hours)
            schedule_time = scheduled_info.get('available_until', 0)
            estimated_completion = schedule_time + 120  # 2 hours for schedule completion
            min_availability = min(min_availability, estimated_completion)
        
        return min_availability if min_availability != float('inf') else 60  # Default 1 hour