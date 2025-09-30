from typing import Dict, List, Optional, Any
from services.simulation.decision_service import DecisionService
from services.simulation.simulation_service import SimulationService
from services.clustering_service import ClusteringService
from services.external.osrm_service import OSRMService
from services.external.vroom_service import VROOMService
from services.routing.optimization_service import OptimizationService
from services.proactive_cluster_dispatch_service import ProactiveClusterDispatchService
import logging

logger = logging.getLogger(__name__)

class WasteCollectionAgent:
    """Main coordination layer with VROOM-powered optimization and enhanced clustering"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.bins_data = []
        
        # Initialize modular services with VROOM
        self.osrm_service = OSRMService()
        self.vroom_service = VROOMService()
        self.optimization_service = OptimizationService(self.vroom_service)
        self.decision_service = DecisionService(self.optimization_service, self.vroom_service)
        self.simulation_service = SimulationService(self.osrm_service)
        self.clustering_service = ClusteringService(osrm_service=self.osrm_service)
        
        # Initialize proactive cluster dispatch service
        self.proactive_dispatch = ProactiveClusterDispatchService(self.clustering_service)
        
        # Cache for clusters
        self.cached_clusters = None
        self.cached_bin_count = 0

        # Simple in-memory queue of bin IDs prioritized for collection
        # This queue is rebuilt on each routing cycle based on urgency and recency
        self.collection_queue: List[str] = []
            
    def get_ai_decision(self, decision_type: str, data: Dict) -> Any:
        """Main AI decision entry point with VROOM optimization and traffic-aware dispatch"""
        if decision_type == "truck_routing":
            current_time = data.get('simulation_time', 0)
            bins_data = data.get('bins_data', [])
            trucks_data = data.get('trucks_data', [])
            # Rebuild queue based on current state
            self._rebuild_collection_queue(current_time)

            # Traffic-aware dispatch logic
            from services.traffic.dispatch_service import DispatchService
            dispatch_service = DispatchService(self.osrm_service)
            dispatches = dispatch_service.dispatch_decision_flow(bins_data, trucks_data, current_time)
            # Only dispatch bins recommended for 'now'
            dispatch_bin_ids = set(d['bin_id'] for d in dispatches)
            # Filter collection queue to only bins recommended for dispatch
            filtered_bin_ids = set(self.collection_queue) & dispatch_bin_ids

            routing_result = self.decision_service.get_routing_decision(
                {**data, "preferred_bin_ids": filtered_bin_ids}, current_time
            )
            return routing_result
        else:
            return {"error": f"Decision type not supported: {decision_type}"}
    
    def get_optimization_status(self) -> Dict:
        """Get current optimization system status"""
        return {
            "vroom_available": self.vroom_service.is_service_available(),
            "osrm_available": self.osrm_service.is_service_available(),
            "optimization_stack": [
                "DBSCAN Clustering",
                "Knapsack Algorithm", 
                "VROOM Routing" if self.vroom_service.is_service_available() else "Fallback Assignment"
            ],
            "assignment_method": "VROOM (no manual tracking)"
        }
    
    def calculate_urgency_score(self, bin_data: Dict, nearest_truck_data: Optional[Dict] = None, 
                               context: Optional[Dict] = None) -> Dict:
        """Calculate urgency score using optimization service"""
        cluster_bins = context.get('cluster_bins') if context else None
        return self.optimization_service.calculate_urgency_score(bin_data, cluster_bins)
    
    def collect_bins_from_cluster(self, target_bin: Dict, cluster_bins: List[Dict], 
                                 truck_capacity: float, current_load: float,
                                 simulation_time: Optional[float] = None) -> List[Dict]:
        """Get optimal bin collection from cluster (still used for individual collections)"""
        return self.decision_service.get_cluster_collection_decision(
            target_bin, cluster_bins, truck_capacity, current_load, simulation_time or 0.0
        )
    
    def handle_bin_reached_dt_with_cluster_optimization(self, trigger_bin: Dict, 
                                                       all_bins: List[Dict],
                                                       all_trucks: List[Dict],
                                                       current_time: float) -> Dict:
        """
        Enhanced bin DT handling with proactive cluster management.
        
        This method prevents redundant truck dispatches by:
        1. Checking if trigger bin's cluster already has an assigned truck
        2. Adding nearby cluster bins to collection queue proactively  
        3. Estimating truck capacity to avoid over-dispatching
        
        Returns:
            Dict with dispatch decision and queue updates
        """
        try:
            # Process with proactive cluster dispatch service
            cluster_decision = self.proactive_dispatch.process_bin_reached_dt(
                trigger_bin, all_bins, all_trucks, current_time, self.collection_queue
            )
            
            # Update collection queue with additional bins
            additional_bins = cluster_decision.get('additional_bins_for_queue', [])
            if additional_bins:
                # Add new bins to queue (avoid duplicates)
                existing_queue_set = set(self.collection_queue)
                new_bins = [bin_id for bin_id in additional_bins if bin_id not in existing_queue_set]
                self.collection_queue.extend(new_bins)
                
                logger.info(f"Added {len(new_bins)} proactive bins to collection queue for cluster containing {trigger_bin['id']}")
            
            # Clean up stale assignments
            self.proactive_dispatch.clear_stale_assignments(current_time)
            
            return {
                'dispatch_recommendation': cluster_decision.get('dispatch_recommendation', 'dispatch'),
                'assigned_truck_id': cluster_decision.get('assigned_truck_id'),
                'estimated_capacity_after': cluster_decision.get('estimated_capacity_after'),
                'proactive_bins_added': len(additional_bins),
                'reason': cluster_decision.get('reason', 'Standard dispatch'),
                'updated_queue_size': len(self.collection_queue)
            }
            
        except Exception as e:
            logger.error(f"Error in enhanced DT handling: {e}")
            # Fallback to normal dispatch
            return {
                'dispatch_recommendation': 'dispatch',
                'assigned_truck_id': None,
                'estimated_capacity_after': None,
                'proactive_bins_added': 0,
                'reason': f'Fallback dispatch due to error: {e}',
                'updated_queue_size': len(self.collection_queue)
            }
    
    def update_truck_assignment_status(self, truck_id: str, status: str):
        """Update truck assignment status for proactive dispatch tracking"""
        try:
            self.proactive_dispatch.update_truck_assignments({
                truck_id: {'status': status}
            })
        except Exception as e:
            logger.warning(f"Error updating truck assignment status: {e}")
    
    def get_proactive_dispatch_status(self) -> Dict:
        """Get status of proactive dispatch system"""
        try:
            return {
                'active_assignments': self.proactive_dispatch.get_active_assignments(),
                'collection_queue_size': len(self.collection_queue),
                'proactive_dispatch_enabled': True
            }
        except Exception as e:
            logger.error(f"Error getting proactive dispatch status: {e}")
            return {
                'active_assignments': {},
                'collection_queue_size': len(self.collection_queue),
                'proactive_dispatch_enabled': False,
                'error': str(e)
            }
    
    def get_clusters(self, bins_data: List[Dict]) -> Dict:
        """Get cached clusters or create new ones using enhanced adaptive clustering"""
        if (self.cached_clusters is None or 
            len(bins_data) != self.cached_bin_count):
            
            # Use adaptive clustering for better results
            self.cached_clusters = self.clustering_service.create_adaptive_clusters(bins_data)
            self.cached_bin_count = len(bins_data)
            
            # Log clustering results
            logger.info(f"Created {len(self.cached_clusters)} clusters for {len(bins_data)} bins")
            cluster_info = self.clustering_service.get_cluster_info(self.cached_clusters)
            
            for cluster_id, info in cluster_info.items():
                quality = info.get('quality_metrics', {})
                logger.debug(f"Cluster {cluster_id}: {info['bin_ids']} - {quality.get('quality_rating', 'unknown')} quality")
                    
        return self.cached_clusters
    
    # Legacy method name for compatibility
    def get_or_create_clusters(self, bins_data: List[Dict]) -> Dict:
        """Legacy method - redirects to enhanced get_clusters"""
        return self.get_clusters(bins_data)
    
    def calculate_dynamic_threshold(self, bin_data: Dict, simulation_time_seconds: float, 
                                   depot_data: Optional[Dict] = None) -> float:
        """Calculate dynamic threshold using simulation service"""
        if not depot_data:
            return bin_data.get('threshold', 80)
        
        updated_bins = self.simulation_service.calculate_dynamic_thresholds(
            [bin_data], simulation_time_seconds, depot_data
        )
        return updated_bins[0].get('dynamic_threshold', bin_data.get('threshold', 80))

    # ------------------ Queue Management ------------------
    def _rebuild_collection_queue(self, current_time: float) -> None:
        """
        Enhanced queue rebuild with proactive cluster recommendations.

        Rules:
        - Exclude bins collected in the last 30 minutes
        - Exclude bins with < 15% fill (fuel saving)
        - Prioritize by: overflow/critical -> above threshold -> urgency score
        - Include proactive cluster recommendations
        """
        try:
            bins = list(self.bins_data) if self.bins_data else []
            if not bins:
                self.collection_queue = []
                return

            def recently_collected(b: Dict) -> bool:
                last = b.get('lastCollection') or b.get('last_collection') or 0
                if not current_time or not last:
                    return False
                return ((current_time - last) / 60) < 30

            # Filter candidates
            candidates = [
                b for b in bins
                if not recently_collected(b)
                and b.get('fillLevel', 0) >= 15
            ]

            # Compute priority tuple
            def priority_tuple(b: Dict):
                fill = b.get('fillLevel', 0)
                threshold = b.get('dynamic_threshold', b.get('threshold', 80))
                overflow_flag = 1 if fill >= 100 else 0
                critical_flag = 1 if fill >= 95 else 0
                above_threshold = 1 if fill >= threshold else 0
                urgency = self.optimization_service.calculate_urgency_score(b).get('total', 0)
                # Higher tuple sorts first
                return (overflow_flag, critical_flag, above_threshold, round(urgency, 2), round(fill, 2))

            candidates.sort(key=priority_tuple, reverse=True)
            
            # Build initial queue
            initial_queue = [b['id'] for b in candidates[:50]]
            
            # Get proactive cluster recommendations
            try:
                proactive_recommendations = self.proactive_dispatch.recommend_collection_queue_updates(
                    initial_queue, bins, current_time
                )
                
                # Add proactive recommendations
                proactive_additions = proactive_recommendations.get('additions', [])
                if proactive_additions:
                    # Combine and deduplicate
                    combined_queue = initial_queue + proactive_additions
                    self.collection_queue = list(dict.fromkeys(combined_queue))  # Preserve order, remove duplicates
                    
                    logger.info(f"Added {len(proactive_additions)} proactive bins to queue. "
                              f"Total queue size: {len(self.collection_queue)}")
                else:
                    self.collection_queue = initial_queue
                    
            except Exception as e:
                logger.warning(f"Error getting proactive recommendations, using basic queue: {e}")
                self.collection_queue = initial_queue
                
        except Exception as e:
            logger.error(f"Error rebuilding collection queue: {e}")
            # On any error, clear queue to avoid blocking
            self.collection_queue = []
            # On any error, clear queue to avoid blocking
            self.collection_queue = []
    
    # Simplified delegation methods (VROOM handles assignments)
    def reset_assignments(self):
        """Reset bin assignments"""
        self.bin_assignments = {}
        print("🔄 Reset bin assignments")
    
    def is_bin_assigned(self, bin_id: str) -> bool:
        """VROOM handles assignments - always return False for compatibility"""
        return False
    
    def mark_bin_assigned(self, bin_id: str):
        """VROOM handles assignments - no manual tracking needed"""
        pass
    
    def reserve_bin(self, bin_id: str, truck_id: str, dispatch_time: float):
        """VROOM handles assignments - no manual reservations needed"""
        pass
    
    def release_reservation(self, bin_id: str, truck_id: str):
        """VROOM handles assignments - no manual tracking needed"""
        pass
    
    def process_waiting_trucks(self, current_simulation_time: float) -> List[Dict]:
        """VROOM optimizes all routes - no manual waiting management needed"""
        return []
    
    @property
    def reserved_bins(self):
        """VROOM handles assignments - return empty set for compatibility"""
        return set()
    
    @property
    def waiting_assignments(self):
        """VROOM handles assignments - return empty dict for compatibility"""
        return {}
    
    # Legacy compatibility methods
    def should_dispatch_truck_with_safety(self, bin_data: Dict, truck_data: Dict, 
                                         simulation_time_seconds: float) -> Dict:
        """
        Legacy method - VROOM now handles dispatch decisions
        Return immediate dispatch for compatibility
        """
        print("ℹ️ Individual dispatch decisions replaced by VROOM optimization")
        return {
            'dispatch': 'now',
            'delay_min': 0,
            'reason': 'VROOM handles optimal dispatch timing'
        }
    
    def calculate_distance(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Calculate distance using utils (for compatibility)"""
        from utils.distance import calculate_distance_km
        return calculate_distance_km(lat1, lng1, lat2, lng2)