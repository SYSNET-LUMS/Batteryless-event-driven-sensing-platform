from typing import Dict, Optional
from config.constants import BIN_TRAFFIC_PROFILES

class TrafficManager:
    """Traffic management service"""
    
    def __init__(self):
        self.normal_traffic_threshold = 3.0
        self.min_travel_savings = 5
        self.safety_buffer = 15
        
        self.critical_fill_threshold = 95
        self.overflow_threshold = 100
        self.max_wait_time = 150

        self.traffic_density = {
            0: 1.0, 1: 1.2, 2: 1.5, 3: 1.2, 4: 1.0, 5: 1.5, 6: 2.0,
            7: 6.0, 8: 10.0, 9: 8.0,
            10: 3.0, 11: 2.0, 12: 1.5, 13: 1.0, 14: 1.5, 15: 2.0,
            16: 5.0, 17: 10.0, 18: 7.0, 19: 4.0,
            20: 3.0, 21: 2.0, 22: 1.5, 23: 1.2
        }
    
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
                               bin_fill_level: Optional[float] = None) -> Dict:
        """Dispatch calculation with multiple safety overrides"""
        
        # Safety checks
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
                'reason': f'OVERFLOW RISK: Only {time_to_overflow_min:.1f}min until overflow'
            }
        
        # Check if traffic is already normal
        is_traffic_normal = current_density <= self.normal_traffic_threshold
        if is_traffic_normal:
            return {'dispatch': 'now', 'delay_min': 0, 'reason': 'Traffic already normal'}
        
        # Check if waiting is beneficial
        wait_for_normal_min = self.find_time_to_normal_traffic_for_bin(current_time_min, bin_id)
        
        if wait_for_normal_min == 0:
            return {'dispatch': 'now', 'delay_min': 0, 'reason': 'Traffic never becomes normal'}
        
        if wait_for_normal_min > self.max_wait_time:
            return {
                'dispatch': 'now',
                'delay_min': 0,
                'reason': f'Max wait time exceeded ({wait_for_normal_min}min > {self.max_wait_time}min)'
            }
        
        # Calculate travel time if we wait
        predicted_time = current_time_min + wait_for_normal_min
        predicted_density = self.get_bin_specific_density(bin_id, predicted_time) if bin_id else self.get_density_at_time(predicted_time)
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
                'reason': f'Waiting would cause overflow (deadline: {safety_deadline:.1f}min)'
            }
        
        # Decision logic
        savings_sufficient = travel_savings >= self.min_travel_savings
        no_overflow_risk = time_to_overflow_min > total_time_if_wait + self.safety_buffer
        wait_worthwhile = travel_savings > wait_for_normal_min * 0.1
        
        if savings_sufficient and no_overflow_risk and wait_worthwhile:
            optimal_delay = min(
                wait_for_normal_min,
                int(time_to_overflow_min - predicted_adjusted - self.safety_buffer),
                self.max_wait_time
            )
            return {
                'dispatch': 'wait',
                'delay_min': optimal_delay,
                'reason': f'Wait {optimal_delay}min for better traffic (save ~{travel_savings:.0f}min travel)'
            }
        else:
            return {'dispatch': 'now', 'delay_min': 0, 'reason': 'Not worth waiting or overflow risk'}
    
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