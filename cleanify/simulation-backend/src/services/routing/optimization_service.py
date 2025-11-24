from typing import Dict, List, Optional
from services.external.vroom_service import VROOMService

class OptimizationService:
    """Route optimization combining knapsack algorithms with VROOM routing"""
    
    def __init__(self, vroom_service: VROOMService = None):
        self.vroom_service = vroom_service or VROOMService()
        self.urgency_weights = {
            'FILL': 0.30,
            'FILL_RATE': 0.50,
            'TIME': 0.20
        }
    
    def optimize_truck_routes_with_vroom(
        self,
        trucks_data: List[Dict],
        bins_data: List[Dict],
        depot_data: Optional[Dict] = None,
        current_time: float = None,
        preferred_bin_ids: Optional[set] = None,
    ) -> Dict:
        """
        Main optimization: Knapsack for capacity + VROOM for routing
        
        Workflow:
        1. Select bins (optionally filtered by preferred IDs) up to available truck capacity
        2. Use VROOM to optimize which truck goes to which bins
        3. Return optimized routes
        """
        try:
            selected_bins = self._select_candidate_bins(
                trucks_data, bins_data, current_time, preferred_bin_ids
            )
            
            if not selected_bins:
                return {
                    "status": "success",
                    "routes": [],
                    "optimization_used": "No bins to collect"
                }
            
            # Step 2: Use VROOM to optimize truck-to-bin assignments
            vroom_result = self.vroom_service.optimize_vehicle_routes(
                trucks_data, selected_bins, depot_data
            )
            
            return vroom_result
            
        except Exception as e:
            print(f"⚠️ Optimization error: {e}")
            return self._fallback_optimization(trucks_data, bins_data, current_time, preferred_bin_ids)
    
    def _select_candidate_bins(
        self,
        trucks_data: List[Dict],
        bins_data: List[Dict],
        current_time: float = None,
        preferred_bin_ids: Optional[set] = None,
    ) -> List[Dict]:
        idle_trucks = [t for t in trucks_data if t.get('status') == 'idle']
        if not idle_trucks:
            return []

        available_capacity = self._calculate_available_capacity(idle_trucks)
        preferred_set = set(preferred_bin_ids) if preferred_bin_ids else None

        urgent_bins: List[Dict] = []
        near_threshold_bins: List[Dict] = []

        for bin_data in bins_data:
            bin_id = bin_data.get('id')
            if preferred_set and bin_id not in preferred_set:
                continue

            if self._needs_collection(bin_data, current_time):
                urgent_bins.append(bin_data)
            elif self._is_near_threshold(bin_data, current_time):
                near_threshold_bins.append(bin_data)

        candidate_bins = urgent_bins or near_threshold_bins
        bypass_check = False if urgent_bins else True

        if not candidate_bins:
            return []

        candidate_bins.sort(
            key=lambda b: self.calculate_urgency_score(b, candidate_bins)['total'],
            reverse=True
        )

        # Estimate traffic data defaults
        for bin_data in candidate_bins:
            bin_data['traffic_density'] = bin_data.get('traffic_density', 1.0)
            bin_data['travel_time_hours'] = bin_data.get('travel_time_hours', 0.1)

        return self._select_optimal_bins(
            candidate_bins, available_capacity, current_time, bypass_needs_check=bypass_check
        )

    def _calculate_available_capacity(self, idle_trucks: List[Dict]) -> int:
        total_capacity = 0
        for truck in idle_trucks:
            cap = truck.get('capacity', 1000)
            load = truck.get('currentLoad', 0)
            total_capacity += max(0, cap - load)
        return max(0, int(total_capacity * 0.95))

    def _is_near_threshold(self, bin_data: Dict, current_time: float = None) -> bool:
        threshold_slack = 5.0
        soon_hours = 1.0

        try:
            threshold = bin_data.get('dynamic_threshold', bin_data.get('threshold', 80))
            fill_level = bin_data.get('fillLevel', 0)
            capacity = bin_data.get('capacity', 500)
            fill_rate = bin_data.get('fillRate', 0)
            if fill_level >= (threshold - threshold_slack):
                return True
            if fill_rate <= 0:
                return False
            liters_needed = max(0.0, ((threshold - fill_level) / 100.0) * capacity)
            hours_to_threshold = liters_needed / fill_rate if fill_rate else float('inf')
            return 0 < hours_to_threshold <= soon_hours
        except Exception:
            return False
    
    def _select_optimal_bins(
        self,
        candidate_bins: List[Dict],
        available_capacity: float,
        current_time: float = None,
        bypass_needs_check: bool = False,
    ) -> List[Dict]:
        """Use knapsack to select optimal bins from provided candidates."""
        if not candidate_bins or available_capacity <= 0:
            return []
        
        # Prepare knapsack items
        items = []
        for bin_data in candidate_bins:
            traffic_density = bin_data.get('traffic_density', 1.0)
            travel_time_hours = bin_data.get('travel_time_hours', 0.0)

            if bypass_needs_check:
                last_collection = bin_data.get('lastCollection') or bin_data.get('last_collection', 0)
                if current_time and last_collection > 0:
                    try:
                        minutes_since = (current_time - last_collection) / 60
                        if minutes_since < 30:
                            continue
                    except Exception:
                        pass
                if bin_data.get('fillLevel', 0) < 15:
                    continue
            else:
                if not self._needs_collection(bin_data, current_time):
                    continue

            waste_amount = (bin_data['fillLevel'] / 100) * bin_data['capacity']
            bin_data['traffic_density'] = traffic_density
            bin_data['travel_time_hours'] = travel_time_hours
            urgency = self.calculate_urgency_score(bin_data, candidate_bins)
            if waste_amount <= available_capacity:
                items.append({
                    'bin_data': bin_data,
                    'weight': int(waste_amount),
                    'value': int(urgency['total'])
                })

        if not items:
            return []

        # Solve knapsack problem
        selected_bins = self.solve_knapsack(items, int(available_capacity))
        return selected_bins
    
    def _needs_collection(self, bin_data: Dict, current_time: float = None) -> bool:
        """Check if bin needs collection based on threshold and urgency"""
        fill_level = bin_data.get('fillLevel', 0)
        threshold = bin_data.get('dynamic_threshold', bin_data.get('threshold', 80))
        
        # CRITICAL: Prevent collection of recently collected bins
        last_collection = bin_data.get('lastCollection') or bin_data.get('last_collection', 0)
        if current_time and last_collection > 0:
            time_since_collection_minutes = (current_time - last_collection) / 60
            # Don't collect bins that were collected less than 30 minutes ago
            if time_since_collection_minutes < 30:
                return False
        
        # CRITICAL: Don't collect nearly empty bins (waste of fuel)
        if fill_level < 5:  # Less than 5% - not worth collecting
            return False
            
        # Minimum collection threshold - don't collect unless at least 15% full
        if fill_level < 15:
            return False
        
        # Emergency collection
        if fill_level >= 95:
            return True
        
        # Threshold-based collection
        if fill_level >= threshold:
            return True
        
        # High urgency collection - but only if bin has substantial waste
        if fill_level >= 25:  # Only consider urgency for bins with >25% fill
            urgency = self.calculate_urgency_score(bin_data)
            if urgency['total'] >= 75:  # High urgency threshold
                return True
        
        return False
    
    def _fallback_optimization(
        self,
        trucks_data: List[Dict],
        bins_data: List[Dict],
        current_time: float = None,
        preferred_bin_ids: Optional[set] = None,
    ) -> Dict:
        """Fallback to simple assignment if VROOM is unavailable"""
        idle_trucks = [t for t in trucks_data if t.get('status') == 'idle']
        if not idle_trucks:
            return {"status": "fallback", "routes": [], "optimization_used": "No idle trucks"}

        preferred_set = set(preferred_bin_ids) if preferred_bin_ids else None
        candidate_bins = [
            b for b in bins_data
            if self._needs_collection(b, current_time)
            and (not preferred_set or b.get('id') in preferred_set)
        ]

        if not candidate_bins:
            return {"status": "fallback", "routes": [], "optimization_used": "No bins to collect"}

        candidate_bins.sort(
            key=lambda b: self.calculate_urgency_score(b)['total'],
            reverse=True
        )

        assigned = set()
        routes = []
        for truck in idle_trucks:
            next_bin = next((b for b in candidate_bins if b['id'] not in assigned), None)
            if not next_bin:
                break
            assigned.add(next_bin['id'])
            routes.append({
                "truck_id": truck['id'],
                "route": [next_bin['id']],
                "dispatch": "now",
                "delay_min": 0,
                "reason": f"Fallback assignment - urgent bin {next_bin['id']}"
            })

        return {
            "status": "fallback",
            "routes": routes,
            "optimization_used": "Simple Bin Assignment"
        }
    
    # Existing methods (unchanged)
    def solve_knapsack(self, items: List[Dict], capacity: int) -> List[Dict]:
        """0/1 Knapsack algorithm for optimal bin selection"""
        if not items or capacity <= 0:
            return []
        
        n = len(items)
        dp = [[0 for _ in range(capacity + 1)] for _ in range(n + 1)]
        
        # Fill the dp table
        for i in range(1, n + 1):
            for w in range(1, capacity + 1):
                weight = items[i-1]['weight']
                value = items[i-1]['value']
                
                if weight <= w:
                    dp[i][w] = max(
                        dp[i-1][w],  # Don't include item
                        dp[i-1][w-weight] + value  # Include item
                    )
                else:
                    dp[i][w] = dp[i-1][w]
        
        # Backtrack to find selected items
        selected = []
        w = capacity
        for i in range(n, 0, -1):
            if dp[i][w] != dp[i-1][w]:
                selected.append(items[i-1]['bin_data'])
                w -= items[i-1]['weight']
        
        return selected
    
    def calculate_urgency_score(
        self,
        bin_data: Dict,
        context_bins: Optional[List[Dict]] = None,
    ) -> Dict:
        """Calculate urgency score with optional candidate normalization"""
        try:
            # Use context bins for normalization if provided
            bins_for_normalization = context_bins or [bin_data]

            # Get fill rate range for normalization
            all_fill_rates = [b.get('fillRate', 3.5) for b in bins_for_normalization]
            min_fill_rate = min(all_fill_rates) if all_fill_rates else 0
            max_fill_rate = max(all_fill_rates) if all_fill_rates else 10

            # Calculate individual scores
            fill_level = bin_data.get('fillLevel', 0)
            fill_rate = bin_data.get('fillRate', 3.5)

            fill_score = fill_level

            # Normalize fill rate score
            if max_fill_rate > min_fill_rate:
                fill_rate_score = (fill_rate - min_fill_rate) / (max_fill_rate - min_fill_rate) * 100
            else:
                fill_rate_score = 0

            # Calculate time urgency
            time_to_overflow = self._calculate_time_to_overflow_safe(bin_data)
            time_urgency_score = self._calculate_time_urgency_score(time_to_overflow)

            # --- TRAFFIC-AWARE LOGIC ---
            # Estimate travel time to bin (with traffic)
            # For now, use a simple traffic multiplier from bin_data if available
            traffic_density = bin_data.get('traffic_density', 1.0)
            travel_time_hours = bin_data.get('travel_time_hours', 0.0)
            # If not present, fallback to 0
            traffic_delay_score = 0
            if travel_time_hours > 0:
                # If travel time is significant compared to time to overflow, increase urgency
                if time_to_overflow > 0:
                    traffic_delay_score = min(100, (travel_time_hours * traffic_density) / max(0.1, time_to_overflow) * 100)
                else:
                    traffic_delay_score = 100

            # Add traffic delay score to urgency (weight can be tuned)
            urgency_score = (
                self.urgency_weights['FILL'] * fill_score +
                self.urgency_weights['TIME'] * time_urgency_score +
                self.urgency_weights['FILL_RATE'] * fill_rate_score +
                0.15 * traffic_delay_score
            )

            priority = self._get_priority(urgency_score)

            return {
                'total': round(urgency_score, 2),
                'priority': priority,
                'components': {
                    'fill': round(fill_score, 1),
                    'fill_rate': round(fill_rate_score, 1),
                    'time': round(time_urgency_score, 1),
                    'traffic_delay': round(traffic_delay_score, 1)
                },
                'reasoning': self._generate_reasoning(fill_score, fill_rate_score, priority) + f" | Traffic delay: {round(traffic_delay_score,1)}"
            }

        except Exception as e:
            print(f"⚠ Urgency calculation failed: {e}")
            return {'total': 50.0, 'priority': 'MEDIUM'}
    
    def _calculate_time_to_overflow_safe(self, bin_data: Dict) -> float:
        """Safe calculation of time to overflow in hours"""
        fill_level = bin_data.get('fillLevel', 0)
        capacity = bin_data.get('capacity', 500)
        fill_rate = bin_data.get('fillRate', 3.5)
        # --- TRAFFIC-AWARE LOGIC ---
        travel_time_hours = bin_data.get('travel_time_hours', 0.0)
        traffic_density = bin_data.get('traffic_density', 1.0)

        if fill_level >= 100:
            return 0.0

        if fill_rate <= 0:
            return float('inf')

        current_fill_liters = (fill_level / 100) * capacity
        remaining_capacity = capacity - current_fill_liters

        if remaining_capacity <= 0:
            return 0.0

        # Subtract travel time (with traffic) from time to overflow
        time_to_overflow = max(0.0, remaining_capacity / fill_rate)
        time_to_overflow -= travel_time_hours * traffic_density
        return max(0.0, time_to_overflow)
    
    def _calculate_time_urgency_score(self, time_to_overflow: float) -> float:
        """Calculate urgency score based on time to overflow"""
        max_safe_time = 8  # hours
        if time_to_overflow >= max_safe_time:
            return 0
        else:
            score = (max_safe_time - time_to_overflow) / max_safe_time * 100
            return max(0, min(100, score))
    
    def _get_priority(self, score: float) -> str:
        """Convert score to priority level"""
        thresholds = {'URGENT': 85, 'HIGH': 70, 'MEDIUM': 50, 'LOW': 0}
        
        if score >= thresholds['URGENT']: return 'URGENT'
        if score >= thresholds['HIGH']: return 'HIGH'
        if score >= thresholds['MEDIUM']: return 'MEDIUM'
        return 'LOW'
    
    def _generate_reasoning(self, fill_score: float, fill_rate_score: float, priority: str) -> str:
        """Generate human-readable reasoning"""
        reasons = []
        
        if fill_score > 100: reasons.append("Bin overflowing")
        elif fill_score > 90: reasons.append("Bin nearly full")
        elif fill_score > 70: reasons.append("Bin getting full")
        
        if fill_rate_score > 80: reasons.append("High fill rate")
        elif fill_rate_score > 60: reasons.append("Moderate fill rate")
        
        return f"{priority} priority: {', '.join(reasons)}" if reasons else f"{priority} priority"