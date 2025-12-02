from typing import Dict, List, Optional
from services.external.osrm_service import OSRMService
from config.settings import Config

class SimulationService:
    def calculate_urgency_score(self, bin_data: Dict) -> Dict:
        import math
        fill = bin_data.get('fillLevel', 0)
        rate = bin_data.get('fillRate', 0)
        cap = bin_data.get('capacity', 500)
        threshold = bin_data.get('dynamic_threshold', bin_data.get('threshold', 80))
        time_to_threshold = self._time_to_threshold_hours(bin_data, threshold)
        # Also compute time to overflow (100%) for stronger escalation
        time_to_overflow = self._time_to_threshold_hours(bin_data, 100.0)
        # Zero fill rate alert
        if rate <= 0:
            print(f"⚠️ ALERT: Bin {bin_data.get('id','?')} has zero fill rate. Sensor or data issue.")

        # Configurable weights
        w_fill = getattr(self.config, 'URGENCY_WEIGHT_FILL', 0.5)
        w_rate = getattr(self.config, 'URGENCY_WEIGHT_RATE', 0.3)
        w_time = getattr(self.config, 'URGENCY_WEIGHT_TIME', 0.2)

        # Sigmoid for time-to-threshold (bins close to threshold get higher urgency)
        time_urgency = 1 / (1 + math.exp(time_to_threshold - 4))  # 4 hours as inflection

        # Additional escalation if time to overflow is short
        overflow_urgency = 0.0
        if time_to_overflow <= 0.5:  # <30 minutes to overflow
            overflow_urgency = 1.0
        elif time_to_overflow <= 1.0:  # <60 minutes
            overflow_urgency = 0.7
        elif time_to_overflow <= 2.0:  # <2 hours
            overflow_urgency = 0.4
        else:
            overflow_urgency = 0.0

        # Base urgency
        urgency = (
            w_fill * (fill / 100) +
            w_rate * (rate / 50) +
            w_time * time_urgency
        )

        # Blend in overflow urgency (weighted so it can dominate near overflow)
        urgency = min(1.2, urgency + 0.6 * overflow_urgency)
        # Escalate urgency if bin is repeatedly just below threshold
        threshold = bin_data.get('dynamic_threshold', bin_data.get('threshold', 80))
        near_threshold = (fill >= (threshold - 2)) and (fill < threshold)
        if near_threshold:
            if 'near_threshold_count' not in bin_data:
                bin_data['near_threshold_count'] = 1
            else:
                bin_data['near_threshold_count'] += 1
            if bin_data['near_threshold_count'] >= 3:
                urgency = min(1.0, urgency + 0.2)  # escalate urgency
        else:
            bin_data['near_threshold_count'] = 0
        urgency = max(0.0, min(1.0, urgency))  # Clamp between 0 and 1
        return {'score': urgency}
    """Manages simulation state and coordinates updates"""
    
    def __init__(self, osrm_service: OSRMService = None):
        self.osrm_service = osrm_service or OSRMService()
        self.config = Config()
        self.simulation_start_hour = self.config.SIMULATION_START_HOUR
        self.travel_time_cache = {}
    
    def calculate_dynamic_thresholds(self, bins_data: List[Dict], 
                                   simulation_time_seconds: float,
                                   depot_data: Optional[Dict] = None) -> List[Dict]:
        """Calculate dynamic thresholds for all bins with smooth, urgency-weighted neighbor adjustment"""
        updated_bins = []
        from utils.distance import calculate_distance_km

        # Precompute urgency for all bins using the dedicated function
        bin_urgencies = {}
        for b in bins_data:
            try:
                urgency_data = self.calculate_urgency_score(b)
                urgency = urgency_data.get('score', 0.5)
                bin_urgencies[b['id']] = urgency
            except Exception:
                bin_urgencies[b['id']] = 0.5

        for bin_data in bins_data:
            try:
                # 1) Base DT using travel time, traffic and safety buffer
                if depot_data:
                    base_dt = self._calculate_single_dynamic_threshold(
                        bin_data, simulation_time_seconds, depot_data
                    )
                else:
                    base_dt = bin_data.get('threshold', 80)

                # 2) Neighbor-aware adjustment
                radius_km = 0.5
                soon_hours = 1.0
                threshold_slack = 5.0

                # Find neighbors that are close to threshold or will reach soon
                neighbor_scores = []
                for other in bins_data:
                    if other is bin_data:
                        continue
                    d_km = calculate_distance_km(
                        bin_data['lat'], bin_data['lng'], other['lat'], other['lng']
                    )
                    if d_km > radius_km:
                        continue
                    other_dt = other.get('dynamic_threshold', other.get('threshold', 80))
                    t_to_dt = self._time_to_threshold_hours(other, other_dt)
                    fill = other.get('fillLevel', 0)
                    # Score: proximity * urgency * (near threshold or soon)
                    proximity = max(0.0, 1.0 - (d_km / radius_km))
                    near_thresh = 1.0 if (fill >= (other_dt - threshold_slack) or t_to_dt <= soon_hours) else 0.0
                    score = proximity * bin_urgencies.get(other['id'], 0.5) * near_thresh
                    if score > 0:
                        neighbor_scores.append(score)

                # Aggregate neighbor influence
                if neighbor_scores:
                    # Use a smooth function: reduction = max(3, min(12, 10 * sigmoid(sum)))
                    import math
                    agg = sum(neighbor_scores)
                    # Sigmoid squashes large values smoothly
                    reduction = 3.0 + 9.0 * (1 / (1 + math.exp(-agg + 1.5)))
                    adjusted_dt = max(50.0, min(95.0, base_dt - reduction))
                else:
                    adjusted_dt = base_dt

                bin_data['dynamic_threshold'] = adjusted_dt
                updated_bins.append(bin_data)
            except Exception as e:
                print(f"Error calculating threshold for {bin_data.get('id')}: {e}")
                bin_data['dynamic_threshold'] = bin_data.get('threshold', 80)
                updated_bins.append(bin_data)

        return updated_bins
    
    def update_bin_fill_levels(self, bins_data: List[Dict], 
                             time_delta_seconds: float) -> tuple:
        """Update bin fill levels and return bins that hit thresholds"""
        bins_that_hit_threshold = []
        updated_bins = []
        
        for bin_data in bins_data:
            try:
                old_fill = bin_data['fillLevel']
                old_threshold = bin_data.get('dynamic_threshold', bin_data.get('threshold', 80))
                
                # Update fill level
                hours_passed = time_delta_seconds / 3600
                increase = bin_data['fillRate'] * hours_passed
                bin_data['fillLevel'] = min(100, bin_data['fillLevel'] + increase)
                
                # Check if bin crossed threshold
                if old_fill < old_threshold and bin_data['fillLevel'] >= old_threshold:
                    bins_that_hit_threshold.append(bin_data['id'])
                
                updated_bins.append(bin_data)
                
            except Exception as e:
                print(f"⚠️ Error updating bin {bin_data.get('id', 'unknown')}: {e}")
                updated_bins.append(bin_data)  # Add unchanged bin
        
        return updated_bins, bins_that_hit_threshold
    
    def get_traffic_info(self, simulation_time_seconds: float) -> Dict:
        """Get current traffic information - simplified for minimalist approach"""
        try:
            start_hour = self.simulation_start_hour
            current_time_min = (start_hour * 60) + (simulation_time_seconds // 60)
            current_hour = (current_time_min // 60) % 24
            
            # Simple traffic logic: heavy during configured hours
            heavy_hours = self.config.TRAFFIC_HEAVY_HOURS
            is_heavy = current_hour in heavy_hours
            current_density = self.config.TRAFFIC_MULTIPLIER if is_heavy else 1.0
            
            return {
                'current_density': current_density,
                'current_hour': current_hour,
                'time_of_day': f"{current_hour:02d}:{(current_time_min % 60):02d}",
                'traffic_level': 'Heavy' if is_heavy else 'Light'
            }
        except Exception as e:
            print(f"⚠️ Error getting traffic info: {e}")
            return {
                'current_density': 1.0,
                'current_hour': 7,
                'time_of_day': "07:00",
                'traffic_level': 'Unknown'
            }
    
    def _calculate_single_dynamic_threshold(self, bin_data: Dict, 
                                          simulation_time_seconds: float,
                                          depot_data: Dict) -> float:
        """Calculate dynamic threshold for a single bin"""
        try:
            C = bin_data['capacity']
            r = bin_data['fillRate']
            current_fill = bin_data.get('fillLevel', 0)
            # Guard
            if r <= 0:
                return bin_data.get('threshold', 80)
            
            # Get travel time to depot
            base_travel_hours = self._get_travel_time_to_depot(bin_data, depot_data)
            
            # Apply traffic multiplier based on current hour
            current_hour = int((simulation_time_seconds / 3600 + self.simulation_start_hour) % 24)
            is_heavy = current_hour in self.config.TRAFFIC_HEAVY_HOURS
            traffic_density = self.config.TRAFFIC_MULTIPLIER if is_heavy else 1.0
            travel_with_traffic = base_travel_hours * traffic_density
            
            # Add collection time and safety buffer
            collection_hours = 5 / 60  # 5 minutes
            
            # Adaptive safety buffer based on fill rate and traffic
            traffic_risk = traffic_density if traffic_density > 2 else 1.0
            if r > 30:
                safety_buffer = 1.2 * traffic_risk
            elif r > 20:
                safety_buffer = 1.0 * traffic_risk
            else:
                safety_buffer = 0.7 * traffic_risk
            
            T_min = travel_with_traffic + collection_hours + safety_buffer
            
            # Calculate base threshold using the theoretical formula (time for remaining capacity fraction)
            base_threshold = 100 * (1 - (r * T_min / C))
            
            # Projected time until overflow and until base_threshold
            time_to_overflow = self._time_to_threshold_hours(bin_data, 100.0)
            time_to_base_threshold = self._time_to_threshold_hours(bin_data, base_threshold)

            # If truck cannot arrive before overflow, aggressively lower threshold
            arrival_feasible = time_to_overflow > T_min
            if not arrival_feasible:
                base_threshold = min(base_threshold, current_fill + 2)  # force immediate dispatch
            else:
                # If arrival is just barely feasible (< 1.2x slack), tighten threshold a bit
                if time_to_overflow < (T_min * 1.2):
                    base_threshold -= 5

            # If time to base threshold is already very short (< travel time), drop further
            if time_to_base_threshold <= T_min:
                base_threshold = min(base_threshold, current_fill + 5)
            
            # Apply fill-level adjustment: lower threshold as bin gets fuller
            # This creates urgency for bins that are already quite full
            fill_urgency_factor = 1.0
            if current_fill >= 70:
                # High fill: reduce threshold significantly (more urgent)
                fill_urgency_factor = 0.85 - (current_fill - 70) * 0.01  # 0.85 to 0.55
            elif current_fill >= 50:
                # Medium fill: reduce threshold moderately
                fill_urgency_factor = 0.95 - (current_fill - 50) * 0.005  # 0.95 to 0.85
            # Low fill (< 50%): no adjustment needed
            
            adjusted_threshold = base_threshold * fill_urgency_factor

            # Final safety: never set DT above current fill + realistic growth window
            # Compute expected fill growth during arrival
            expected_growth = (r * T_min) / C * 100  # percent points
            upper_cap = min(95, current_fill + expected_growth + 10)
            adjusted_threshold = min(adjusted_threshold, upper_cap)
            
            # Final threshold with proper bounds
            final_threshold = max(50, min(95, adjusted_threshold))
            
            return final_threshold
            
        except Exception as e:
            print(f"⚠️ Dynamic threshold calculation error: {e}")
            return bin_data.get('threshold', 80)
  
    def _get_travel_time_to_depot(self, bin_data: Dict, depot_data: Dict, truck_data: Dict = None) -> float:
        """Get travel time from bin to depot in hours (cached) using actual truck speed"""
        # Create cache key from coordinates and truck speed
        truck_speed = truck_data.get('speed', 40.0) if truck_data else 40.0  # Use actual truck speed or default
        cache_key = f"{bin_data['lat']},{bin_data['lng']}->{depot_data['lat']},{depot_data['lng']}-{truck_speed}"
        
        # Return cached value if exists
        if cache_key in self.travel_time_cache:
            return self.travel_time_cache[cache_key]
        
        try:
            # Try OSRM first for base route time
            base_travel_time_min = self.osrm_service.get_travel_time_with_traffic(
                bin_data['lat'], bin_data['lng'],
                depot_data['lat'], depot_data['lng'],
                traffic_multiplier=1.0
            )
            
            # Apply truck speed factor to OSRM time
            # OSRM gives time at ~40 km/h average, adjust for actual truck speed
            osrm_speed = 40.0  # OSRM baseline speed
            speed_factor = osrm_speed / truck_speed  # Slower trucks take longer
            travel_time_hours = (base_travel_time_min * speed_factor) / 60
            
        except:
            # Fallback calculation using ACTUAL truck speed
            from utils.distance import calculate_distance_km
            distance_km = calculate_distance_km(
                bin_data['lat'], bin_data['lng'],
                depot_data['lat'], depot_data['lng']
            )
            travel_time_hours = distance_km / truck_speed  # Use actual truck speed instead of hardcoded 30
        
        # Cache the result
        self.travel_time_cache[cache_key] = travel_time_hours
        return travel_time_hours

    def _time_to_threshold_hours(self, bin_data: Dict, target_threshold: float) -> float:
        """Estimate hours until bin reaches a given threshold.
        Returns inf if fillRate <= 0. Uses simple linear projection.
        """
        try:
            fill_level = bin_data.get('fillLevel', 0)
            capacity = bin_data.get('capacity', 500)
            fill_rate = bin_data.get('fillRate', 0.0)
            if fill_level >= target_threshold:
                return 0.0
            if fill_rate <= 0:
                print(f"⚠️ ALERT: Bin {bin_data.get('id','?')} has zero fill rate. Sensor or data issue.")
                return float('inf')
            liters_needed = max(0.0, ((target_threshold - fill_level) / 100.0) * capacity)
            return liters_needed / fill_rate
        except Exception:
            return float('inf')
    
    def should_dispatch_now(self, simulation_time_seconds: float) -> bool:
        """Check if current time is good for dispatch (light traffic)"""
        traffic_info = self.get_traffic_info(simulation_time_seconds)
        return traffic_info['traffic_level'] == 'Light'