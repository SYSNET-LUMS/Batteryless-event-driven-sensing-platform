import logging
from typing import Dict, List, Set, Optional, Tuple, Callable
from services.clustering_service import ClusteringService
from services.traffic_service import TrafficManager
from utils.distance import calculate_distance_km

logger = logging.getLogger(__name__)

class ProactiveClusterDispatchService:
    """
    Proactive cluster dispatch service that prevents redundant truck dispatches 
    to the same cluster by:
    
    1. When a bin reaches DT, proactively check other bins in same cluster
    2. Add near-DT bins from same cluster to collection queue immediately
    3. Estimate truck capacity after collecting all assigned bins
    4. Only dispatch additional trucks if remaining capacity is insufficient
    """
    
    def __init__(self, clustering_service: Optional[ClusteringService] = None, 
                 clustering_callback: Optional[Callable] = None):
        self.clustering_service = clustering_service or ClusteringService()
        self.clustering_callback = clustering_callback  # Preferred: use agent's cached clustering
        self.traffic_manager = TrafficManager()
        
        # Parameters for proactive cluster management (simplified)
        self.cluster_radius_km = 0.6  # Nominal cluster radius (km) - informational
        self.proactive_dt_threshold_percent = 5.0  # Consider bins within 5% of DT
        self.proactive_time_window_hours = 1.0  # Add bins reaching DT within 1 hour
        self.capacity_safety_margin = 0.05  # 5% safety margin for capacity estimates
        # Scoring weights for selecting bins within a cluster (fill level, fill rate, proximity)
        self.score_weights = {'fill': 0.55, 'fill_rate': 0.30, 'proximity': 0.15}
        
        # Track active cluster assignments to prevent duplicate dispatches
        self.active_cluster_assignments: Dict[str, Dict] = {}  # cluster_id -> assignment_info
    
    def process_bin_reached_dt(self, trigger_bin: Dict, all_bins: List[Dict], 
                              all_trucks: List[Dict], current_time: float,
                              existing_collection_queue: List[str]) -> Dict:
        """
        Process when a bin reaches DT - proactively manage cluster collection.
        
        Returns:
            Dict with:
            - additional_bins_for_queue: List of bin IDs to add to collection queue
            - dispatch_recommendation: 'dispatch' or 'wait_for_existing_truck'
            - assigned_truck_id: ID of truck that should handle this cluster
            - estimated_capacity_after: Remaining capacity after all collections
            - reason: Explanation of decision
        """
        # Simplified cluster-scoped dispatch algorithm (single-truck per cluster)
        try:
            # Get clusters
            if self.clustering_callback:
                clusters = self.clustering_callback(all_bins)
            else:
                clusters = self.clustering_service.create_adaptive_clusters(all_bins)

            cluster_key, cluster_bins = self._find_bin_cluster(trigger_bin['id'], clusters)
            if not cluster_bins:
                return {
                    'additional_bins_for_queue': [],
                    'dispatch_recommendation': 'dispatch',
                    'assigned_truck_id': None,
                    'estimated_capacity_after': None,
                    'reason': 'Bin not found in any cluster - dispatch normally'
                }

            cluster_key = str(cluster_key) if cluster_key is not None else str(trigger_bin['id'])

            # If cluster already has active assignment, ask to wait for that truck
            if cluster_key in self.active_cluster_assignments:
                assignment = self.active_cluster_assignments[cluster_key]
                return {
                    'additional_bins_for_queue': [],
                    'dispatch_recommendation': 'wait_for_existing_truck',
                    'assigned_truck_id': assignment.get('truck_id'),
                    'estimated_capacity_after': assignment.get('total_load'),
                    'reason': 'Cluster already assigned to a truck'
                }

            # Build candidate set: cluster bins excluding recently collected and those already queued
            candidates = []
            for b in cluster_bins:
                if b.get('id') == trigger_bin.get('id'):
                    candidates.append(b)
                    continue
                if b.get('id') in existing_collection_queue:
                    continue
                # skip recently collected
                last_col = b.get('lastCollection') or b.get('last_collection', 0)
                if current_time and last_col and (current_time - last_col) / 60 < 30:
                    continue
                # only consider bins with non-trivial fill
                if b.get('fillLevel', 0) < 5:
                    continue
                candidates.append(b)

            # Ensure trigger bin is present
            if trigger_bin.get('id') not in [c['id'] for c in candidates]:
                candidates.insert(0, trigger_bin)

            # Score bins: higher fill, higher fill rate, closer to trigger bin
            def score_bin(b):
                fill = b.get('fillLevel', 0)
                fill_rate = b.get('fillRate', 0)
                # normalize fill_rate roughly to 0-100 scale assuming typical rates
                fr_score = min(100, (fill_rate / 10.0) * 100)
                dist_m = calculate_distance_km(trigger_bin.get('lat', 0), trigger_bin.get('lng', 0), b.get('lat', 0), b.get('lng', 0)) * 1000
                # proximity score: closer is better
                prox = max(0, 1 - (dist_m / 2000.0)) * 100
                w = self.score_weights
                return w['fill'] * fill + w['fill_rate'] * fr_score + w['proximity'] * prox

            for c in candidates:
                c['_score'] = score_bin(c)

            # Consider only idle trucks for full cluster dispatch; prefer trucks with enough capacity
            idle_trucks = [t for t in all_trucks if t.get('status') == 'idle']
            if not idle_trucks:
                return {
                    'additional_bins_for_queue': [c['id'] for c in candidates if c['id'] != trigger_bin['id']],
                    'dispatch_recommendation': 'dispatch',
                    'assigned_truck_id': None,
                    'estimated_capacity_after': None,
                    'reason': 'No idle trucks available'
                }

            best_choice = None
            best_choice_score = -1

            # Greedy selection by score for each truck
            for truck in idle_trucks:
                avail = truck.get('capacity', 1000) - truck.get('currentLoad', 0)
                avail = avail * (1 - self.capacity_safety_margin)
                # greedy pick highest-score bins until capacity used
                sorted_bins = sorted(candidates, key=lambda x: x['_score'], reverse=True)
                chosen = []
                used = 0.0
                total_score = 0.0
                for cb in sorted_bins:
                    vol = (cb.get('fillLevel', 0) / 100.0) * cb.get('capacity', 500)
                    if vol + used <= avail and vol > 0:
                        chosen.append(cb)
                        used += vol
                        total_score += cb['_score']

                # compute truck preference score (balance total_score and proximity)
                # distance from truck to cluster center
                center_lat = sum(b.get('lat', 0) for b in cluster_bins) / len(cluster_bins)
                center_lng = sum(b.get('lng', 0) for b in cluster_bins) / len(cluster_bins)
                dist_km = calculate_distance_km(truck.get('lat', 0), truck.get('lng', 0), center_lat, center_lng)
                distance_score = 1.0 / (1.0 + dist_km)
                choice_score = total_score * 0.7 + distance_score * 0.3

                if choice_score > best_choice_score and chosen:
                    best_choice_score = choice_score
                    best_choice = {
                        'truck': truck,
                        'chosen_bins': chosen,
                        'used_capacity': used,
                        'distance_km': dist_km,
                        'total_score': total_score
                    }

            if not best_choice:
                # Nothing fits in any truck - fall back to dispatch just the trigger bin
                return {
                    'additional_bins_for_queue': [],
                    'dispatch_recommendation': 'dispatch',
                    'assigned_truck_id': None,
                    'estimated_capacity_after': None,
                    'reason': 'No truck can accommodate cluster bins - dispatch trigger bin alone'
                }

            # Traffic-aware decision: check if waiting is beneficial/safe
            truck = best_choice['truck']
            # approximate base travel time (minutes) one-way using truck distance and 40 km/h
            base_travel_min = (best_choice['distance_km'] / 40.0) * 60.0
            time_to_overflow_hours = self._time_to_threshold_hours(trigger_bin, trigger_bin.get('dynamic_threshold', trigger_bin.get('threshold', 80)))
            time_to_overflow_min = time_to_overflow_hours * 60.0

            # Ask TrafficManager whether to wait
            current_time_min = int(current_time // 60) if current_time else 0
            dispatch_decision = self.traffic_manager.calculate_dispatch_time(
                time_to_overflow_min, base_travel_min, current_time_min, bin_id=trigger_bin.get('id'), bin_fill_level=trigger_bin.get('fillLevel', 0), use_predictive_logic=True
            )

            if dispatch_decision.get('dispatch') == 'wait' and dispatch_decision.get('delay_min', 0) > 0:
                return {
                    'additional_bins_for_queue': [b['id'] for b in best_choice['chosen_bins'] if b['id'] != trigger_bin['id']],
                    'dispatch_recommendation': 'wait',
                    'assigned_truck_id': None,
                    'estimated_capacity_after': None,
                    'reason': f"Wait recommended by traffic manager: {dispatch_decision.get('reason')}",
                    'wait_min': dispatch_decision.get('delay_min', 0)
                }

            # Otherwise dispatch now: register assignment and return route
            assigned_bins = best_choice['chosen_bins']
            self._register_cluster_assignment(cluster_key, truck['id'], assigned_bins, current_time)

            # Compute simple nearest-neighbor route starting from truck location
            route = self._compute_nearest_neighbor_route(truck, assigned_bins)

            return {
                'additional_bins_for_queue': [b['id'] for b in assigned_bins if b['id'] != trigger_bin['id']],
                'dispatch_recommendation': 'dispatch',
                'assigned_truck_id': truck['id'],
                'estimated_capacity_after': truck.get('capacity', 0) - truck.get('currentLoad', 0) - best_choice['used_capacity'],
                'reason': f'Proactive cluster dispatch simplified: assigned {len(assigned_bins)} bins',
                'route': route
            }
        except Exception as e:
            logger.error(f"Error in simplified proactive cluster dispatch: {e}")
            return {
                'additional_bins_for_queue': [],
                'dispatch_recommendation': 'dispatch',
                'assigned_truck_id': None,
                'estimated_capacity_after': None,
                'reason': f'Error in proactive dispatch: {e}'
            }
    
    def _find_bin_cluster(self, bin_id: str, clusters: Dict) -> Tuple[Optional[str], List[Dict]]:
        """Find which cluster a bin belongs to"""
        for cluster_id, cluster_bins in clusters.items():
            for bin_data in cluster_bins:
                if bin_data['id'] == bin_id:
                    return str(cluster_id), cluster_bins
        return None, []
    
    def _find_proactive_bins_in_cluster(self, cluster_bins: List[Dict], 
                                      current_time: float,
                                      existing_queue: List[str],
                                      trigger_bin_id: Optional[str] = None) -> List[Dict]:
        # Keep legacy method for compatibility but simplified - prefer _should_collect_proactively
        proactive_bins = []
        for bin_data in cluster_bins:
            if trigger_bin_id and bin_data.get('id') == trigger_bin_id:
                continue
            if bin_data.get('id') in existing_queue:
                continue
            if self._recently_collected(bin_data, current_time):
                continue
            if self._should_collect_proactively(bin_data):
                proactive_bins.append(bin_data)
        return proactive_bins
    
    def _should_collect_proactively(self, bin_data: Dict) -> bool:
        """Check if bin should be collected proactively"""
        fill_level = bin_data.get('fillLevel', 0)
        threshold = bin_data.get('dynamic_threshold', bin_data.get('threshold', 80))
        
        # Include bins within threshold percentage of DT
        dt_proximity = threshold - self.proactive_dt_threshold_percent
        if fill_level >= dt_proximity:
            return True
        
        # Include bins that will reach DT within time window
        time_to_dt = self._time_to_threshold_hours(bin_data, threshold)
        if time_to_dt <= self.proactive_time_window_hours:
            return True
            
        return False
    
    def _time_to_threshold_hours(self, bin_data: Dict, threshold: float) -> float:
        """Calculate time until bin reaches threshold"""
        try:
            fill_level = bin_data.get('fillLevel', 0)
            fill_rate = bin_data.get('fillRate', 0)
            capacity = bin_data.get('capacity', 500)
            
            if fill_level >= threshold or fill_rate <= 0:
                return 0.0 if fill_level >= threshold else float('inf')
            
            liters_needed = ((threshold - fill_level) / 100) * capacity
            return liters_needed / fill_rate
            
        except Exception:
            return float('inf')
    
    def _recently_collected(self, bin_data: Dict, current_time: float) -> bool:
        """Check if bin was recently collected"""
        last_collection = bin_data.get('lastCollection') or bin_data.get('last_collection', 0)
        if not last_collection or not current_time:
            return False
        
        minutes_since = (current_time - last_collection) / 60
        return minutes_since < 30  # Recently collected within 30 minutes
    
    def _find_best_truck_for_cluster(self, cluster_bins: List[Dict], 
                                   all_trucks: List[Dict],
                                   additional_bins: List[Dict]) -> Optional[Dict]:
        """Find the best available truck for cluster collection"""
        available_trucks = [
            truck for truck in all_trucks 
            if truck.get('status') == 'idle'
        ]
        
        if not available_trucks:
            return None
        
        # Calculate cluster center
        cluster_center_lat = sum(bin_data['lat'] for bin_data in cluster_bins) / len(cluster_bins)
        cluster_center_lng = sum(bin_data['lng'] for bin_data in cluster_bins) / len(cluster_bins)
        
        # Calculate required capacity
        total_required_load = self._calculate_cluster_load(
            cluster_bins + additional_bins
        )
        
        # Score trucks by distance and capacity
        truck_scores = []
        for truck in available_trucks:
            # Distance score (closer is better)
            distance_km = calculate_distance_km(
                truck['lat'], truck['lng'],
                cluster_center_lat, cluster_center_lng
            )
            distance_score = 1.0 / (1.0 + distance_km)  # Closer trucks get higher score
            
            # Capacity score (sufficient capacity required, efficiency preferred)
            available_capacity = truck['capacity'] - truck.get('currentLoad', 0)
            
            if available_capacity < total_required_load:
                capacity_score = 0.0  # Can't handle the load
            else:
                # Prefer trucks that are not overly large for the task
                utilization = total_required_load / available_capacity
                if utilization >= 0.3:  # Good utilization
                    capacity_score = 1.0
                else:  # Truck too large, but still usable
                    capacity_score = 0.7
            
            # Combined score
            total_score = (distance_score * 0.4) + (capacity_score * 0.6)
            
            truck_scores.append((total_score, truck))
        
        # Return best truck
        truck_scores.sort(key=lambda x: x[0], reverse=True)
        return truck_scores[0][1] if truck_scores and truck_scores[0][0] > 0 else None
    
    def _calculate_cluster_load(self, bins: List[Dict]) -> float:
        """Calculate total waste load for bins"""
        total_load = 0.0
        for bin_data in bins:
            fill_level = bin_data.get('fillLevel', 0)
            capacity = bin_data.get('capacity', 500)
            bin_load = (fill_level / 100) * capacity
            total_load += bin_load
        return total_load
    
    def _register_cluster_assignment(self, cluster_id: str, truck_id: str,
                                   assigned_bins: List[Dict], current_time: float):
        """Register active cluster assignment"""
        unique_bins: List[Dict] = []
        seen_ids: Set[str] = set()
        for bin_data in assigned_bins:
            bin_id = bin_data.get('id')
            if not bin_id or bin_id in seen_ids:
                continue
            unique_bins.append(bin_data)
            seen_ids.add(bin_id)

        self.active_cluster_assignments[cluster_id] = {
            'truck_id': truck_id,
            'assigned_bins': [bin_data['id'] for bin_data in unique_bins],
            'assigned_at': current_time,
            'total_load': self._calculate_cluster_load(unique_bins)
        }
        print(
            f"📌 ProactiveDispatch: registered cluster {cluster_id} assignment → truck {truck_id}, "
            f"bins={[b['id'] for b in unique_bins]}, total_load={self.active_cluster_assignments[cluster_id]['total_load']:.1f}"
        )
    
    def _evaluate_existing_assignment(self, cluster_id: str, new_bin: Dict, cluster_bins: List[Dict],
                                    existing_assignment: Dict, all_bins: List[Dict],
                                    all_trucks: List[Dict], current_time: float) -> Dict:
        """Evaluate if existing truck assignment can handle new bin"""
        try:
            # Find the assigned truck
            truck_id = existing_assignment['truck_id']
            assigned_bin_ids = existing_assignment['assigned_bins']
            existing_load = existing_assignment['total_load']
            
            # Find truck capacity from actual trucks list
            estimated_truck_capacity = None
            for t in all_trucks:
                if t.get('id') == truck_id:
                    estimated_truck_capacity = t.get('capacity', None)
                    break
            if estimated_truck_capacity is None:
                # Fallback conservative estimate
                estimated_truck_capacity = 1500
            available_capacity = estimated_truck_capacity - existing_load

            if new_bin['id'] in assigned_bin_ids:
                return {
                    'additional_bins_for_queue': [],
                    'dispatch_recommendation': 'wait_for_existing_truck',
                    'assigned_truck_id': truck_id,
                    'estimated_capacity_after': available_capacity,
                    'reason': f"Bin {new_bin['id']} already assigned to truck {truck_id}"
                }

            # Calculate new bin load
            new_bin_load = self._calculate_cluster_load([new_bin])
            print(
                f"🔁 ProactiveDispatch: evaluating existing assignment for cluster {cluster_id} → "
                f"truck {truck_id}, assigned_bins={assigned_bin_ids}, existing_load={existing_load:.1f}, "
                f"new_bin={new_bin['id']} ({new_bin_load:.1f}), available_capacity={available_capacity:.1f}"
            )
            
            if new_bin_load <= (available_capacity * (1 - self.capacity_safety_margin)):
                # Existing truck can handle the new bin
                self.active_cluster_assignments[cluster_id]['assigned_bins'].append(new_bin['id'])
                self.active_cluster_assignments[cluster_id]['total_load'] += new_bin_load
                
                decision = {
                    'additional_bins_for_queue': [new_bin['id']],
                    'dispatch_recommendation': 'wait_for_existing_truck',
                    'assigned_truck_id': truck_id,
                    'estimated_capacity_after': available_capacity - new_bin_load,
                    'reason': f'Added to existing truck {truck_id} assignment'
                }
                print(
                    f"✅ ProactiveDispatch: kept truck {truck_id} on cluster {cluster_id}; "
                    f"new total_load={self.active_cluster_assignments[cluster_id]['total_load']:.1f}"
                )
                return decision
            else:
                # Existing truck cannot handle additional load
                print(
                    f"⚠️ ProactiveDispatch: truck {truck_id} capacity insufficient for bin {new_bin['id']} "
                    f"(needed={new_bin_load:.1f}, available={available_capacity:.1f})"
                )
                return {
                    'additional_bins_for_queue': [new_bin['id']],
                    'dispatch_recommendation': 'dispatch',
                    'assigned_truck_id': None,
                    'estimated_capacity_after': None,
                    'reason': 'Existing truck at capacity - need additional truck'
                }
                
        except Exception as e:
            logger.error(f"Error evaluating existing assignment: {e}")
            # Default to new dispatch on error
            return {
                'additional_bins_for_queue': [new_bin['id']],
                'dispatch_recommendation': 'dispatch',
                'assigned_truck_id': None,
                'estimated_capacity_after': None,
                'reason': f'Error evaluating existing assignment: {e}'
            }
    
    def update_truck_assignments(self, truck_updates: Dict):
        """Update truck assignment status (call when trucks start/complete routes)"""
        for truck_id, update_info in truck_updates.items():
            status = update_info.get('status')
            
            if status in ['completed_route', 'available', 'idle']:
                # Remove completed/idle assignments to allow truck reassignment
                clusters_to_remove = []
                for cluster_id, assignment in self.active_cluster_assignments.items():
                    if assignment['truck_id'] == truck_id:
                        clusters_to_remove.append(cluster_id)
                
                for cluster_id in clusters_to_remove:
                    del self.active_cluster_assignments[cluster_id]
                    logger.info(f"🧹 Cleared assignment for truck {truck_id} (cluster {cluster_id}) - status: {status}")
                    
            elif status == 'route_started':
                # Track truck assignment to clusters to prevent duplicates
                assigned_bins = update_info.get('assigned_bins', [])
                simulation_time = update_info.get('simulation_time', 0)
                all_bins = update_info.get('all_bins')

                if assigned_bins:
                    logger.info(f"Tracking assignment: truck {truck_id} → bins {assigned_bins}")
                    # Determine clusters using provided all_bins if available
                    if all_bins and self.clustering_callback:
                        try:
                            clusters = self.clustering_callback(all_bins)
                            # Build reverse map: bin_id -> cluster_id
                            bin_to_cluster = {}
                            for cid, c_bins in clusters.items():
                                for b in c_bins:
                                    bin_to_cluster[b['id']] = str(cid)
                            # Group assigned bins by their cluster_id
                            cluster_groups: Dict[str, List[str]] = {}
                            for bid in assigned_bins:
                                cid = bin_to_cluster.get(bid)
                                if cid:
                                    cluster_groups.setdefault(cid, []).append(bid)
                            # Build map for quick lookup
                            id_to_bin = {b['id']: b for b in all_bins}
                            for cid, bin_ids in cluster_groups.items():
                                # Deduplicate while preserving order
                                seen: Set[str] = set()
                                ordered_unique = []
                                for bid in bin_ids:
                                    if bid not in seen:
                                        ordered_unique.append(bid)
                                        seen.add(bid)
                                # Compute total load for these assigned bins
                                assigned_bin_objs = [id_to_bin[bid] for bid in ordered_unique if bid in id_to_bin]
                                print(
                                    f"🚚 ProactiveDispatch: route_started for truck {truck_id}, cluster {cid}, "
                                    f"bins={ordered_unique}"
                                )
                                total_load = self._calculate_cluster_load(assigned_bin_objs) if assigned_bin_objs else 0.0
                                existing = self.active_cluster_assignments.get(cid)
                                if existing and existing.get('truck_id') != truck_id:
                                    logger.info(
                                        "ProactiveDispatch: ignoring route_started for truck %s on cluster %s "
                                        "because truck %s already owns it", truck_id, cid, existing.get('truck_id')
                                    )
                                    continue
                                if existing and existing.get('truck_id') == truck_id:
                                    merged_ids: List[str] = []
                                    seen_ids: Set[str] = set()
                                    for bid in existing.get('assigned_bins', []) + ordered_unique:
                                        if bid not in seen_ids:
                                            merged_ids.append(bid)
                                            seen_ids.add(bid)
                                    merged_objs = [id_to_bin[bid] for bid in merged_ids if bid in id_to_bin]
                                    merged_load = self._calculate_cluster_load(merged_objs) if merged_objs else total_load
                                    existing.update({
                                        'assigned_bins': merged_ids,
                                        'assigned_at': simulation_time,
                                        'total_load': merged_load
                                    })
                                    continue
                                self.active_cluster_assignments[cid] = {
                                    'truck_id': truck_id,
                                    'assigned_bins': ordered_unique,
                                    'assigned_at': simulation_time,
                                    'total_load': total_load
                                }
                        except Exception as e:
                            logger.warning(f"Failed to map assigned bins to clusters: {e}")
                    else:
                        # Fallback: use a consistent but less accurate key per first bin
                        primary_bin = assigned_bins[0]
                        cluster_key = f"unknown_cluster_of:{primary_bin}"
                        unique_assigned = []
                        seen_ids: Set[str] = set()
                        for bid in assigned_bins:
                            if bid not in seen_ids:
                                unique_assigned.append(bid)
                                seen_ids.add(bid)
                        print(
                            f"🚚 ProactiveDispatch: route_started fallback for truck {truck_id}, key={cluster_key}, "
                            f"bins={unique_assigned}"
                        )
                        existing = self.active_cluster_assignments.get(cluster_key)
                        if existing and existing.get('truck_id') != truck_id:
                            logger.info(
                                "ProactiveDispatch: ignoring fallback route_started for truck %s on key %s "
                                "because truck %s already owns it",
                                truck_id,
                                cluster_key,
                                existing.get('truck_id')
                            )
                            continue
                        if existing and existing.get('truck_id') == truck_id:
                            merged_ids = []
                            seen_ids.clear()
                            for bid in existing.get('assigned_bins', []) + unique_assigned:
                                if bid not in seen_ids:
                                    merged_ids.append(bid)
                                    seen_ids.add(bid)
                            existing.update({
                                'assigned_bins': merged_ids,
                                'assigned_at': simulation_time
                            })
                            continue
                        self.active_cluster_assignments[cluster_key] = {
                            'truck_id': truck_id,
                            'assigned_bins': unique_assigned,
                            'assigned_at': simulation_time,
                            'total_load': 0.0
                        }
    
    def get_active_assignments(self) -> Dict:
        """Get current active cluster assignments for monitoring"""
        return self.active_cluster_assignments.copy()
    
    def clear_stale_assignments(self, current_time: float, max_age_hours: float = 4.0):
        """Clear assignments that are too old (indicates truck may have failed)"""
        max_age_seconds = max_age_hours * 3600
        stale_clusters = []
        
        for cluster_id, assignment in self.active_cluster_assignments.items():
            age = current_time - assignment['assigned_at']
            if age > max_age_seconds:
                stale_clusters.append(cluster_id)
        
        for cluster_id in stale_clusters:
            logger.warning(f"Clearing stale cluster assignment: {cluster_id}")
            del self.active_cluster_assignments[cluster_id]
    
    def recommend_collection_queue_updates(self, current_queue: List[str], 
                                         all_bins: List[Dict],
                                         current_time: float) -> Dict:
        """
        Recommend updates to collection queue based on cluster analysis.
        
        This proactively adds bins that are in the same clusters as queued bins
        and are close to reaching DT.
        """
        try:
            if not current_queue:
                return {'additions': [], 'reason': 'No bins in queue'}
            
            # Get clusters using cached clustering if available
            if self.clustering_callback:
                print("📌 ProactiveDispatch: Using cached clustering from agent (expand)")
                clusters = self.clustering_callback(all_bins)
            else:
                print("📌 ProactiveDispatch: Using direct clustering service (expand)")
                clusters = self.clustering_service.create_adaptive_clusters(all_bins)
            
            # Find clusters that have bins in the queue
            affected_clusters = set()
            queue_set = set(current_queue)
            
            for cluster_id, cluster_bins in clusters.items():
                for bin_data in cluster_bins:
                    if bin_data['id'] in queue_set:
                        affected_clusters.add(cluster_id)
                        break
            
            # Find proactive additions for affected clusters
            additions = []
            for cluster_id in affected_clusters:
                cluster_bins = clusters[cluster_id]
                proactive_bins = self._find_proactive_bins_in_cluster(
                    cluster_bins, current_time, current_queue
                )
                additions.extend([bin_data['id'] for bin_data in proactive_bins])
            
            return {
                'additions': additions,
                'affected_clusters': list(affected_clusters),
                'reason': f'Proactive additions for {len(affected_clusters)} clusters with queued bins'
            }
            
        except Exception as e:
            logger.error(f"Error recommending queue updates: {e}")
            return {'additions': [], 'reason': f'Error: {e}'}
    
    def mark_bins_collected(self, truck_id: str, collected_bin_ids: List[str], 
                           all_bins: List[Dict], current_time: float) -> None:
        """
        Mark bins as collected and clear cluster assignments.
        
        This prevents duplicate dispatches when a truck collects additional bins
        from a cluster that weren't in the original route.
        
        Args:
            truck_id: ID of truck that collected the bins
            collected_bin_ids: List of bin IDs that were collected
            all_bins: Full list of bins for cluster mapping
            current_time: Current simulation time
        """
        try:
            # Get clusters to identify which cluster(s) the collected bins belong to
            if self.clustering_callback:
                clusters = self.clustering_callback(all_bins)
            else:
                clusters = self.clustering_service.create_adaptive_clusters(all_bins)
            
            # Find cluster IDs for collected bins
            collected_clusters = set()
            for bin_id in collected_bin_ids:
                cluster_id, _ = self._find_bin_cluster(bin_id, clusters)
                if cluster_id is not None:
                    cluster_key = str(cluster_id)
                    collected_clusters.add(cluster_key)
            
            # Clear assignments for clusters that have been fully or partially collected
            for cluster_key in collected_clusters:
                if cluster_key in self.active_cluster_assignments:
                    assignment = self.active_cluster_assignments[cluster_key]
                    assigned_truck = assignment.get('truck_id')
                    
                    # Only clear if the truck matches (safety check)
                    if assigned_truck == truck_id:
                        logger.info(f"✅ Clearing cluster {cluster_key} assignment after collection by {truck_id}")
                        del self.active_cluster_assignments[cluster_key]
                    else:
                        logger.warning(f"⚠️ Truck {truck_id} collected from cluster {cluster_key} "
                                     f"but assigned truck was {assigned_truck}")
            
            logger.info(f"Marked {len(collected_bin_ids)} bins as collected by {truck_id}, "
                       f"cleared {len(collected_clusters)} cluster assignments")
            
        except Exception as e:
            logger.error(f"Error marking bins as collected: {e}")

    def _compute_nearest_neighbor_route(self, truck: Dict, bins: List[Dict]) -> List[str]:
        """Simple nearest-neighbor route starting from truck location."""
        if not bins:
            return []

        remaining = bins[:]  # shallow copy
        route = []
        curr_lat = truck.get('lat', 0)
        curr_lng = truck.get('lng', 0)

        while remaining:
            nearest = min(remaining, key=lambda b: calculate_distance_km(curr_lat, curr_lng, b.get('lat', 0), b.get('lng', 0)))
            route.append(nearest.get('id'))
            curr_lat, curr_lng = nearest.get('lat', 0), nearest.get('lng', 0)
            remaining.remove(nearest)

        return route