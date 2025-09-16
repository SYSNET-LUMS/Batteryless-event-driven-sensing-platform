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
    
    def optimize_truck_routes_with_vroom(self, trucks_data: List[Dict], clusters: Dict, 
                                       depot_data: Optional[Dict] = None, 
                                       current_time: float = None,
                                       preferred_bin_ids: Optional[set] = None) -> Dict:
        """
        Main optimization: Knapsack for capacity + VROOM for routing
        
        Workflow:
        1. For each cluster, use knapsack to select bins within truck capacity
        2. Use VROOM to optimize which truck goes to which selected bins
        3. Return optimized routes
        """
        try:
            # Step 1: Select bins using knapsack within each cluster
            selected_bins = self._select_bins_from_clusters(
                trucks_data, clusters, current_time, preferred_bin_ids
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
            return self._fallback_optimization(trucks_data, clusters, current_time)
    
    def _select_bins_from_clusters(self, trucks_data: List[Dict], clusters: Dict, 
                                  current_time: float = None,
                                  preferred_bin_ids: Optional[set] = None) -> List[Dict]:
        """
        Use knapsack to select optimal bins from each cluster
        
        This replaces the manual assignment tracking approach
        """
        all_selected_bins = []
        idle_trucks = [t for t in trucks_data if t.get('status') == 'idle']
        
        if not idle_trucks:
            return []
        
        # Calculate total available capacity (use full remaining capacity across idle trucks)
        total_capacity = 0
        for t in idle_trucks:
            cap = t.get('capacity', 1000)
            load = t.get('currentLoad', 0)
            total_capacity += max(0, cap - load)
        # Allow near-full utilization; keep a tiny 5% safety margin to avoid slight overfill rounding
        available_capacity = max(0, int(total_capacity * 0.95))
        
        # Process each cluster
        for cluster_id, cluster_bins in clusters.items():
            # Filter bins that need collection
            urgent_bins = [
                bin_data for bin_data in cluster_bins
                if self._needs_collection(bin_data, current_time)
            ]

            # Also opportunistically include nearby bins about to reach threshold soon
            def time_to_threshold_hours(b: Dict) -> float:
                try:
                    fill_level = b.get('fillLevel', 0)
                    capacity = b.get('capacity', 500)
                    fill_rate = b.get('fillRate', 0)
                    threshold = b.get('dynamic_threshold', b.get('threshold', 80))
                    if fill_level >= threshold:
                        return 0.0
                    if fill_rate <= 0:
                        return float('inf')
                    liters_needed = max(0.0, ((threshold - fill_level) / 100.0) * capacity)
                    return liters_needed / fill_rate
                except Exception:
                    return float('inf')

            soon_hours = 1.0
            threshold_slack = 5.0
            for b in cluster_bins:
                if b in urgent_bins:
                    continue
                th = b.get('dynamic_threshold', b.get('threshold', 80))
                fl = b.get('fillLevel', 0)
                if fl >= (th - threshold_slack) or time_to_threshold_hours(b) <= soon_hours:
                    urgent_bins.append(b)

            # If a preferred queue is provided, restrict to those IDs
            if preferred_bin_ids:
                urgent_bins = [b for b in urgent_bins if b.get('id') in preferred_bin_ids]
            
            if not urgent_bins:
                continue
            
            # Select optimal bins from this cluster using knapsack
            cluster_selected = self._select_optimal_bins_from_cluster(
                urgent_bins, available_capacity, current_time
            )
            
            # Add to global selection
            all_selected_bins.extend(cluster_selected)
            
            # Reduce available capacity
            used_capacity = sum(
                (bin_data['fillLevel'] / 100) * bin_data['capacity']
                for bin_data in cluster_selected
            )
            available_capacity = max(0, available_capacity - used_capacity)
            
            # Continue evaluating clusters while any capacity remains
            if available_capacity <= 0:
                break
        
        return all_selected_bins
    
    def _select_optimal_bins_from_cluster(self, cluster_bins: List[Dict], 
                                        available_capacity: float,
                                        current_time: float = None,
                                        bypass_needs_check: bool = False) -> List[Dict]:
        """Use knapsack to select optimal bins from a single cluster"""
        if not cluster_bins or available_capacity <= 0:
            return []
        
        # Prepare knapsack items
        items = []
        for bin_data in cluster_bins:
            # Apply safety filters
            if bypass_needs_check:
                # Even in relaxed mode, enforce recency and minimum fill safeguards
                last_collection = bin_data.get('lastCollection') or bin_data.get('last_collection', 0)
                if current_time and last_collection > 0:
                    try:
                        minutes_since = (current_time - last_collection) / 60
                        if minutes_since < 30:
                            continue  # too recent
                    except Exception:
                        pass
                # Skip trivially low-fill to save fuel
                if bin_data.get('fillLevel', 0) < 15:
                    continue
            else:
                # Strict mode: only include bins that truly need collection
                if not self._needs_collection(bin_data, current_time):
                    continue
            waste_amount = (bin_data['fillLevel'] / 100) * bin_data['capacity']
            urgency = self.calculate_urgency_score(bin_data, cluster_bins)
            print(urgency)
            
            # Only include bins that fit in available capacity
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
    
    def _fallback_optimization(self, trucks_data: List[Dict], clusters: Dict, 
                              current_time: float = None) -> Dict:
        """Fallback to simple assignment if VROOM is unavailable"""
        routes = []
        idle_trucks = [t for t in trucks_data if t.get('status') == 'idle']
        
        # Simple assignment: one truck per cluster's most urgent bin
        truck_index = 0
        for cluster_id, cluster_bins in clusters.items():
            if truck_index >= len(idle_trucks):
                break
            
            # Find most urgent bin in cluster
            urgent_bins = [b for b in cluster_bins if self._needs_collection(b, current_time)]
            if not urgent_bins:
                continue
            
            # Sort by urgency and take the most urgent
            urgent_bins.sort(
                key=lambda b: self.calculate_urgency_score(b)['total'],
                reverse=True
            )
            
            most_urgent = urgent_bins[0]
            truck = idle_trucks[truck_index]
            
            routes.append({
                "truck_id": truck['id'],
                "route": [most_urgent['id']],
                "dispatch": "now",
                "delay_min": 0,
                "reason": f"Fallback assignment - most urgent in cluster {cluster_id}"
            })
            
            truck_index += 1
        
        return {
            "status": "fallback",
            "routes": routes,
            "optimization_used": "Simple Cluster Assignment"
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
    
    def calculate_urgency_score(self, bin_data: Dict, 
                              context_bins: Optional[List[Dict]] = None) -> Dict:
        """Calculate urgency score with optional cluster normalization"""
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
            
            # Calculate weighted total
            urgency_score = (
                self.urgency_weights['FILL'] * fill_score +
                self.urgency_weights['TIME'] * time_urgency_score +
                self.urgency_weights['FILL_RATE'] * fill_rate_score
            )
            
            priority = self._get_priority(urgency_score)
            
            return {
                'total': round(urgency_score, 2),
                'priority': priority,
                'components': {
                    'fill': round(fill_score, 1),
                    'fill_rate': round(fill_rate_score, 1),
                    'time': round(time_urgency_score, 1)
                },
                'reasoning': self._generate_reasoning(fill_score, fill_rate_score, priority)
            }
            
        except Exception as e:
            print(f"⚠ Urgency calculation failed: {e}")
            return {'total': 50.0, 'priority': 'MEDIUM'}
    
    def _calculate_time_to_overflow_safe(self, bin_data: Dict) -> float:
        """Safe calculation of time to overflow in hours"""
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