"""
Enhanced Predictive Dispatch Service

Integrates concepts from abc.py into the existing sophisticated traffic system:
- Predictive dispatch timing before heavy traffic periods
- Better fuel efficiency through traffic-aware scheduling
- Enhanced urgency scoring based on upcoming traffic conditions
"""

from typing import Dict, List, Optional, Tuple
from services.traffic_service import TrafficManager
from services.external.osrm_service import OSRMService
from config.settings import Config
import math
import logging

logger = logging.getLogger(__name__)

class PredictiveDispatchService:
    """Enhanced dispatch service with predictive traffic awareness"""
    
    def __init__(self, osrm_service: OSRMService = None):
        self.traffic_manager = TrafficManager()
        self.osrm_service = osrm_service or OSRMService()
        self.config = Config()
        
        # Enhanced parameters for predictive dispatch
        self.heavy_traffic_threshold = 5.0  # Density above this is considered "heavy"
        self.prediction_window_hours = 4.0  # Look ahead window for traffic predictions
        self.fuel_efficiency_weight = 0.3  # Weight for fuel savings in dispatch decisions
        self.overflow_prevention_weight = 0.7  # Weight for overflow prevention
        
        # Traffic pattern learning (could be enhanced with ML in future)
        self.traffic_patterns = {}
        
    def predict_optimal_dispatch_window(self, bin_data: Dict, current_time_seconds: float) -> Dict:
        """
        Enhanced version of abc.py's prediction logic but using the sophisticated traffic system
        
        Returns optimal dispatch timing considering:
        1. Current and predicted traffic conditions
        2. Bin fill rate and overflow risk
        3. Fuel efficiency optimization
        4. Safety buffers
        """
        try:
            current_time_min = (self.config.SIMULATION_START_HOUR * 60) + (current_time_seconds // 60)
            current_hour = int(current_time_min // 60) % 24
            
            bin_id = bin_data.get('id')
            fill_level = bin_data.get('fillLevel', 0)
            fill_rate = bin_data.get('fillRate', 3.5)
            dynamic_threshold = bin_data.get('dynamic_threshold', bin_data.get('threshold', 80))
            
            # Safety checks first to avoid complex calculations for urgent cases
            if fill_level >= 100:
                return {
                    'dispatch': 'now',
                    'delay_min': 0,
                    'reason': 'EMERGENCY: Bin overflowing',
                    'confidence': 1.0
                }
            
            if fill_level >= 95:
                return {
                    'dispatch': 'now',
                    'delay_min': 0,
                    'reason': 'CRITICAL: Bin at 95%+ - safety override',
                    'confidence': 1.0
                }
            
            # Calculate time to dynamic threshold (like abc.py but more sophisticated)
            time_to_threshold_min = self._calculate_time_to_threshold_minutes(bin_data, dynamic_threshold)
            time_to_overflow_min = self._calculate_time_to_threshold_minutes(bin_data, 100.0)
            
            # Get base travel time
            base_travel_min = self._get_base_travel_time_minutes(bin_data)
            
            # Use simplified traffic check to avoid recursion
            current_density = self.traffic_manager.get_bin_specific_density(bin_id, current_time_min)
            current_travel_time = base_travel_min * current_density
            
            # Quick overflow risk check
            if time_to_overflow_min <= (current_travel_time + 15):  # 15 min safety buffer
                return {
                    'dispatch': 'now',
                    'delay_min': 0,
                    'reason': f'OVERFLOW RISK: Only {time_to_overflow_min:.1f}min to overflow',
                    'confidence': 1.0
                }
            
            # Predict traffic conditions for the next few hours (simplified)
            traffic_forecast = self._forecast_traffic_conditions(bin_id, current_time_min, 
                                                               int(self.prediction_window_hours * 60))
            
            # Find optimal dispatch window
            optimal_timing = self._find_optimal_dispatch_timing(
                bin_data, current_time_min, time_to_threshold_min, time_to_overflow_min,
                base_travel_min, traffic_forecast
            )
            
            return optimal_timing
            
        except Exception as e:
            logger.error(f"Error in predict_optimal_dispatch_window: {e}")
            # Safe fallback - immediate dispatch with basic reasoning
            fill_level = bin_data.get('fillLevel', 0)
            if fill_level >= 80:
                return {
                    'dispatch': 'now',
                    'delay_min': 0,
                    'reason': f'Error in prediction, dispatching for safety (fill: {fill_level}%)',
                    'confidence': 0.5
                }
            else:
                return {
                    'dispatch': 'now',
                    'delay_min': 0,
                    'reason': f'Error in prediction: {str(e)[:50]}',
                    'confidence': 0.0
                }
    
    def _calculate_time_to_threshold_minutes(self, bin_data: Dict, target_threshold: float) -> float:
        """Enhanced time-to-threshold calculation with traffic consideration"""
        fill_level = bin_data.get('fillLevel', 0)
        capacity = bin_data.get('capacity', 500)
        fill_rate = bin_data.get('fillRate', 3.5)
        
        if fill_level >= target_threshold:
            return 0.0
        
        if fill_rate <= 0:
            return float('inf')
        
        # Calculate time based on current fill rate
        liters_needed = ((target_threshold - fill_level) / 100.0) * capacity
        time_hours = liters_needed / fill_rate
        
        # Convert to minutes
        return time_hours * 60.0
    
    def _get_base_travel_time_minutes(self, bin_data: Dict, truck_data: Dict = None) -> float:
        """Get base travel time to bin in minutes using actual truck speed"""
        # This should integrate with OSRM service for real travel times
        # For now, using a simple distance-based calculation with actual truck speed
        try:
            # This would be replaced with actual OSRM query in production
            distance_km = bin_data.get('distance_to_depot', 5.0)  # Default 5km
            truck_speed = truck_data.get('speed', 40.0) if truck_data else 40.0  # Use actual truck speed
            time_hours = distance_km / truck_speed
            return time_hours * 60.0  # Convert to minutes
        except Exception:
            return 20.0  # Default 20 minutes
    
    def _forecast_traffic_conditions(self, bin_id: str, current_time_min: int, 
                                   forecast_window_min: int) -> List[Dict]:
        """
        Forecast traffic conditions for the prediction window
        
        Enhanced version of abc.py's traffic prediction using the sophisticated system
        """
        forecast = []
        
        for minutes_ahead in range(0, forecast_window_min, 15):  # 15-minute intervals
            future_time_min = current_time_min + minutes_ahead
            future_hour = int(future_time_min // 60) % 24
            
            # Get traffic density using existing sophisticated system
            if bin_id:
                density = self.traffic_manager.get_bin_specific_density(bin_id, future_time_min)
            else:
                density = self.traffic_manager.get_density_at_time(future_time_min)
            
            # Classify traffic level (like abc.py but more nuanced)
            if density <= self.traffic_manager.normal_traffic_threshold:
                level = 'light'
            elif density >= self.heavy_traffic_threshold:
                level = 'heavy'
            else:
                level = 'moderate'
            
            forecast.append({
                'time_min': future_time_min,
                'hour': future_hour,
                'density': density,
                'level': level,
                'minutes_ahead': minutes_ahead
            })
        
        return forecast
    
    def _find_optimal_dispatch_timing(self, bin_data: Dict, current_time_min: int,
                                    time_to_threshold_min: float, time_to_overflow_min: float,
                                    base_travel_min: float, traffic_forecast: List[Dict]) -> Dict:
        """
        Find optimal dispatch timing considering traffic patterns and fuel efficiency
        
        Inspired by abc.py but much more sophisticated
        """
        bin_id = bin_data.get('id')
        current_density = traffic_forecast[0]['density'] if traffic_forecast else 1.0
        
        # Safety checks first (same as existing system)
        fill_level = bin_data.get('fillLevel', 0)
        if fill_level >= 100:
            return {
                'dispatch': 'now',
                'delay_min': 0,
                'reason': 'EMERGENCY: Bin overflowing',
                'confidence': 1.0
            }
        
        if fill_level >= 95:
            return {
                'dispatch': 'now',
                'delay_min': 0,
                'reason': 'CRITICAL: Bin at 95%+ - safety override',
                'confidence': 1.0
            }
        
        # Check if we have time to optimize
        current_travel_time = base_travel_min * current_density
        safety_buffer = 15  # minutes
        
        if time_to_overflow_min <= (current_travel_time + safety_buffer):
            return {
                'dispatch': 'now',
                'delay_min': 0,
                'reason': f'OVERFLOW RISK: Only {time_to_overflow_min:.1f}min to overflow',
                'confidence': 1.0
            }
        
        # Now find the optimal timing (this is where abc.py concepts are enhanced)
        best_option = None
        best_score = -float('inf')
        
        for forecast_point in traffic_forecast:
            minutes_ahead = forecast_point['minutes_ahead']
            future_density = forecast_point['density']
            future_travel_time = base_travel_min * future_density
            
            # Check if this timing is feasible (won't cause overflow)
            total_time_if_wait = minutes_ahead + future_travel_time
            deadline = time_to_overflow_min - safety_buffer
            
            if total_time_if_wait > deadline:
                continue  # This timing would cause overflow
            
            # Calculate score for this timing
            fuel_savings = (current_travel_time - future_travel_time)  # Positive = savings
            wait_cost = minutes_ahead * 0.1  # Small penalty for waiting
            
            # Enhanced scoring that considers both fuel efficiency and safety
            fuel_score = fuel_savings * self.fuel_efficiency_weight
            safety_score = (deadline - total_time_if_wait) * self.overflow_prevention_weight * 0.1
            
            total_score = fuel_score + safety_score - wait_cost
            
            if total_score > best_score and minutes_ahead >= 0:
                best_score = total_score
                best_option = {
                    'dispatch': 'wait' if minutes_ahead > 0 else 'now',
                    'delay_min': minutes_ahead,
                    'future_travel_time': future_travel_time,
                    'fuel_savings': fuel_savings,
                    'total_score': total_score,
                    'future_density': future_density,
                    'traffic_level': forecast_point['level']
                }
        
        if best_option and best_option['delay_min'] > 0:
            reason = self._generate_dispatch_reason(best_option)
            confidence = min(1.0, max(0.0, best_option['total_score'] / 10.0))
            
            return {
                'dispatch': 'wait',
                'delay_min': int(best_option['delay_min']),
                'reason': reason,
                'confidence': confidence,
                'fuel_savings_min': round(best_option['fuel_savings'], 1),
                'future_traffic_level': best_option['traffic_level']
            }
        else:
            return {
                'dispatch': 'now',
                'delay_min': 0,
                'reason': 'No beneficial wait period found - dispatch now',
                'confidence': 0.8
            }
    
    def _generate_dispatch_reason(self, option: Dict) -> str:
        """Generate human-readable reason for dispatch timing"""
        delay = option['delay_min']
        savings = option['fuel_savings']
        traffic_level = option['traffic_level']
        
        if savings > 5:
            return f"Wait {delay:.0f}min for {traffic_level} traffic (save ~{savings:.0f}min travel)"
        elif traffic_level == 'light':
            return f"Wait {delay:.0f}min for lighter traffic conditions"
        else:
            return f"Wait {delay:.0f}min for improved traffic conditions"
    
    def enhance_urgency_score_with_traffic_prediction(self, bin_data: Dict, 
                                                    current_time_seconds: float) -> Dict:
        """
        Enhance the existing urgency scoring with traffic predictions
        
        This integrates predictive traffic concepts into the urgency calculation
        """
        try:
            # Get base urgency from existing system
            base_urgency = self._calculate_base_urgency(bin_data)
            
            # Get traffic prediction
            prediction = self.predict_optimal_dispatch_window(bin_data, current_time_seconds)
            
            # Modify urgency based on traffic predictions
            traffic_modifier = 1.0
            
            if prediction['dispatch'] == 'now':
                if 'EMERGENCY' in prediction.get('reason', ''):
                    traffic_modifier = 1.5  # Increase urgency for emergencies
                elif 'CRITICAL' in prediction.get('reason', ''):
                    traffic_modifier = 1.3  # Increase urgency for critical
                elif 'OVERFLOW RISK' in prediction.get('reason', ''):
                    traffic_modifier = 1.4  # High urgency for overflow risk
            else:
                # If we can wait, slightly reduce urgency but maintain awareness
                confidence = prediction.get('confidence', 0.5)
                traffic_modifier = 0.9 + (0.1 * (1 - confidence))  # Reduce urgency if confident we can wait
            
            # Calculate enhanced urgency
            enhanced_urgency = min(1.0, base_urgency * traffic_modifier)
            
            return {
                'base_urgency': base_urgency,
                'traffic_modifier': traffic_modifier,
                'enhanced_urgency': enhanced_urgency,
                'prediction': prediction
            }
            
        except Exception as e:
            logger.error(f"Error enhancing urgency score: {e}")
            return {
                'base_urgency': self._calculate_base_urgency(bin_data),
                'traffic_modifier': 1.0,
                'enhanced_urgency': self._calculate_base_urgency(bin_data),
                'prediction': {'dispatch': 'now', 'delay_min': 0, 'reason': 'Error in prediction'}
            }
    
    def _calculate_base_urgency(self, bin_data: Dict) -> float:
        """Calculate base urgency score using existing logic"""
        fill_level = bin_data.get('fillLevel', 0)
        fill_rate = bin_data.get('fillRate', 3.5)
        threshold = bin_data.get('dynamic_threshold', bin_data.get('threshold', 80))
        
        # Simple urgency calculation (this would use the existing sophisticated method in practice)
        fill_urgency = fill_level / 100.0
        
        if fill_rate > 0:
            time_to_threshold = max(0, (threshold - fill_level) / (fill_rate * 100 / bin_data.get('capacity', 500) * 60))  # minutes
            time_urgency = max(0, 1 - (time_to_threshold / (4 * 60)))  # 4 hours as baseline
        else:
            time_urgency = 1.0  # Maximum urgency if no fill rate data
        
        return min(1.0, (fill_urgency * 0.6 + time_urgency * 0.4))
    
    def get_system_wide_dispatch_recommendations(self, bins_data: List[Dict], 
                                               trucks_data: List[Dict],
                                               current_time_seconds: float) -> Dict:
        """
        Generate system-wide dispatch recommendations optimized for fuel efficiency and safety
        
        This is the main method that replaces simple dispatch decisions with predictive ones
        """
        recommendations = {
            'immediate_dispatches': [],
            'scheduled_dispatches': [],
            'fuel_savings_estimate': 0.0,
            'overflow_prevented': [],
            'summary': {
                'total_bins': len(bins_data),
                'immediate_action': 0,
                'scheduled_action': 0,
                'no_action': 0
            }
        }
        
        idle_trucks = [t for t in trucks_data if t.get('status') == 'idle']
        total_fuel_savings = 0.0
        
        for bin_data in bins_data:
            try:
                prediction = self.predict_optimal_dispatch_window(bin_data, current_time_seconds)
                urgency_data = self.enhance_urgency_score_with_traffic_prediction(bin_data, current_time_seconds)
                
                dispatch_recommendation = {
                    'bin_id': bin_data.get('id'),
                    'prediction': prediction,
                    'urgency': urgency_data,
                    'fill_level': bin_data.get('fillLevel', 0),
                    'dynamic_threshold': bin_data.get('dynamic_threshold', bin_data.get('threshold', 80))
                }
                
                if prediction['dispatch'] == 'now':
                    recommendations['immediate_dispatches'].append(dispatch_recommendation)
                    recommendations['summary']['immediate_action'] += 1
                    
                    # Track overflow prevention
                    if any(keyword in prediction.get('reason', '') for keyword in ['OVERFLOW', 'EMERGENCY', 'CRITICAL']):
                        recommendations['overflow_prevented'].append(bin_data.get('id'))
                        
                elif prediction['delay_min'] > 0:
                    recommendations['scheduled_dispatches'].append(dispatch_recommendation)
                    recommendations['summary']['scheduled_action'] += 1
                    
                    # Accumulate fuel savings
                    fuel_savings = prediction.get('fuel_savings_min', 0)
                    if fuel_savings > 0:
                        total_fuel_savings += fuel_savings
                        
                else:
                    recommendations['summary']['no_action'] += 1
                    
            except Exception as e:
                logger.error(f"Error processing bin {bin_data.get('id', 'unknown')}: {e}")
                # Default to immediate dispatch for safety
                recommendations['immediate_dispatches'].append({
                    'bin_id': bin_data.get('id'),
                    'prediction': {'dispatch': 'now', 'delay_min': 0, 'reason': f'Error: {str(e)}'},
                    'urgency': {'enhanced_urgency': 0.8}
                })
                recommendations['summary']['immediate_action'] += 1
        
        recommendations['fuel_savings_estimate'] = total_fuel_savings
        
        return recommendations

    def integrate_with_existing_optimization(self, optimization_result: Dict, 
                                           current_time_seconds: float) -> Dict:
        """
        Integrate predictive dispatch recommendations with existing optimization results
        
        This allows the new predictive logic to enhance rather than replace the existing system
        """
        try:
            # Get predictive recommendations for all bins in the optimization result
            enhanced_routes = []
            
            for route in optimization_result.get('routes', []):
                enhanced_route = dict(route)
                
                # For each bin in the route, get predictive timing
                if 'bins' in route:
                    enhanced_bins = []
                    for bin_data in route['bins']:
                        prediction = self.predict_optimal_dispatch_window(bin_data, current_time_seconds)
                        urgency = self.enhance_urgency_score_with_traffic_prediction(bin_data, current_time_seconds)
                        
                        enhanced_bin = dict(bin_data)
                        enhanced_bin['predictive_dispatch'] = prediction
                        enhanced_bin['enhanced_urgency'] = urgency
                        enhanced_bins.append(enhanced_bin)
                    
                    enhanced_route['bins'] = enhanced_bins
                
                enhanced_routes.append(enhanced_route)
            
            # Return enhanced optimization result
            enhanced_result = dict(optimization_result)
            enhanced_result['routes'] = enhanced_routes
            enhanced_result['predictive_enhancement'] = True
            
            return enhanced_result
            
        except Exception as e:
            logger.error(f"Error integrating predictive dispatch: {e}")
            return optimization_result  # Return original if enhancement fails