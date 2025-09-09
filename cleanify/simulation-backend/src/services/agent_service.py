# src/services/agent_service.py (Updated with VROOM)
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
        
        print("🚀 WasteCollectionAgent initialized with VROOM optimization")
    
    def get_ai_decision(self, decision_type: str, data: Dict) -> Any:
        """Main AI decision entry point with VROOM optimization"""
        if decision_type == "truck_routing":
            # Enhanced with VROOM + Knapsack + Clustering workflow
            routing_result = self.decision_service.get_routing_decision(data)
            
            # Add system info
            vroom_status = self.decision_service.check_vroom_availability()
            print(f"🎯 Routing decision using {vroom_status['optimization_method']}")
            
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
                                 truck_capacity: float, current_load: float) -> List[Dict]:
        """Get optimal bin collection from cluster (still used for individual collections)"""
        return self.decision_service.get_cluster_collection_decision(
            target_bin, cluster_bins, truck_capacity, current_load
        )
    
    def get_or_create_clusters(self, bins_data: List[Dict]) -> Dict:
        """Get cached clusters or create new ones using DBSCAN"""
        if (self.cached_clusters is None or 
            len(bins_data) != self.cached_bin_count):
            
            print(f"🔄 Creating clusters for {len(bins_data)} bins...")
            distance_matrix = self.clustering_service.create_bin_distance_matrix(bins_data)
            self.cached_clusters = self.clustering_service.create_clusters_dbscan(
                bins_data, distance_matrix, eps_meters=300, min_samples=2
            )
            self.cached_bin_count = len(bins_data)
            
            print(f"📍 Created {len(self.cached_clusters)} clusters")
        
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
    
    # Simplified delegation methods (VROOM handles assignments)
    def reset_assignments(self):
        """No longer needed - VROOM handles all assignments optimally"""
        print("ℹ️ Manual assignment reset not needed with VROOM")
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