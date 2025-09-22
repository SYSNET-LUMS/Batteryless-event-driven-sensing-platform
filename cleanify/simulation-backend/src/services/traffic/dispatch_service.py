
from typing import Dict, List, Optional
from services.traffic_service import TrafficManager
from services.external.osrm_service import OSRMService
from config.settings import Config

class DispatchService:
    """Handles dispatch timing decisions with traffic awareness"""
    
    def __init__(self, osrm_service: OSRMService = None):
        self.traffic_manager = TrafficManager()
        self.osrm_service = osrm_service or OSRMService()
        self.config = Config()
        
        # Dispatch thresholds
        self.critical_fill_threshold = 95
        self.overflow_threshold = 100
        self.max_wait_time = 150
        self.safety_buffer = 15
        self.min_travel_savings = 5
    
    def should_dispatch_now(self, bin_data: Dict, truck_data: Dict, 
                          simulation_time_seconds: float) -> Dict:
        """Main dispatch decision logic with safety overrides"""
        start_hour = self.config.SIMULATION_START_HOUR
        current_time_min = (start_hour * 60) + (simulation_time_seconds // 60)
        
        time_to_overflow_hours = self._calculate_time_to_overflow(bin_data)
        time_to_overflow_min = time_to_overflow_hours * 60

        # Get travel time
        base_travel_min = self._get_base_travel_time(bin_data, truck_data)

        # Safety checks first
        safety_decision = self._check_safety_overrides(bin_data, time_to_overflow_min)
        if safety_decision:
            return safety_decision

        # Ensure truck can reach bin before overflow
        # If travel time (with current traffic) + buffer > time to overflow, dispatch now
        current_density = self.traffic_manager.get_bin_specific_density(bin_data['id'], current_time_min)
        travel_time_with_traffic = base_travel_min * current_density
        if (travel_time_with_traffic + self.safety_buffer) >= time_to_overflow_min:
            return {
                'dispatch': 'now',
                'delay_min': 0,
                'reason': f'Travel time ({travel_time_with_traffic:.1f}min) + buffer exceeds time to overflow ({time_to_overflow_min:.1f}min)'
            }

        # Traffic-based decision
        return self.traffic_manager.calculate_dispatch_time(
            time_to_overflow_min,
            base_travel_min,
            current_time_min,
            bin_id=bin_data['id'],
            bin_fill_level=bin_data.get('fillLevel', 0)
        )
    
    def _check_safety_overrides(self, bin_data: Dict, time_to_overflow_min: float) -> Optional[Dict]:
        """Check for safety conditions that override traffic optimization"""
        fill_level = bin_data.get('fillLevel', 0)
        fill_rate = bin_data.get('fillRate', 0)
        if fill_rate <= 0:
            print(f"⚠️ ALERT: Bin {bin_data.get('id','?')} has zero fill rate. Sensor or data issue.")
        if fill_level >= self.overflow_threshold:
            return {
                'dispatch': 'now',
                'delay_min': 0,
                'reason': f'EMERGENCY: Bin overflowing at {fill_level}%'
            }
        if fill_level >= self.critical_fill_threshold:
            return {
                'dispatch': 'now',
                'delay_min': 0,
                'reason': f'CRITICAL: Bin at {fill_level}% - safety override'
            }
        if time_to_overflow_min <= 0:
            return {
                'dispatch': 'now',
                'delay_min': 0,
                'reason': 'EMERGENCY: Bin already overflowing (time calculation)'
            }
        return None
    
    def _get_base_travel_time(self, bin_data: Dict, truck_data: Dict) -> float:
        """Get base travel time in minutes"""
        try:
            # Try OSRM first for accurate routing
            return self.osrm_service.get_travel_time_with_traffic(
                truck_data['lat'], truck_data['lng'],
                bin_data['lat'], bin_data['lng'],
                traffic_multiplier=1.0  # Base time, no traffic
            )
        except:
            # Fallback to simple calculation
            from utils.distance import calculate_distance_km
            distance_km = calculate_distance_km(
                truck_data['lat'], truck_data['lng'],
                bin_data['lat'], bin_data['lng']
            )
            return (distance_km / 50) * 60  # 50 km/h average speed
    
    def _calculate_time_to_overflow(self, bin_data: Dict) -> float:
        """Calculate time until bin overflows in hours"""
        fill_level = bin_data.get('fillLevel', 0)
        capacity = bin_data.get('capacity', 500)
        fill_rate = bin_data.get('fillRate', 3.5)
        
        if fill_level >= 100:
            return 0.0
        
        if fill_rate <= 0:
            return float('inf')
        
        current_fill_liters = (fill_level / 100) * capacity
        remaining_capacity = capacity - current_fill_liters
        
        if remaining_capacity <= 0:
            return 0.0
        
        return max(0.0, remaining_capacity / fill_rate)
    
    def process_waiting_assignments(self, waiting_assignments: Dict, 
                                  current_simulation_time: float) -> List[Dict]:
        """Process trucks whose waiting period has ended"""
        current_time_min = (7 * 60) + (current_simulation_time // 60)
        ready_dispatches = []
        
        for truck_id, assignment in list(waiting_assignments.items()):
            if current_time_min >= assignment['dispatch_time']:
                ready_dispatches.append({
                    "truck_id": truck_id,
                    "route": assignment['route'],
                    "dispatch": 'now',
                    "delay_min": 0,
                    "reason": f"Post-wait dispatch to {assignment['bin_id']}"
                })
        
        return ready_dispatches
    def dispatch_decision_flow(self, bins_data: List[Dict], trucks_data: List[Dict], simulation_time_seconds: float) -> List[Dict]:
            """
            Example orchestration method: For each bin and available truck, decide whether to dispatch now or wait,
            using traffic-aware logic.
            Returns a list of dispatch decisions for bins that should be collected now.
            """
            dispatches = []
            for bin_data in bins_data:
                for truck_data in trucks_data:
                    decision = self.should_dispatch_now(bin_data, truck_data, simulation_time_seconds)
                    if decision['dispatch'] == 'now':
                        dispatches.append({
                            'truck_id': truck_data.get('id'),
                            'bin_id': bin_data.get('id'),
                            'route': [bin_data.get('id')],
                            'delay_min': decision.get('delay_min', 0),
                            'reason': decision.get('reason', '')
                        })
                    # If decision['dispatch'] == 'wait', you can schedule for later or log
            return dispatches