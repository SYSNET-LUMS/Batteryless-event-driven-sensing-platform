"""
Minimalist Traffic-Aware Bin Filtering Service
Decides which bins to dispatch now vs wait for light traffic
"""

from typing import Dict, List, Tuple, Optional
from config.settings import Config


class TrafficService:
    """Simple traffic-aware bin filtering"""
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.heavy_hours = self.config.TRAFFIC_HEAVY_HOURS
        self.multiplier = self.config.TRAFFIC_MULTIPLIER
        self.buffer_hours = self.config.TRAFFIC_BUFFER_HOURS
    
    def filter_bins_for_dispatch(
        self, 
        bins: List[Dict], 
        current_simulation_seconds: float
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Split bins into: (dispatch_now, wait_for_light_traffic)
        
        Logic:
        - For every full bin, calculate Time_To_Overflow = Remaining_Capacity / Fill_Rate
        - If traffic is heavy AND Time_To_Overflow > Time_To_Light_Traffic + 1hr, return False (Wait)
        - Otherwise return True (Dispatch)
        
        Args:
            bins: All bins with fill_level > threshold
            current_simulation_seconds: Seconds since simulation start
            
        Returns:
            (bins_to_dispatch, bins_to_wait)
        """
        current_hour = self._get_simulation_hour(current_simulation_seconds)
        is_heavy_traffic = current_hour in self.heavy_hours
        
        dispatch_now = []
        wait = []
        
        for bin_data in bins:
            # Calculate time to overflow
            time_to_overflow_hours = self._calculate_time_to_overflow(bin_data)
            
            # Calculate time to next light traffic period
            time_to_light_traffic_hours = self._calculate_time_to_light_traffic(current_hour)
            
            # CRITICAL DECISION LOGIC
            if not is_heavy_traffic:
                # Always dispatch during light traffic
                dispatch_now.append(bin_data)
            elif time_to_overflow_hours <= (time_to_light_traffic_hours + self.buffer_hours):
                # Urgent: will overflow before light traffic + buffer
                dispatch_now.append(bin_data)
            else:
                # Can safely wait for light traffic
                wait.append({
                    **bin_data,
                    'wait_reason': f'Wait {time_to_light_traffic_hours:.1f}h for light traffic',
                    'time_to_overflow': time_to_overflow_hours
                })
        
        return dispatch_now, wait
    
    def _get_simulation_hour(self, simulation_seconds: float) -> int:
        """Convert simulation seconds to hour (7am start by default)"""
        start_hour = self.config.SIMULATION_START_HOUR
        hours_elapsed = simulation_seconds / 3600
        return int((start_hour + hours_elapsed) % 24)
    
    def _calculate_time_to_overflow(self, bin_data: Dict) -> float:
        """
        Calculate hours until bin overflows
        
        Returns:
            Hours until overflow (inf if fillRate is 0)
        """
        fill_level = bin_data.get('fillLevel', 0)
        capacity = bin_data.get('capacity', 500)
        fill_rate = bin_data.get('fillRate', 3.5)
        
        if fill_level >= 100:
            return 0.0
        if fill_rate <= 0:
            return float('inf')
        
        # Calculate remaining capacity in liters
        current_fill_liters = (fill_level / 100) * capacity
        remaining_capacity = capacity - current_fill_liters
        
        # Time = Remaining / Rate
        return max(0.0, remaining_capacity / fill_rate)
    
    def _calculate_time_to_light_traffic(self, current_hour: int) -> float:
        """
        Calculate hours until next non-heavy traffic period
        
        Returns:
            Hours until light traffic (checking next 24 hours)
        """
        for i in range(1, 25):  # Check next 24 hours
            future_hour = (current_hour + i) % 24
            if future_hour not in self.heavy_hours:
                return float(i)
        
        # Traffic never clears (shouldn't happen with reasonable config)
        return 0.0
