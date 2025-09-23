
from typing import Dict, List, Optional
from services.traffic_service import TrafficManager
from services.traffic.predictive_dispatch_service import PredictiveDispatchService
from services.external.osrm_service import OSRMService
from config.settings import Config
import logging

logger = logging.getLogger(__name__)

class DispatchService:
    """Enhanced dispatch service with predictive traffic awareness"""
    
    def __init__(self, osrm_service: OSRMService = None):
        self.traffic_manager = TrafficManager()
        self.predictive_dispatch = PredictiveDispatchService(osrm_service)
        self.osrm_service = osrm_service or OSRMService()
        self.config = Config()
        
        # Dispatch thresholds
        self.critical_fill_threshold = 95
        self.overflow_threshold = 100
        self.max_wait_time = 150
        self.safety_buffer = 15
        self.min_travel_savings = 5
        
        # Enhanced features toggle
        self.use_predictive_dispatch = True  # Enable enhanced predictive features
    
    def should_dispatch_now(self, bin_data: Dict, truck_data: Dict, 
                          simulation_time_seconds: float) -> Dict:
        """Enhanced dispatch decision logic with predictive capabilities"""
        start_hour = self.config.SIMULATION_START_HOUR
        current_time_min = (start_hour * 60) + (simulation_time_seconds // 60)
        
        time_to_overflow_hours = self._calculate_time_to_overflow(bin_data)
        time_to_overflow_min = time_to_overflow_hours * 60

        # Get travel time
        base_travel_min = self._get_base_travel_time(bin_data, truck_data)

        # Safety checks first (unchanged - critical for safety)
        safety_decision = self._check_safety_overrides(bin_data, time_to_overflow_min)
        if safety_decision:
            return safety_decision

        # Enhanced: Use predictive dispatch if enabled
        if self.use_predictive_dispatch:
            try:
                # Get predictive recommendation
                predictive_result = self.predictive_dispatch.predict_optimal_dispatch_window(
                    bin_data, simulation_time_seconds
                )
                
                # If predictive dispatch gives a clear benefit, use it
                if (predictive_result.get('dispatch') == 'wait' and 
                    predictive_result.get('fuel_savings_min', 0) > self.min_travel_savings):
                    
                    logger.info(f"Using predictive dispatch for bin {bin_data.get('id')}: {predictive_result['reason']}")
                    return predictive_result
                    
                # For immediate dispatch with specific reasons, respect predictive logic
                elif (predictive_result.get('dispatch') == 'now' and 
                      any(keyword in predictive_result.get('reason', '') 
                          for keyword in ['EMERGENCY', 'CRITICAL', 'OVERFLOW'])):
                    return predictive_result
                    
            except Exception as e:
                logger.warning(f"Predictive dispatch failed for bin {bin_data.get('id', 'unknown')}, using standard logic: {e}")
                # Disable predictive dispatch for this request to avoid further issues
                self.use_predictive_dispatch = False

        # Enhanced traffic-aware dispatch check
        bin_id = bin_data.get('id')
        current_density = self.traffic_manager.get_bin_specific_density(bin_id, current_time_min)
        travel_time_with_traffic = base_travel_min * current_density
        
        if (travel_time_with_traffic + self.safety_buffer) >= time_to_overflow_min:
            # Get traffic level for better reasoning
            traffic_level = self.traffic_manager.classify_traffic_level(current_density)
            return {
                'dispatch': 'now',
                'delay_min': 0,
                'reason': f'Travel time ({travel_time_with_traffic:.1f}min, {traffic_level} traffic) + buffer exceeds time to overflow ({time_to_overflow_min:.1f}min)'
            }

        # Enhanced: Use improved traffic-based decision with predictive logic
        return self.traffic_manager.calculate_dispatch_time(
            time_to_overflow_min,
            base_travel_min,
            current_time_min,
            bin_id=bin_id,
            bin_fill_level=bin_data.get('fillLevel', 0),
            use_predictive_logic=self.use_predictive_dispatch
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
    
    def get_system_traffic_overview(self, bins_data: List[Dict], 
                                  simulation_time_seconds: float) -> Dict:
        """
        Get comprehensive traffic overview for the entire system
        
        This provides insights for fuel efficiency optimization and dispatch planning
        """
        try:
            current_time_min = (self.config.SIMULATION_START_HOUR * 60) + (simulation_time_seconds // 60)
            current_hour = int(current_time_min // 60) % 24
            
            overview = {
                'current_time': {
                    'hour': current_hour,
                    'minute': int(current_time_min % 60),
                    'simulation_seconds': simulation_time_seconds
                },
                'system_summary': {
                    'total_bins': len(bins_data),
                    'bins_in_light_traffic': 0,
                    'bins_in_moderate_traffic': 0,
                    'bins_in_heavy_traffic': 0,
                    'average_traffic_density': 0.0,
                },
                'dispatch_recommendations': {
                    'immediate_dispatch': [],
                    'wait_for_better_traffic': [],
                    'fuel_savings_potential': 0.0
                },
                'traffic_insights': [],
                'next_optimal_windows': []
            }
            
            total_density = 0.0
            fuel_savings_potential = 0.0
            
            # Analyze each bin's traffic situation
            for bin_data in bins_data:
                try:
                    bin_id = bin_data.get('id')
                    if not bin_id:
                        continue
                    
                    # Get traffic insights
                    traffic_insights = self.traffic_manager.get_traffic_insights_for_bin(
                        bin_id, current_time_min
                    )
                    overview['traffic_insights'].append(traffic_insights)
                    
                    # Update system summary
                    current_level = traffic_insights.get('current_level', 'unknown')
                    if current_level == 'light':
                        overview['system_summary']['bins_in_light_traffic'] += 1
                    elif current_level == 'moderate':
                        overview['system_summary']['bins_in_moderate_traffic'] += 1
                    elif current_level == 'heavy':
                        overview['system_summary']['bins_in_heavy_traffic'] += 1
                    
                    current_density = traffic_insights.get('current_density', 1.0)
                    total_density += current_density
                    
                    # Get predictive dispatch recommendation if available
                    if self.use_predictive_dispatch:
                        prediction = self.predictive_dispatch.predict_optimal_dispatch_window(
                            bin_data, simulation_time_seconds
                        )
                        
                        dispatch_rec = {
                            'bin_id': bin_id,
                            'current_fill': bin_data.get('fillLevel', 0),
                            'prediction': prediction,
                            'traffic_level': current_level,
                            'density': current_density
                        }
                        
                        if prediction.get('dispatch') == 'now':
                            overview['dispatch_recommendations']['immediate_dispatch'].append(dispatch_rec)
                        elif prediction.get('delay_min', 0) > 0:
                            overview['dispatch_recommendations']['wait_for_better_traffic'].append(dispatch_rec)
                            
                            # Accumulate fuel savings potential
                            savings = prediction.get('fuel_savings_min', 0)
                            if savings > 0:
                                fuel_savings_potential += savings
                    
                    # Track next optimal windows
                    light_window = traffic_insights.get('next_light_window')
                    if light_window:
                        overview['next_optimal_windows'].append({
                            'bin_id': bin_id,
                            'start_in_minutes': light_window.get('time_until_start', 0),
                            'duration_minutes': light_window.get('duration_min', 0),
                            'avg_density': light_window.get('avg_density', 1.0)
                        })
                        
                except Exception as e:
                    logger.warning(f"Error analyzing bin {bin_data.get('id', 'unknown')}: {e}")
                    continue
            
            # Calculate system averages
            if len(bins_data) > 0:
                overview['system_summary']['average_traffic_density'] = round(total_density / len(bins_data), 2)
            
            overview['dispatch_recommendations']['fuel_savings_potential'] = round(fuel_savings_potential, 1)
            
            # Sort recommendations by urgency/savings
            overview['dispatch_recommendations']['immediate_dispatch'].sort(
                key=lambda x: x.get('current_fill', 0), reverse=True
            )
            overview['dispatch_recommendations']['wait_for_better_traffic'].sort(
                key=lambda x: x.get('prediction', {}).get('fuel_savings_min', 0), reverse=True
            )
            
            return overview
            
        except Exception as e:
            logger.error(f"Error generating system traffic overview: {e}")
            return {
                'error': str(e),
                'current_time': {
                    'simulation_seconds': simulation_time_seconds
                },
                'system_summary': {'total_bins': len(bins_data)}
            }
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