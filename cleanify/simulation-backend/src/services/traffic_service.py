from typing import Dict, Optional, List, Tuple
from config.constants import BIN_TRAFFIC_PROFILES
import logging

logger = logging.getLogger(__name__)

class TrafficManager:
    """Enhanced traffic management service with predictive capabilities"""
    
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
                'traffic_profile': BIN_TRAFFIC_PROFILES.get(bin_id, {}).get('road_type', 'general')
            }
            
        except Exception as e:
            logger.error(f"Error getting traffic insights for bin {bin_id}: {e}")
            return {
                'bin_id': bin_id,
                'error': str(e),
                'current_level': 'unknown'
            }