from typing import Dict, List, Optional, Any
from config.settings import Config
from repositories.system_repository import get_system_repository
from services.simulation.decision_service import DecisionService
from services.simulation.simulation_service import SimulationService
from services.external.osrm_service import OSRMService
from services.external.vroom_service import VROOMService
from services.routing.optimization_service import OptimizationService
from services.distance_cache_service import DistanceCacheService
from services.dispatch_planner_service import DispatchPlannerService
import logging

logger = logging.getLogger(__name__)

class WasteCollectionAgent:
    """Main coordination layer with VROOM-powered optimization and distance-based dispatch"""
    
    def __init__(self, api_key: Optional[str] = None):
        import traceback
        print(f"🏗️ Creating new WasteCollectionAgent instance - agent_id={id(self)}")
        print(f"📍 Agent creation stack trace:")
        for line in traceback.format_stack()[-5:-1]:
            print(f"  {line.strip()}")
        
        self.api_key = api_key
        self.config = Config()
        self.system_repository = get_system_repository()
        self.bins_data = []
        self.simulation_started = False  # Track if simulation has started
        
        # Initialize modular services with VROOM
        self.osrm_service = OSRMService()
        self.vroom_service = VROOMService()
        self.optimization_service = OptimizationService(self.vroom_service)
        self.simulation_service = SimulationService(self.osrm_service)
        self.distance_cache = DistanceCacheService()
        self.dispatch_planner = DispatchPlannerService(
            self.config,
            self.distance_cache,
            self.system_repository,
            self.optimization_service
        )
        
        # Initialize decision service without clustering dependency
        self.decision_service = DecisionService(
            self.optimization_service,
            self.vroom_service
        )

        # Simple in-memory queue of bin IDs prioritized for collection
        # This queue is rebuilt on each routing cycle based on urgency and recency
        self.collection_queue: List[str] = []
            
    def get_ai_decision(self, decision_type: str, data: Dict) -> Any:
        """Main AI decision entry point with VROOM optimization and traffic-aware dispatch"""
        if decision_type == "truck_routing":
            current_time = data.get('simulation_time', 0)
            bins_data = data.get('bins_data', [])
            trucks_data = data.get('trucks_data', [])
            depots_data = data.get('depots_data', [])
            # Error checks for required entities
            if not bins_data:
                raise ValueError("No bins provided. At least one bin is required to run the system.")
            if not trucks_data:
                raise ValueError("No trucks provided. At least one truck is required to run the system.")
            if not depots_data:
                raise ValueError("No depots provided. At least one depot is required to run the system.")
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

            # Provide active assignments for duplicate-dispatch filtering
            routing_result = self.decision_service.get_routing_decision(
                    {**data, "preferred_bin_ids": filtered_bin_ids}, current_time
            )
            
            # Ensure all dispatched bins are properly tracked in collection queue
            self._ensure_dispatched_bins_in_queue(routing_result)
            
            return routing_result
        else:
            return {"error": f"Decision type not supported: {decision_type}"}
    
    def get_optimization_status(self) -> Dict:
        """Get current optimization system status for distance-based dispatch."""
        status = {
            "vroom_available": self.vroom_service.is_service_available(),
            "osrm_available": self.osrm_service.is_service_available(),
            "optimization_stack": [
                "Distance-Based Dispatch Planner",
                "Knapsack Algorithm",
                "VROOM Routing" if self.vroom_service.is_service_available() else "Fallback Assignment"
            ],
            "assignment_method": "VROOM (no manual tracking)",
            "distance_dispatch_enabled": True
        }

        if self.bins_data:
            try:
                depots = self.system_repository.get_depots()
                self.distance_cache.ensure_cache(self.bins_data, depots)
                status["distance_cache"] = {
                    "bins_indexed": len(self.distance_cache.list_bins()),
                    "depots_indexed": len(self.distance_cache.list_depots())
                }
            except Exception as e:
                logger.warning(f"Could not build distance cache status: {e}")

        return status
    
    def calculate_urgency_score(self, bin_data: Dict, nearest_truck_data: Optional[Dict] = None, 
                               context: Optional[Dict] = None) -> Dict:
        """Calculate urgency score using optimization service"""
        neighbor_bins = context.get('neighbor_bins') if context else None
        return self.optimization_service.calculate_urgency_score(bin_data, neighbor_bins)
    
    def plan_distance_dispatch_for_bin(self, bin_id: str, current_time: float) -> Dict:
        """Convenience wrapper over the dispatch planner for external callers."""
        return self.dispatch_planner.plan_dispatch_for_bin(bin_id, current_time)

    def refresh_system_state(self, bins: List[Dict], depots: List[Dict]):
        """Update cached system records and rebuild distance cache after file loads."""
        self.bins_data = list(bins or [])
        self.simulation_started = False
        try:
            self.distance_cache.warm_cache(self.bins_data, depots or [])
        except Exception as exc:
            logger.warning(f"Failed to warm distance cache during system refresh: {exc}")

    def handle_bin_reached_dt(self, trigger_bin: Dict,
                              all_bins: List[Dict],
                              all_trucks: List[Dict],
                              current_time: float) -> Dict:
        """Distance-only DT handler kept for backward compatibility with route signatures."""
        try:
            plan = self.plan_distance_dispatch_for_bin(trigger_bin['id'], current_time)
            return {
                'dispatch_recommendation': 'dispatch' if plan.get('status') == 'success' else plan.get('status'),
                'assigned_truck_id': plan.get('truck_id'),
                'reason': plan.get('reason'),
                'distance_km': plan.get('distance_km'),
                'eta_minutes': plan.get('eta_minutes'),
                'selected_bins': plan.get('selected_bins'),
                'plan': plan,
                'mode': 'distance_dispatch'
            }
        except Exception as e:
            logger.error(f"Error in distance dispatch planning: {e}")
            return {
                'dispatch_recommendation': 'error',
                'assigned_truck_id': None,
                'reason': str(e),
                'mode': 'distance_dispatch'
            }

    def update_truck_assignment_status(self, truck_id: str, status: str):
        """No-op placeholder kept for backward compatibility with legacy endpoints."""
        logger.info(f"Ignoring truck assignment status update for {truck_id} → {status}; clustering removed.")

    def get_proactive_dispatch_status(self) -> Dict:
        """Return a simplified status block noting that distance dispatch is active."""
        return {
            'active_assignments': {},
            'collection_queue_size': len(self.collection_queue),
            'proactive_dispatch_enabled': False,
            'mode': 'distance_dispatch'
        }
    
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
    def _process_route_extensions(self, routing_result: List[Dict], current_time: float):
        """Process route extension results and add nearby bins to collection queue"""
        try:
            for route in routing_result:
                # Check if this route has extension information
                if 'route_extensions' in route or 'nearby_bins' in route:
                    additional_bins = []
                    
                    # Extract additional bins from route extensions
                    if 'route_extensions' in route:
                        for extension in route['route_extensions']:
                            if extension.get('success') and 'additional_bins' in extension:
                                additional_bins.extend(extension['additional_bins'])
                    
                    # Extract nearby bins directly
                    if 'nearby_bins' in route:
                        nearby_bin_ids = [b.get('id') for b in route['nearby_bins'] if b.get('id')]
                        additional_bins.extend(nearby_bin_ids)
                    
                    # Add additional bins to collection queue
                    if additional_bins:
                        existing_queue_set = set(self.collection_queue)
                        new_bins = [bin_id for bin_id in additional_bins if bin_id not in existing_queue_set]
                        if new_bins:
                            self.collection_queue.extend(new_bins)
                            logger.info(f"Added {len(new_bins)} nearby bins from route extensions to collection queue: {new_bins}")
                            
                            # Mark these bins as assigned to prevent duplicate dispatch
                            for bin_id in new_bins:
                                self.mark_bin_assigned(bin_id)
                    
        except Exception as e:
            logger.warning(f"Error processing route extensions: {e}")

    def _ensure_dispatched_bins_in_queue(self, routing_result: List[Dict]):
        """
        Ensure all bins being dispatched are properly tracked in collection queue.
        This maintains consistency between what trucks are sent to collect and what's in the queue.
        """
        try:
            dispatched_bins = set()
            
            # Extract all bins from routing results
            for route in routing_result:
                route_bins = route.get('route', [])
                if route_bins:
                    dispatched_bins.update(route_bins)
                    
                # Also check route extensions
                if 'route_extensions' in route:
                    for extension in route['route_extensions']:
                        if extension.get('success') and 'additional_bins' in extension:
                            dispatched_bins.update(extension['additional_bins'])
                
                # Check nearby bins
                if 'nearby_bins' in route:
                    nearby_bin_ids = [b.get('id') for b in route['nearby_bins'] if b.get('id')]
                    dispatched_bins.update(nearby_bin_ids)
            
            # Add any dispatched bins that aren't in collection queue
            existing_queue_set = set(self.collection_queue)
            missing_bins = dispatched_bins - existing_queue_set
            
            if missing_bins:
                self.collection_queue.extend(list(missing_bins))
                logger.info(f"Added {len(missing_bins)} dispatched bins to collection queue: {list(missing_bins)}")
                
                # Mark these bins as assigned
                for bin_id in missing_bins:
                    self.mark_bin_assigned(bin_id)
            
            # Log for debugging
            if dispatched_bins:
                logger.info(f"🚛 Dispatching trucks to {len(dispatched_bins)} bins: {list(dispatched_bins)}")
                logger.info(f"📦 Collection queue now has {len(self.collection_queue)} bins")
                
        except Exception as e:
            logger.warning(f"Error ensuring dispatched bins in queue: {e}")

    def _rebuild_collection_queue(self, current_time: float) -> None:
        """
        Rebuild the collection queue using distance-based urgency only.

        Rules:
        - Exclude bins collected in the last 30 minutes
        - Exclude bins with < 15% fill (fuel saving)
        - Prioritize by: overflow/critical -> above threshold -> urgency score
        - No clustering or proactive grouping logic
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

            # Filter candidates - only include bins that need collection (above threshold)
            candidates = []
            for b in bins:
                if recently_collected(b):
                    continue
                fill = b.get('fillLevel', 0)
                threshold = b.get('dynamic_threshold', b.get('threshold', 80))
                # Only include bins that are above their threshold or critically full
                if fill >= threshold or fill >= 90:
                    candidates.append(b)

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

            # Distance-based prioritization: rely solely on urgency ordering
            seen = set()
            ordered_queue: List[str] = []
            for bin_id in initial_queue:
                if bin_id in seen:
                    continue
                seen.add(bin_id)
                ordered_queue.append(bin_id)
            self.collection_queue = ordered_queue
                
        except Exception as e:
            logger.error(f"Error rebuilding collection queue: {e}")
            # On any error, clear queue to avoid blocking
            self.collection_queue = []
    
    # Simplified delegation methods (VROOM handles assignments)
    def reset_assignments(self):
        """Reset bin assignments"""
        self.bin_assignments = {}
    
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