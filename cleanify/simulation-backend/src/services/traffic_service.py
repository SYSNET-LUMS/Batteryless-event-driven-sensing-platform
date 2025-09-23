from typing import Dict, Optional, List, Tuple
from config.constants import BIN_TRAFFIC_PROFILES
from services.routing.enhanced_truck_availability_service import EnhancedTruckAvailabilityService
from services.routing.dynamic_route_optimizer import DynamicRouteOptimizer
import logging

logger = logging.getLogger(__name__)

class TrafficManager:
    """Enhanced traffic management service with predictive capabilities and dynamic routing"""
    
    def __init__(self):
        self.normal_traffic_threshold = 3.0
        self.min_travel_savings = 5
        self.safety_buffer = 15
        
        self.critical_fill_threshold = 95
        self.overflow_threshold = 100
        self.max_wait_time = 150

        # Enhanced traffic density with more granular patterns
        self.traffic_density = {
            0: 1.0, 1: 1.2, 2: 1.5, 3: 1.2, 4: 1.0, 5: 1.5, 6: 2.0,
            7: 6.0, 8: 10.0, 9: 8.0,
            10: 3.0, 11: 2.0, 12: 1.5, 13: 1.0, 14: 1.5, 15: 2.0,
            16: 5.0, 17: 10.0, 18: 7.0, 19: 4.0,
            20: 3.0, 21: 2.0, 22: 1.5, 23: 1.2
        }
        
        # Traffic pattern classification thresholds (inspired by abc.py but enhanced)
        self.heavy_traffic_threshold = 5.0
        self.moderate_traffic_threshold = 3.0
        
        # Initialize enhanced services
        self.enhanced_availability_service = EnhancedTruckAvailabilityService()
        self.dynamic_optimizer = DynamicRouteOptimizer()
        
        # Enhanced routing features
        self.enable_dynamic_routing = True
        self.enable_predictive_dispatch = True
    
    def get_bin_specific_density(self, bin_id: str, time_min: int) -> float:
        """Get traffic density for specific bin location"""
        hour = (time_min // 60) % 24
        
        if bin_id in BIN_TRAFFIC_PROFILES:
            profile = BIN_TRAFFIC_PROFILES[bin_id]
            density = profile['pattern'].get(hour, 1.0)
            return density
        
        return self.traffic_density.get(hour, 1.0)
    
    def find_time_to_normal_traffic_for_bin(self, current_min: int, bin_id: str) -> int:
        """Find minutes until next normal traffic period for specific bin"""
        profile = BIN_TRAFFIC_PROFILES.get(bin_id)
        if not profile:
            return self.find_time_to_normal_traffic(current_min)
        
        for minutes_ahead in range(1, 24 * 60):
            future_min = current_min + minutes_ahead
            future_hour = (future_min // 60) % 24
            
            bin_density = profile['pattern'].get(future_hour, 1.0)
            
            if bin_density <= self.normal_traffic_threshold:
                return minutes_ahead
        
        return 0
    
    def find_time_to_normal_traffic(self, current_min: int) -> int:
        """Find minutes until next normal traffic period using general traffic"""
        for minutes_ahead in range(1, 24 * 60):
            future_min = current_min + minutes_ahead
            future_hour = (future_min // 60) % 24
            
            if self.traffic_density[future_hour] <= self.normal_traffic_threshold:
                return minutes_ahead
        
        return 0
    
    def calculate_dispatch_time(self, time_to_overflow_min: float, base_travel_min: float, 
                               current_time_min: int, bin_id: Optional[str] = None, 
                               bin_fill_level: Optional[float] = None, 
                               use_predictive_logic: bool = True) -> Dict:
        """
        Enhanced dispatch calculation with predictive capabilities
        
        Args:
            time_to_overflow_min: Time until bin overflows
            base_travel_min: Base travel time without traffic
            current_time_min: Current time in minutes from midnight
            bin_id: Optional bin ID for location-specific traffic
            bin_fill_level: Optional current fill level
            use_predictive_logic: Whether to use enhanced predictive dispatch logic
        """
        
        # Safety checks (unchanged - these are critical)
        if bin_fill_level is not None and bin_fill_level >= self.overflow_threshold:
            return {
                'dispatch': 'now',
                'delay_min': 0,
                'reason': f'EMERGENCY: Bin overflowing at {bin_fill_level}%'
            }
        
        if bin_fill_level is not None and bin_fill_level >= self.critical_fill_threshold:
            return {
                'dispatch': 'now',
                'delay_min': 0,
                'reason': f'CRITICAL: Bin at {bin_fill_level}% - safety override'
            }
        
        if time_to_overflow_min <= 0:
            return {
                'dispatch': 'now',
                'delay_min': 0,
                'reason': 'EMERGENCY: Bin already overflowing (time calculation)'
            }
        
        # Enhanced: Try predictive logic first if enabled and bin_id available
        if use_predictive_logic and bin_id:
            try:
                predictive_result = self.find_optimal_dispatch_before_heavy_traffic(
                    current_time_min, bin_id, base_travel_min, time_to_overflow_min
                )
                
                # If predictive logic gives a clear recommendation, use it
                if 'fuel_savings_min' in predictive_result and predictive_result['fuel_savings_min'] > 0:
                    logger.info(f"Using predictive dispatch for bin {bin_id}: {predictive_result['reason']}")
                    return predictive_result
                elif predictive_result.get('dispatch') == 'now' and 'overflow' in predictive_result.get('reason', '').lower():
                    return predictive_result  # Safety override from predictive logic
                    
            except Exception as e:
                logger.warning(f"Predictive dispatch failed for bin {bin_id}, falling back to standard logic: {e}")
        
        # Standard logic (enhanced with better traffic classification)
        # Get current traffic density
        if bin_id:
            current_density = self.get_bin_specific_density(bin_id, current_time_min)
        else:
            current_density = self.get_density_at_time(current_time_min)
        
        # Calculate travel time with current traffic
        adjusted_now = base_travel_min * current_density
        
        overflow_deadline = adjusted_now + self.safety_buffer
        if time_to_overflow_min <= overflow_deadline:
            return {
                'dispatch': 'now',
                'delay_min': 0,
                'reason': f'OVERFLOW RISK: Only {time_to_overflow_min:.1f}min until overflow',
                'current_traffic_level': self.classify_traffic_level(current_density)
            }
        
        # Enhanced: Check if traffic is already in optimal range
        current_level = self.classify_traffic_level(current_density)
        if current_level == 'light':
            return {
                'dispatch': 'now', 
                'delay_min': 0, 
                'reason': 'Traffic already light - optimal time to dispatch',
                'current_traffic_level': current_level
            }
        
        # Enhanced: Look for better traffic conditions
        if bin_id:
            wait_for_normal_min = self.find_time_to_normal_traffic_for_bin(current_time_min, bin_id)
            # Also check for light traffic windows
            light_window = self.find_next_light_traffic_window(current_time_min, bin_id, 15)
            
            if light_window and light_window['time_until_start'] < wait_for_normal_min:
                wait_for_normal_min = light_window['time_until_start']
        else:
            wait_for_normal_min = self.find_time_to_normal_traffic(current_time_min)
        
        if wait_for_normal_min == 0:
            return {
                'dispatch': 'now', 
                'delay_min': 0, 
                'reason': 'Traffic never becomes normal',
                'current_traffic_level': current_level
            }
        
        if wait_for_normal_min > self.max_wait_time:
            return {
                'dispatch': 'now',
                'delay_min': 0,
                'reason': f'Max wait time exceeded ({wait_for_normal_min}min > {self.max_wait_time}min)',
                'current_traffic_level': current_level
            }
        
        # Calculate travel time if we wait
        predicted_time = current_time_min + wait_for_normal_min
        if bin_id:
            predicted_density = self.get_bin_specific_density(bin_id, predicted_time)
        else:
            predicted_density = self.get_density_at_time(predicted_time)
        predicted_adjusted = base_travel_min * predicted_density
        
        # Calculate potential savings
        travel_savings = adjusted_now - predicted_adjusted
        total_time_if_wait = predicted_adjusted + wait_for_normal_min
        
        # Safety check: waiting would cause overflow
        safety_deadline = time_to_overflow_min - self.safety_buffer
        if total_time_if_wait > safety_deadline:
            return {
                'dispatch': 'now',
                'delay_min': 0,
                'reason': f'Waiting would cause overflow (deadline: {safety_deadline:.1f}min)',
                'current_traffic_level': current_level
            }
        
        # Enhanced decision logic with traffic level awareness
        savings_sufficient = travel_savings >= self.min_travel_savings
        no_overflow_risk = time_to_overflow_min > total_time_if_wait + self.safety_buffer
        wait_worthwhile = travel_savings > wait_for_normal_min * 0.1
        
        # Enhanced: Consider traffic level transitions
        future_level = self.classify_traffic_level(predicted_density)
        traffic_improvement = (current_level == 'heavy' and future_level in ['light', 'moderate']) or \
                            (current_level == 'moderate' and future_level == 'light')
        
        if savings_sufficient and no_overflow_risk and wait_worthwhile and traffic_improvement:
            optimal_delay = min(
                wait_for_normal_min,
                int(time_to_overflow_min - predicted_adjusted - self.safety_buffer),
                self.max_wait_time
            )
            return {
                'dispatch': 'wait',
                'delay_min': optimal_delay,
                'reason': f'Wait {optimal_delay}min: {current_level}→{future_level} traffic (save ~{travel_savings:.0f}min)',
                'current_traffic_level': current_level,
                'future_traffic_level': future_level,
                'fuel_savings_min': round(travel_savings, 1)
            }
        else:
            reason_parts = []
            if not savings_sufficient:
                reason_parts.append(f"insufficient savings ({travel_savings:.1f}min)")
            if not no_overflow_risk:
                reason_parts.append("overflow risk")
            if not wait_worthwhile:
                reason_parts.append("wait cost too high")
            if not traffic_improvement:
                reason_parts.append(f"no significant traffic improvement ({current_level}→{future_level})")
                
            return {
                'dispatch': 'now', 
                'delay_min': 0, 
                'reason': f'Not worth waiting: {", ".join(reason_parts)}',
                'current_traffic_level': current_level
            }
    
    def get_density_at_time(self, time_min: int) -> float:
        """Get traffic density at a given time in minutes from midnight"""
        hour = (time_min // 60) % 24
        next_hour = (hour + 1) % 24
        minutes_into_hour = time_min % 60
        
        current_density = self.traffic_density[hour]
        next_density = self.traffic_density[next_hour]
        
        # Linear interpolation between hours
        interpolated = current_density + (next_density - current_density) * (minutes_into_hour / 60)
        return interpolated
    
    def classify_traffic_level(self, density: float) -> str:
        """
        Classify traffic density into categories (enhanced from abc.py concepts)
        
        Args:
            density: Traffic density multiplier
            
        Returns:
            Traffic level: 'light', 'moderate', or 'heavy'
        """
        if density <= self.normal_traffic_threshold:
            return 'light'
        elif density >= self.heavy_traffic_threshold:
            return 'heavy'
        else:
            return 'moderate'
    
    def predict_traffic_transition_times(self, current_time_min: int, bin_id: str = None, 
                                       prediction_window_hours: int = 4) -> List[Dict]:
        """
        Predict upcoming traffic level transitions (inspired by abc.py but enhanced)
        
        Args:
            current_time_min: Current time in minutes from midnight
            bin_id: Optional bin ID for location-specific traffic
            prediction_window_hours: Hours to look ahead
            
        Returns:
            List of traffic transition events with timing and levels
        """
        transitions = []
        current_level = None
        
        end_time = current_time_min + (prediction_window_hours * 60)
        
        for time_offset in range(0, prediction_window_hours * 60, 15):  # 15-minute intervals
            future_time = current_time_min + time_offset
            
            if bin_id:
                density = self.get_bin_specific_density(bin_id, future_time)
            else:
                density = self.get_density_at_time(future_time)
            
            level = self.classify_traffic_level(density)
            
            # Detect transitions
            if level != current_level:
                transitions.append({
                    'time_min': future_time,
                    'time_offset': time_offset,
                    'from_level': current_level,
                    'to_level': level,
                    'density': density,
                    'hour': int(future_time // 60) % 24
                })
                current_level = level
        
        return transitions
    
    def find_next_light_traffic_window(self, current_time_min: int, bin_id: str = None,
                                     min_duration_min: int = 30) -> Optional[Dict]:
        """
        Find the next sustained light traffic window (enhanced version of abc.py concept)
        
        Args:
            current_time_min: Current time in minutes
            bin_id: Optional bin ID for location-specific traffic
            min_duration_min: Minimum duration of light traffic window
            
        Returns:
            Dict with window start time, duration, and traffic info, or None if not found
        """
        for time_offset in range(0, 24 * 60, 15):  # Check next 24 hours in 15-min intervals
            window_start = current_time_min + time_offset
            window_duration = 0
            
            # Check how long light traffic continues from this point
            for duration_check in range(0, 4 * 60, 15):  # Check up to 4 hours
                check_time = window_start + duration_check
                
                if bin_id:
                    density = self.get_bin_specific_density(bin_id, check_time)
                else:
                    density = self.get_density_at_time(check_time)
                
                if self.classify_traffic_level(density) == 'light':
                    window_duration += 15
                else:
                    break  # Traffic is no longer light
            
            # If we found a window of sufficient duration
            if window_duration >= min_duration_min:
                return {
                    'start_time_min': window_start,
                    'duration_min': window_duration,
                    'time_until_start': time_offset,
                    'avg_density': self._calculate_average_density(window_start, window_duration, bin_id),
                    'level': 'light'
                }
        
        return None  # No suitable light traffic window found in next 24 hours
    
    def find_optimal_dispatch_before_heavy_traffic(self, current_time_min: int, bin_id: str,
                                                  base_travel_min: float, 
                                                  time_to_overflow_min: float) -> Dict:
        """
        Enhanced dispatch timing to avoid heavy traffic (core concept from abc.py but improved)
        
        This implements the key insight from abc.py: dispatch before heavy traffic hits,
        but uses our sophisticated traffic system
        
        Args:
            current_time_min: Current time in minutes
            bin_id: Bin identifier for location-specific traffic
            base_travel_min: Base travel time without traffic
            time_to_overflow_min: Time until bin overflows
            
        Returns:
            Dispatch recommendation with timing and reasoning
        """
        try:
            # Get traffic transitions for the next few hours
            transitions = self.predict_traffic_transition_times(current_time_min, bin_id, 6)
            
            # Find upcoming heavy traffic periods
            heavy_traffic_starts = [
                t for t in transitions 
                if t['to_level'] == 'heavy' and t['time_offset'] > 0
            ]
            
            if not heavy_traffic_starts:
                # No heavy traffic expected, use standard logic (disable predictive to avoid recursion)
                return self.calculate_dispatch_time(time_to_overflow_min, base_travel_min, 
                                                  current_time_min, bin_id, None, use_predictive_logic=False)
            
            # Find the earliest heavy traffic period
            next_heavy_traffic = min(heavy_traffic_starts, key=lambda x: x['time_offset'])
            
            # Calculate when we should dispatch to arrive before heavy traffic
            heavy_start_time = next_heavy_traffic['time_min']
            arrival_before_heavy = heavy_start_time - 10  # Arrive 10 minutes before heavy traffic
            
            # Work backwards to find dispatch time
            current_density = self.get_bin_specific_density(bin_id, current_time_min)
            current_travel_time = base_travel_min * current_density
            
            # Dispatch time to arrive before heavy traffic
            optimal_dispatch_time = arrival_before_heavy - current_travel_time
            dispatch_delay = max(0, optimal_dispatch_time - current_time_min)
            
            # Safety checks
            total_time_with_delay = dispatch_delay + current_travel_time
            safety_deadline = time_to_overflow_min - self.safety_buffer
            
            if total_time_with_delay > safety_deadline:
                # Can't wait, would cause overflow
                return {
                    'dispatch': 'now',
                    'delay_min': 0,
                    'reason': f'Cannot wait for optimal timing - would cause overflow',
                    'heavy_traffic_warning': f"Heavy traffic starts at {next_heavy_traffic['hour']:02d}:{(heavy_start_time % 60):02d}"
                }
            
            if dispatch_delay > self.max_wait_time:
                # Wait time too long, use standard logic (disable predictive to avoid recursion)
                return self.calculate_dispatch_time(time_to_overflow_min, base_travel_min, 
                                                  current_time_min, bin_id, None, use_predictive_logic=False)
            
            # Calculate potential fuel savings
            heavy_density = next_heavy_traffic['density']
            heavy_travel_time = base_travel_min * heavy_density
            fuel_savings = heavy_travel_time - current_travel_time
            
            if fuel_savings >= self.min_travel_savings and dispatch_delay > 0:
                return {
                    'dispatch': 'wait',
                    'delay_min': int(dispatch_delay),
                    'reason': f"Dispatch in {int(dispatch_delay)}min to avoid heavy traffic at {next_heavy_traffic['hour']:02d}:{(heavy_start_time % 60):02d}",
                    'fuel_savings_min': round(fuel_savings, 1),
                    'heavy_traffic_start': heavy_start_time,
                    'arrival_time': arrival_before_heavy
                }
            else:
                return {
                    'dispatch': 'now',
                    'delay_min': 0,
                    'reason': 'Minimal fuel savings from waiting - dispatch now',
                    'heavy_traffic_warning': f"Heavy traffic starts at {next_heavy_traffic['hour']:02d}:{(heavy_start_time % 60):02d}"
                }
                
        except Exception as e:
            logger.error(f"Error in optimal dispatch calculation: {e}")
            # Use standard logic without predictive to avoid recursion
            return self.calculate_dispatch_time(time_to_overflow_min, base_travel_min, 
                                              current_time_min, bin_id, None, use_predictive_logic=False)
    
    def _calculate_average_density(self, start_time_min: int, duration_min: int, 
                                 bin_id: str = None) -> float:
        """Calculate average traffic density over a time window"""
        total_density = 0.0
        sample_count = 0
        
        for time_offset in range(0, duration_min, 15):
            check_time = start_time_min + time_offset
            
            if bin_id:
                density = self.get_bin_specific_density(bin_id, check_time)
            else:
                density = self.get_density_at_time(check_time)
            
            total_density += density
            sample_count += 1
        
        return total_density / sample_count if sample_count > 0 else 1.0
    
    def get_traffic_insights_for_bin(self, bin_id: str, current_time_min: int) -> Dict:
        """
        Get comprehensive traffic insights for a specific bin (new feature)
        
        This provides detailed traffic analysis that can be used by other services
        """
        try:
            current_density = self.get_bin_specific_density(bin_id, current_time_min)
            current_level = self.classify_traffic_level(current_density)
            
            # Get upcoming transitions
            transitions = self.predict_traffic_transition_times(current_time_min, bin_id, 6)
            
            # Find next light traffic window
            light_window = self.find_next_light_traffic_window(current_time_min, bin_id)
            
            # Find upcoming heavy traffic
            heavy_periods = [t for t in transitions if t['to_level'] == 'heavy']
            
            return {
                'bin_id': bin_id,
                'current_time_hour': int(current_time_min // 60) % 24,
                'current_density': current_density,
                'current_level': current_level,
                'next_light_window': light_window,
                'upcoming_heavy_periods': heavy_periods[:3],  # Next 3 heavy periods
                'transitions_next_6h': transitions,
                'analysis_timestamp': current_time_min
            }
        
        except Exception as e:
            logger.error(f"Error getting traffic insights for bin {bin_id}: {e}")
            return {
                'bin_id': bin_id,
                'error': str(e),
                'current_level': 'unknown'
            }
    
    def get_enhanced_routing_recommendations(self, trucks_data: List[Dict], bins_data: List[Dict],
                                           schedules: List[Dict], depot_data: Dict,
                                           current_time_seconds: float) -> Dict:
        """
        NEW ENHANCED METHOD: Get comprehensive routing recommendations with smart truck availability
        
        This is the main method that implements the user's requirements:
        1. Only consider available trucks (checking schedules and return times)
        2. Allow route extension for trucks already on trips when nearby bins need collection
        
        Returns detailed routing recommendations with availability analysis
        """
        try:
            if not self.enable_dynamic_routing:
                logger.info("Dynamic routing disabled, using basic recommendations")
                return self._get_basic_routing_recommendations(trucks_data, bins_data, current_time_seconds)
            
            logger.info(f"Starting enhanced routing analysis for {len(trucks_data)} trucks and {len(bins_data)} bins")
            
            # Use the dynamic optimizer to get comprehensive routing solution
            routing_result = self.dynamic_optimizer.optimize_routes_with_dynamic_availability(
                trucks_data, bins_data, schedules, depot_data, current_time_seconds
            )
            
            if not routing_result.get('success', False):
                logger.warning(f"Dynamic routing failed: {routing_result.get('error', 'Unknown error')}")
                return routing_result.get('fallback_result', self._get_basic_routing_recommendations(
                    trucks_data, bins_data, current_time_seconds
                ))
            
            optimization_result = routing_result['optimization_result']
            
            # Enhance with traffic-aware recommendations
            traffic_enhanced_result = self._add_traffic_recommendations(
                optimization_result, current_time_seconds
            )
            
            # Generate executive summary
            executive_summary = self._generate_executive_routing_summary(traffic_enhanced_result)
            
            return {
                'success': True,
                'routing_strategy': 'enhanced_dynamic_with_traffic_awareness',
                'executive_summary': executive_summary,
                'detailed_results': traffic_enhanced_result,
                'recommendations': self._extract_actionable_recommendations(traffic_enhanced_result),
                'timestamp': current_time_seconds
            }
            
        except Exception as e:
            logger.error(f"Error in enhanced routing recommendations: {e}")
            return {
                'success': False,
                'error': str(e),
                'fallback_recommendations': self._get_basic_routing_recommendations(
                    trucks_data, bins_data, current_time_seconds
                )
            }
    
    def _add_traffic_recommendations(self, optimization_result: Dict, current_time_seconds: float) -> Dict:
        """Add traffic-aware recommendations to optimization results"""
        enhanced_result = optimization_result.copy()
        current_time_min = current_time_seconds // 60
        
        # Enhance route extensions with traffic timing
        if 'route_extensions' in enhanced_result:
            for extension in enhanced_result['route_extensions']:
                if extension.get('success', False):
                    # Add traffic timing advice for extension
                    extension['traffic_advice'] = self._get_traffic_advice_for_route_extension(
                        extension, current_time_min
                    )
        
        # Enhance new routes with traffic timing
        if 'new_routes' in enhanced_result:
            for route in enhanced_result['new_routes']:
                if route.get('success', False):
                    # Add optimal dispatch timing based on traffic
                    route['optimal_dispatch_timing'] = self._get_optimal_dispatch_timing(
                        route, current_time_min
                    )
        
        # Add overall traffic strategy recommendations
        enhanced_result['traffic_strategy'] = self._generate_traffic_strategy(current_time_min)
        
        return enhanced_result
    
    def _get_traffic_advice_for_route_extension(self, extension: Dict, current_time_min: int) -> Dict:
        """Generate traffic advice for route extension"""
        try:
            # Estimate when extension will occur
            current_duration = extension.get('optimization_details', {}).get('additional_time_minutes', 30)
            extension_start_time = current_time_min + current_duration
            
            # Get traffic conditions during extension
            extension_density = self.get_density_at_time(extension_start_time)
            extension_level = self.classify_traffic_level(extension_density)
            
            advice = {
                'extension_timing': 'optimal' if extension_level == 'light' else 'acceptable' if extension_level == 'moderate' else 'challenging',
                'traffic_level_during_extension': extension_level,
                'estimated_traffic_delay': self._estimate_traffic_delay(extension_density, current_duration),
                'recommendation': ''
            }
            
            # Generate specific recommendations
            if extension_level == 'heavy':
                advice['recommendation'] = 'Consider delaying extension until traffic improves, or proceed if bins are critical'
            elif extension_level == 'moderate':
                advice['recommendation'] = 'Good timing for extension with moderate traffic impact'
            else:
                advice['recommendation'] = 'Excellent timing for extension with minimal traffic delays'
            
            return advice
            
        except Exception as e:
            return {'error': str(e), 'recommendation': 'Unable to analyze traffic conditions'}
    
    def _get_optimal_dispatch_timing(self, route: Dict, current_time_min: int) -> Dict:
        """Get optimal dispatch timing for new route considering traffic"""
        try:
            truck_id = route.get('truck_id')
            estimated_duration = route.get('route_metrics', {}).get('estimated_duration_minutes', 60)
            
            # Check if delaying dispatch would be beneficial
            dispatch_analysis = self.find_optimal_dispatch_before_heavy_traffic(
                current_time_min, estimated_duration, None  # No specific bin ID for route analysis
            )
            
            return {
                'immediate_dispatch_recommended': dispatch_analysis.get('dispatch', 'now') == 'now',
                'optimal_delay_minutes': dispatch_analysis.get('delay_min', 0),
                'traffic_reasoning': dispatch_analysis.get('reason', 'Standard dispatch timing'),
                'fuel_savings_potential': dispatch_analysis.get('fuel_savings_min', 0)
            }
            
        except Exception as e:
            return {'error': str(e), 'immediate_dispatch_recommended': True}
    
    def _generate_traffic_strategy(self, current_time_min: int) -> Dict:
        """Generate overall traffic strategy for the current time"""
        try:
            current_density = self.get_density_at_time(current_time_min)
            current_level = self.classify_traffic_level(current_density)
            
            # Get next light traffic window
            light_window = self.find_next_light_traffic_window(current_time_min)
            
            # Find upcoming heavy traffic
            transitions = self.predict_traffic_transition_times(current_time_min, prediction_window_hours=4)
            next_heavy = next((t for t in transitions if t['to_level'] == 'heavy'), None)
            
            strategy = {
                'current_conditions': {
                    'level': current_level,
                    'density': current_density,
                    'hour': int(current_time_min // 60) % 24
                },
                'strategic_recommendations': [],
                'timing_windows': {
                    'next_light_traffic': light_window,
                    'next_heavy_traffic': next_heavy
                }
            }
            
            # Generate strategic recommendations
            if current_level == 'light':
                strategy['strategic_recommendations'].append(
                    "Excellent time for dispatching - take advantage of light traffic"
                )
            elif current_level == 'heavy':
                if light_window and light_window['time_offset'] <= 60:
                    strategy['strategic_recommendations'].append(
                        f"Consider delaying non-critical dispatches {light_window['time_offset']} minutes for better conditions"
                    )
                else:
                    strategy['strategic_recommendations'].append(
                        "Heavy traffic period - prioritize critical collections only"
                    )
            else:  # moderate
                strategy['strategic_recommendations'].append(
                    "Moderate traffic - good time for routine dispatches"
                )
            
            # Add route extension recommendations
            if current_level in ['light', 'moderate']:
                strategy['strategic_recommendations'].append(
                    "Good conditions for route extensions - trucks can efficiently collect additional bins"
                )
            
            return strategy
            
        except Exception as e:
            return {'error': str(e)}
    
    def _generate_executive_routing_summary(self, detailed_results: Dict) -> Dict:
        """Generate executive summary of routing decisions"""
        try:
            summary = detailed_results.get('optimization_summary', {})
            availability = detailed_results.get('availability_analysis', {}).get('availability_summary', {})
            
            return {
                'total_trucks_available': availability.get('available_count', 0),
                'total_trucks_busy': availability.get('busy_count', 0),
                'total_trucks_scheduled': availability.get('scheduled_count', 0),
                'route_extensions_possible': availability.get('route_extendable_count', 0),
                'bins_assigned_for_collection': summary.get('total_bins_assigned', 0),
                'bins_deferred': summary.get('total_bins_deferred', 0),
                'efficiency_score': round(summary.get('optimization_efficiency', 0) * 100, 1),
                'key_decisions': self._extract_key_decisions(detailed_results),
                'next_review_recommended_minutes': self._recommend_next_review_time(detailed_results)
            }
            
        except Exception as e:
            return {'error': str(e)}
    
    def _extract_key_decisions(self, detailed_results: Dict) -> List[str]:
        """Extract key routing decisions made"""
        decisions = []
        
        try:
            # Route extensions
            extensions = detailed_results.get('route_extensions', [])
            successful_extensions = [e for e in extensions if e.get('success', False)]
            if successful_extensions:
                decisions.append(f"Extended routes for {len(successful_extensions)} trucks to collect additional bins")
            
            # New dispatches
            new_routes = detailed_results.get('new_routes', [])
            successful_routes = [r for r in new_routes if r.get('success', False)]
            if successful_routes:
                decisions.append(f"Created {len(successful_routes)} new optimized routes")
            
            # Critical overrides
            overrides = detailed_results.get('critical_overrides', [])
            if overrides:
                decisions.append(f"Override {len(overrides)} scheduled trucks for emergency collections")
            
            # Deferrals
            deferred = detailed_results.get('deferred_collections', [])
            if deferred:
                decisions.append(f"Deferred {len(deferred)} bin collections due to truck unavailability")
            
            return decisions[:5]  # Limit to top 5 decisions
            
        except Exception:
            return ["Unable to analyze routing decisions"]
    
    def _recommend_next_review_time(self, detailed_results: Dict) -> int:
        """Recommend when to next review routing decisions"""
        try:
            # If there are deferred collections, review sooner
            deferred_count = len(detailed_results.get('deferred_collections', []))
            if deferred_count > 0:
                return 15  # 15 minutes
            
            # If there are route extensions happening, review when they complete
            extensions = detailed_results.get('route_extensions', [])
            if extensions:
                avg_extension_time = sum(
                    e.get('estimated_additional_time', 30) 
                    for e in extensions if e.get('success', False)
                ) / max(len(extensions), 1)
                return int(avg_extension_time + 15)  # Extension time + buffer
            
            # Normal review interval
            return 60  # 1 hour
            
        except Exception:
            return 30  # Default 30 minutes
    
    def _extract_actionable_recommendations(self, detailed_results: Dict) -> List[Dict]:
        """Extract actionable recommendations for operators"""
        recommendations = []
        
        try:
            # Immediate actions for route extensions
            extensions = detailed_results.get('route_extensions', [])
            for extension in extensions:
                if extension.get('success', False):
                    truck_id = extension.get('truck_id')
                    additional_bins = extension.get('additional_bins', [])
                    
                    recommendations.append({
                        'priority': 'high',
                        'action': 'extend_route',
                        'truck_id': truck_id,
                        'details': f"Extend route for truck {truck_id} to collect {len(additional_bins)} additional bins",
                        'estimated_time': extension.get('estimated_additional_time', 'unknown'),
                        'traffic_advice': extension.get('traffic_advice', {}).get('recommendation', 'Proceed with extension')
                    })
            
            # New route dispatches
            new_routes = detailed_results.get('new_routes', [])
            for route in new_routes:
                if route.get('success', False):
                    truck_id = route.get('truck_id')
                    bin_count = len(route.get('optimized_route', []))
                    dispatch_timing = route.get('optimal_dispatch_timing', {})
                    
                    priority = 'high' if dispatch_timing.get('immediate_dispatch_recommended', True) else 'medium'
                    action_text = "Dispatch immediately" if priority == 'high' else f"Delay dispatch {dispatch_timing.get('optimal_delay_minutes', 0)} minutes"
                    
                    recommendations.append({
                        'priority': priority,
                        'action': 'dispatch_truck',
                        'truck_id': truck_id,
                        'details': f"{action_text} for truck {truck_id} to collect {bin_count} bins",
                        'timing_reason': dispatch_timing.get('traffic_reasoning', 'Optimal timing'),
                        'potential_fuel_savings': dispatch_timing.get('fuel_savings_potential', 0)
                    })
            
            # Critical overrides
            overrides = detailed_results.get('critical_overrides', [])
            for override in overrides:
                if override.get('success', False):
                    recommendations.append({
                        'priority': 'critical',
                        'action': 'emergency_dispatch',
                        'truck_id': override.get('truck_id'),
                        'details': f"EMERGENCY: Override scheduled truck for critical bin collection",
                        'overridden_schedule': override.get('overridden_schedule_id'),
                        'reason': override.get('urgency_reason', 'Critical emergency')
                    })
            
            # Sort by priority
            priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
            recommendations.sort(key=lambda x: priority_order.get(x.get('priority', 'low'), 3))
            
            return recommendations[:10]  # Limit to top 10 recommendations
            
        except Exception as e:
            logger.error(f"Error extracting recommendations: {e}")
            return [{'priority': 'low', 'action': 'error', 'details': f'Error generating recommendations: {str(e)}'}]
    
    def _get_basic_routing_recommendations(self, trucks_data: List[Dict], bins_data: List[Dict], 
                                         current_time_seconds: float) -> Dict:
        """Fallback basic routing recommendations when enhanced routing fails"""
        try:
            current_time_min = current_time_seconds // 60
            
            # Simple analysis
            available_trucks = [t for t in trucks_data if t.get('status') == 'idle']
            urgent_bins = [b for b in bins_data 
                          if b.get('fillLevel', 0) >= b.get('threshold', 80)]
            
            return {
                'success': True,
                'routing_strategy': 'basic_fallback',
                'executive_summary': {
                    'total_trucks_available': len(available_trucks),
                    'bins_needing_collection': len(urgent_bins),
                    'efficiency_score': 70.0,  # Conservative estimate
                    'key_decisions': ['Using basic routing due to enhanced system unavailability']
                },
                'recommendations': [{
                    'priority': 'medium',
                    'action': 'basic_dispatch',
                    'details': f'Dispatch {min(len(available_trucks), len(urgent_bins))} trucks for urgent bin collection',
                    'truck_count': min(len(available_trucks), len(urgent_bins))
                }] if available_trucks and urgent_bins else []
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'routing_strategy': 'failed_fallback'
            }
    
    def _estimate_traffic_delay(self, density: float, base_duration_min: float) -> float:
        """Estimate additional delay due to traffic density"""
        if density <= 1.0:
            return 0
        else:
            # Traffic delay increases non-linearly with density
            delay_factor = (density - 1.0) * 0.3  # 30% delay per density unit above 1.0
            return base_duration_min * delay_factor