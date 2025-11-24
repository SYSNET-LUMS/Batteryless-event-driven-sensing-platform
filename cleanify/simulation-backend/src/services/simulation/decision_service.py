from typing import Dict, List, Optional

from services.routing.optimization_service import OptimizationService
from services.routing.dynamic_route_optimizer import DynamicRouteOptimizer
from services.external.vroom_service import VROOMService


class DecisionService:
    """AI decision service that prioritizes distance-based dispatching."""

    def __init__(
        self,
        optimization_service: Optional[OptimizationService] = None,
        vroom_service: Optional[VROOMService] = None,
    ):
        self.vroom_service = vroom_service or VROOMService()
        self.optimization_service = optimization_service or OptimizationService(self.vroom_service)
        self.dynamic_route_optimizer = DynamicRouteOptimizer(self.vroom_service)

    def get_routing_decision(self, data: Dict, current_time: float = 0.0) -> List[Dict]:
        """Plan routes using queue priorities first, then dynamic optimization."""
        bins_data = data.get("bins_data", [])
        trucks_data = data.get("trucks_data", [])
        depot_data = data.get("depots_data", [{}])[0] if data.get("depots_data") else None
        schedules = data.get("schedules", [])
        preferred_bin_ids = data.get("preferred_bin_ids")

        print(f"[DEBUG] DecisionService.get_routing_decision called at {current_time}")
        print(f"[DEBUG] preferred_bin_ids: {preferred_bin_ids}")

        if not bins_data or not trucks_data:
            return []

        if preferred_bin_ids:
            preferred_set = set(preferred_bin_ids)
            filtered_bins = [b for b in bins_data if b.get("id") in preferred_set]
            print(f"🎯 Queue dispatch request with {len(filtered_bins)} filtered bins")
            if not filtered_bins:
                print("⚠️ Collection queue is empty after filtering")
                return []

            optimization_result = self.optimization_service.optimize_truck_routes_with_vroom(
                trucks_data,
                filtered_bins,
                depot_data,
                current_time,
                preferred_set,
            )
            routes = optimization_result.get("routes", [])
            annotated = self._annotate_routes(routes, "priority_queue", "Collection queue dispatch")
            print(f"[DEBUG] Returning {len(annotated)} priority queue routes")
            return annotated

        try:
            dynamic_result = self.dynamic_route_optimizer.optimize_routes_with_dynamic_availability(
                trucks_data,
                bins_data,
                schedules,
                depot_data or {},
                current_time,
            )

            if dynamic_result and dynamic_result.get("success"):
                optimization_result = dynamic_result.get("optimization_result")
                if not optimization_result:
                    raise ValueError("Optimization result is None")

                routes: List[Dict] = []

                for extension in optimization_result.get("route_extensions", []):
                    if extension.get("success"):
                        routes.append(
                            {
                                "truck_id": extension["truck_id"],
                                "route": extension.get("extended_route", []),
                                "dispatch": "now",
                                "delay_min": 0,
                                "reason": f"Route extended with {len(extension.get('additional_bins', []))} nearby bins",
                                "route_extensions": [extension],
                                "extension_type": extension.get("extension_type", "route_extension"),
                                "collection_source": "dynamic_optimization",
                            }
                        )

                for new_route in optimization_result.get("new_routes", []):
                    if new_route.get("success"):
                        routes.append(
                            {
                                "truck_id": new_route["truck_id"],
                                "route": new_route.get("optimized_route", []),
                                "dispatch": "now",
                                "delay_min": 0,
                                "reason": f"New optimized route with {len(new_route.get('optimized_route', []))} bins",
                                "collection_source": "dynamic_optimization",
                            }
                        )

                for override in optimization_result.get("critical_overrides", []):
                    if override.get("success"):
                        routes.append(
                            {
                                "truck_id": override["truck_id"],
                                "route": override.get("assigned_bins", []),
                                "dispatch": "now",
                                "delay_min": 0,
                                "reason": f"Critical override: {override.get('reason', 'Emergency dispatch')}",
                                "collection_source": "critical_override",
                            }
                        )

                if routes:
                    return routes

        except Exception as exc:
            print(f"⚠️ Dynamic optimization failed: {exc}, falling back to basic routing")

        optimization_result = self.optimization_service.optimize_truck_routes_with_vroom(
            trucks_data,
            bins_data,
            depot_data,
            current_time,
        )
        fallback_routes = optimization_result.get("routes", [])
        return self._annotate_routes(fallback_routes, "fallback_basic", "Fallback routing")

    def check_vroom_availability(self) -> Dict:
        """Expose VROOM health for UI/status endpoints."""
        is_available = self.vroom_service.is_service_available()
        return {
            "vroom_available": is_available,
            "fallback_mode": not is_available,
            "optimization_method": "VROOM" if is_available else "Simple Assignment",
        }

    def _annotate_routes(self, routes: Optional[List[Dict]], source: str, reason_prefix: str) -> List[Dict]:
        annotated: List[Dict] = []
        for route in routes or []:
            enriched = dict(route)
            enriched["collection_source"] = source
            enriched_reason = route.get("reason") or "Optimized route"
            enriched["reason"] = f"{reason_prefix}: {enriched_reason}"
            annotated.append(enriched)
        return annotated

    # Legacy compatibility methods (no-ops kept for backward compatibility)
    def reset_assignments(self):
        print("ℹ️ Assignment reset not needed - VROOM handles optimization")

    def is_bin_assigned(self, bin_id: str) -> bool:
        return False

    def mark_bin_assigned(self, bin_id: str):
        return None

    def reserve_bin(self, bin_id: str, truck_id: str, dispatch_time: float):
        return None

    def release_reservation(self, bin_id: str, truck_id: str):
        return None

    @property
    def reserved_bins(self):
        return set()

    @property
    def waiting_assignments(self):
        return {}

    def process_waiting_trucks(self, current_simulation_time: float) -> List[Dict]:
        return []
