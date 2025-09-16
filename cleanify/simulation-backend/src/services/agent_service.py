from typing import Dict, List, Optional, Any
from services.simulation.decision_service import DecisionService
from services.simulation.simulation_service import SimulationService
from services.clustering_service import ClusteringService
from services.external.osrm_service import OSRMService
from services.external.vroom_service import VROOMService
from services.routing.optimization_service import OptimizationService

class WasteCollectionAgent:
    """Main coordination layer with VROOM-powered optimization"""
    
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
        
        # Cache for clusters
        self.cached_clusters = None
        self.cached_bin_count = 0

        # Simple in-memory queue of bin IDs prioritized for collection
        # This queue is rebuilt on each routing cycle based on urgency and recency
        self.collection_queue: List[str] = []
            
    def get_ai_decision(self, decision_type: str, data: Dict) -> Any:
        """Main AI decision entry point with VROOM optimization"""
        if decision_type == "truck_routing":
            # Enhanced with VROOM + Knapsack + Clustering workflow
            current_time = data.get('simulation_time', 0)
            # Rebuild queue based on current state
            self._rebuild_collection_queue(current_time)

            routing_result = self.decision_service.get_routing_decision(
                {**data, "preferred_bin_ids": set(self.collection_queue)}, current_time
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
                                 simulation_time: float = None) -> List[Dict]:
        """Get optimal bin collection from cluster (still used for individual collections)"""
        return self.decision_service.get_cluster_collection_decision(
            target_bin, cluster_bins, truck_capacity, current_load, simulation_time
        )
    
    def get_or_create_clusters(self, bins_data: List[Dict]) -> Dict:
        """Get cached clusters or create new ones using DBSCAN"""
        if (self.cached_clusters is None or 
            len(bins_data) != self.cached_bin_count):
            
            distance_matrix = self.clustering_service.create_bin_distance_matrix(bins_data)
            self.cached_clusters = self.clustering_service.create_clusters_dbscan(
                bins_data, distance_matrix, eps_meters=300, min_samples=2
            )
            self.cached_bin_count = len(bins_data)
                    
        return self.cached_clusters
    
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
        """Build a prioritized queue of bin IDs that should be collected next.

        Rules:
        - Exclude bins collected in the last 30 minutes
        - Exclude bins with < 15% fill (fuel saving)
        - Prioritize by: overflow/critical -> above threshold -> urgency score
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
            # Keep a modest queue length to avoid thrashing; adjust as needed
            self.collection_queue = [b['id'] for b in candidates[:50]]
        except Exception:
            # On any error, clear queue to avoid blocking
            self.collection_queue = []
    
    # Simplified delegation methods (VROOM handles assignments)
    def reset_assignments(self):
        """No longer needed - VROOM handles all assignments optimally"""
        pass
    
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