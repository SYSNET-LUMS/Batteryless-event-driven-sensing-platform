import logging
from typing import Dict, List, Set, Optional, Tuple, Callable
from services.clustering_service import ClusteringService
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
        
        # Parameters for proactive cluster management
        self.cluster_radius_km = 0.6  # Match clustering distance threshold
        self.proactive_dt_threshold_percent = 5.0  # Add bins within 5% of DT
        self.proactive_time_window_hours = 1.0  # Add bins reaching DT within 1 hour
        self.capacity_safety_margin = 0.05  # 5% safety margin for capacity estimates
        
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
        try:
            # Get clusters using cached clustering if available
            if self.clustering_callback:
                print("📌 ProactiveDispatch: Using cached clustering from agent")
                clusters = self.clustering_callback(all_bins)
            else:
                print("📌 ProactiveDispatch: Using direct clustering service")
                clusters = self.clustering_service.create_adaptive_clusters(all_bins)
            
            # Find which cluster the trigger bin belongs to
            trigger_cluster_id, trigger_cluster_bins = self._find_bin_cluster(
                trigger_bin['id'], clusters
            )
            
            if not trigger_cluster_bins:
                # Single bin cluster - handle normally
                return {
                    'additional_bins_for_queue': [],
                    'dispatch_recommendation': 'dispatch',
                    'assigned_truck_id': None,
                    'estimated_capacity_after': None,
                    'reason': 'Single bin cluster - normal dispatch'
                }
            
            # Check if cluster already has an active assignment
            existing_assignment = self.active_cluster_assignments.get(trigger_cluster_id)
            if existing_assignment:
                # Evaluate if existing truck can handle additional bin
                return self._evaluate_existing_assignment(
                    trigger_bin, trigger_cluster_bins, existing_assignment, 
                    all_bins, current_time
                )
            
            # Find proactive bins in the cluster
            proactive_bins = self._find_proactive_bins_in_cluster(
                trigger_cluster_bins, current_time, existing_collection_queue
            )
            
            # Find best truck for this cluster
            best_truck = self._find_best_truck_for_cluster(
                trigger_cluster_bins, all_trucks, proactive_bins
            )
            
            if not best_truck:
                return {
                    'additional_bins_for_queue': [bin_data['id'] for bin_data in proactive_bins],
                    'dispatch_recommendation': 'dispatch',
                    'assigned_truck_id': None,
                    'estimated_capacity_after': None,
                    'reason': 'No suitable truck available'
                }
            
            # Calculate total load for cluster collection
            total_load = self._calculate_cluster_load(
                [trigger_bin] + proactive_bins
            )
            
            available_capacity = best_truck['capacity'] - best_truck.get('currentLoad', 0)
            capacity_after = available_capacity - total_load
            
            # Register cluster assignment
            self._register_cluster_assignment(
                trigger_cluster_id, best_truck['id'], 
                [trigger_bin] + proactive_bins, current_time
            )
            
            return {
                'additional_bins_for_queue': [bin_data['id'] for bin_data in proactive_bins],
                'dispatch_recommendation': 'dispatch',
                'assigned_truck_id': best_truck['id'],
                'estimated_capacity_after': capacity_after,
                'reason': f'Proactive cluster dispatch: {len(proactive_bins)} additional bins added'
            }
            
        except Exception as e:
            logger.error(f"Error in proactive cluster dispatch: {e}")
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
                                      existing_queue: List[str]) -> List[Dict]:
        """Find bins in cluster that should be proactively collected"""
        proactive_bins = []
        
        for bin_data in cluster_bins:
            # Skip if already in collection queue
            if bin_data['id'] in existing_queue:
                continue
                
            # Skip if recently collected
            if self._recently_collected(bin_data, current_time):
                continue
                
            # Check if bin is close to DT or will reach DT soon
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
        self.active_cluster_assignments[cluster_id] = {
            'truck_id': truck_id,
            'assigned_bins': [bin_data['id'] for bin_data in assigned_bins],
            'assigned_at': current_time,
            'total_load': self._calculate_cluster_load(assigned_bins)
        }
    
    def _evaluate_existing_assignment(self, new_bin: Dict, cluster_bins: List[Dict],
                                    existing_assignment: Dict, all_bins: List[Dict],
                                    current_time: float) -> Dict:
        """Evaluate if existing truck assignment can handle new bin"""
        try:
            # Find the assigned truck
            truck_id = existing_assignment['truck_id']
            assigned_bin_ids = existing_assignment['assigned_bins']
            existing_load = existing_assignment['total_load']
            
            # Calculate new bin load
            new_bin_load = self._calculate_cluster_load([new_bin])
            
            # Find truck capacity (need to get truck data)
            # For now, assume standard capacity - this should be passed in or looked up
            estimated_truck_capacity = 1500  # Conservative estimate
            available_capacity = estimated_truck_capacity - existing_load
            
            if new_bin_load <= (available_capacity * (1 - self.capacity_safety_margin)):
                # Existing truck can handle the new bin
                self.active_cluster_assignments[truck_id]['assigned_bins'].append(new_bin['id'])
                self.active_cluster_assignments[truck_id]['total_load'] += new_bin_load
                
                return {
                    'additional_bins_for_queue': [new_bin['id']],
                    'dispatch_recommendation': 'wait_for_existing_truck',
                    'assigned_truck_id': truck_id,
                    'estimated_capacity_after': available_capacity - new_bin_load,
                    'reason': f'Added to existing truck {truck_id} assignment'
                }
            else:
                # Existing truck cannot handle additional load
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
            
            if status == 'completed_route':
                # Remove completed assignments
                clusters_to_remove = []
                for cluster_id, assignment in self.active_cluster_assignments.items():
                    if assignment['truck_id'] == truck_id:
                        clusters_to_remove.append(cluster_id)
                
                for cluster_id in clusters_to_remove:
                    del self.active_cluster_assignments[cluster_id]
                    
            elif status == 'route_started':
                # Track truck assignment to clusters to prevent duplicates
                assigned_bins = update_info.get('assigned_bins', [])
                simulation_time = update_info.get('simulation_time', 0)
                
                if assigned_bins:
                    # Find which cluster these bins belong to
                    # Use clustering to determine cluster membership
                    if self.clustering_callback:
                        # Get all bins to determine clusters
                        # Note: This is a simplified approach - in production,
                        # we'd want to get actual bin data from repository
                        logger.info(f"Tracking assignment: truck {truck_id} → bins {assigned_bins}")
                        
                        # For now, create a basic cluster key from first bin
                        # The actual cluster determination would need full bin data
                        primary_bin = assigned_bins[0] if assigned_bins else None
                        if primary_bin:
                            cluster_key = f"cluster_{primary_bin}"
                            self.active_cluster_assignments[cluster_key] = {
                                'truck_id': truck_id,
                                'assigned_bins': assigned_bins,
                                'assignment_time': simulation_time,
                                'status': 'active'
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