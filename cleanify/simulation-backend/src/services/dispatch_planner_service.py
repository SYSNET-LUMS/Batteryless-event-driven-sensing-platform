from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from config.settings import Config
from services.distance_cache_service import DistanceCacheService
from services.routing.optimization_service import OptimizationService
from utils.distance import calculate_haversine_distance


class DispatchPlannerService:
    """Plans depot→bin→depot routes using distance lookups and capacity checks."""

    def __init__(
        self,
        config: Config,
        distance_cache: DistanceCacheService,
        system_repository,
        optimization_service: Optional[OptimizationService] = None,
    ) -> None:
        self.config = config
        self.distance_cache = distance_cache
        self.system_repository = system_repository
        self.optimization_service = optimization_service or OptimizationService()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def plan_dispatch_for_bin(self, trigger_bin_id: str, current_time: float = 0.0) -> Dict:
        bins = self.system_repository.get_bins()
        depots = self.system_repository.get_depots()
        trucks = self.system_repository.get_trucks()

        if not bins or not depots or not trucks:
            return {
                'status': 'error',
                'reason': 'missing_system_entities',
                'detail': 'Bins, depots, and trucks are required'
            }

        trigger_bin = self._find_bin(bins, trigger_bin_id)
        if not trigger_bin:
            return {
                'status': 'error',
                'reason': 'bin_not_found',
                'detail': trigger_bin_id
            }

        self.distance_cache.ensure_cache(bins, depots)
        depot = self.distance_cache.get_nearest_depot_for_bin(trigger_bin_id) or depots[0]

        idle_trucks = [t for t in trucks if t.get('status') == 'idle']
        if not idle_trucks:
            return {
                'status': 'error',
                'reason': 'no_idle_trucks'
            }

        truck = self._select_best_truck(idle_trucks, depot)
        available_capacity = self._available_capacity(truck)
        if available_capacity <= 0:
            return {
                'status': 'error',
                'reason': 'no_capacity',
                'truck_id': truck['id']
            }

        selected_bins = self._select_bins(trigger_bin, bins, available_capacity, current_time)
        if not selected_bins:
            selected_bins = [trigger_bin]

        route_points = self._build_route(depot, selected_bins)
        load_profile = self._build_load_profile(route_points, selected_bins)
        total_distance_m = self._compute_total_distance(route_points)
        eta_minutes = self._estimate_eta_minutes(total_distance_m)

        return {
            'status': 'success',
            'mode': 'distance_dispatch',
            'truck_id': truck['id'],
            'depot_id': depot.get('id'),
            'selected_bins': [b['id'] for b in selected_bins],
            'route': route_points,
            'load_profile': load_profile,
            'distance_km': round(total_distance_m / 1000, 3),
            'eta_minutes': eta_minutes,
            'reason': f"distance_plan_for_{trigger_bin_id}"
        }

    # ------------------------------------------------------------------
    # Selection helpers
    # ------------------------------------------------------------------
    def _select_bins(self, trigger_bin: Dict, bins: List[Dict], available_capacity: float,
                     current_time: float) -> List[Dict]:
        selections = [trigger_bin]
        used_capacity = self._estimate_load_liters(trigger_bin)
        neighbors = self.distance_cache.get_bin_neighbors(
            trigger_bin['id'],
            radius_m=self.config.DISPATCH_NEARBY_RADIUS_M,
        )
        context_bins = [entry['bin'] for entry in neighbors]
        for entry in neighbors:
            candidate = entry['bin']
            if candidate['id'] == trigger_bin['id']:
                continue
            if not self._should_consider_bin(candidate, current_time):
                continue
            load = self._estimate_load_liters(candidate)
            if load <= 0:
                continue
            if used_capacity + load > available_capacity:
                continue
            urgency = self.optimization_service.calculate_urgency_score(
                candidate,
                context_bins
            )
            candidate['_urgency'] = urgency['total']
            candidate['_distance_m'] = entry['distance_m']
            selections.append(candidate)
            used_capacity += load
            if len(selections) >= self.config.DISPATCH_MAX_ROUTE_BINS:
                break

        if len(selections) == 1:
            return selections

        # Sort by urgency desc, then distance asc, keep trigger first
        trigger = selections[0]
        rest = sorted(
            selections[1:],
            key=lambda b: (-b.get('_urgency', 0), b.get('_distance_m', 0))
        )
        for bin_obj in rest:
            bin_obj.pop('_urgency', None)
            bin_obj.pop('_distance_m', None)
        return [trigger] + rest

    def _should_consider_bin(self, bin_data: Dict, current_time: float) -> bool:
        threshold = bin_data.get('dynamic_threshold', bin_data.get('threshold', 80))
        fill = bin_data.get('fillLevel', 0)
        if fill < 5:
            return False
        cooldown = self.config.DISPATCH_COOLDOWN_MIN
        last_collection = bin_data.get('lastCollection') or bin_data.get('last_collection')
        if last_collection and current_time:
            minutes_since = (current_time - last_collection) / 60
            if minutes_since < cooldown:
                return False
        if fill >= threshold:
            return True
        buffer = max(5, threshold * 0.1)
        return fill >= (threshold - buffer)

    def _estimate_load_liters(self, bin_data: Dict) -> float:
        capacity = bin_data.get('capacity', 500)
        fill = bin_data.get('fillLevel', 0)
        return max(0.0, (fill / 100.0) * capacity)

    def _available_capacity(self, truck: Dict) -> float:
        capacity = truck.get('capacity', 1000)
        current = truck.get('currentLoad', 0)
        buffer = capacity * (self.config.DISPATCH_CAPACITY_BUFFER_PERCENT / 100.0)
        return max(0.0, capacity - current - buffer)

    def _select_best_truck(self, trucks: List[Dict], depot: Dict) -> Dict:
        def score(truck: Dict) -> float:
            truck_lat = truck.get('lat', depot.get('lat'))
            truck_lng = truck.get('lng', depot.get('lng'))
            dist = calculate_haversine_distance(truck_lat, truck_lng, depot['lat'], depot['lng'])
            capacity = truck.get('capacity', 1000) - truck.get('currentLoad', 0)
            return dist + (1000 - capacity)  # prefer closer + more capacity
        return min(trucks, key=score)

    # ------------------------------------------------------------------
    # Route helpers
    # ------------------------------------------------------------------
    def _build_route(self, depot: Dict, bins: List[Dict]) -> List[Dict]:
        if not bins:
            return []
        points = [{'type': 'depot', **depot}]
        points.extend({'type': 'bin', **b} for b in bins)
        order = self._nearest_neighbor_order(points)
        optimized = self._two_opt(order, points)
        route = [points[idx] for idx in optimized]
        return route

    def _nearest_neighbor_order(self, points: List[Dict]) -> List[int]:
        n = len(points)
        unvisited = set(range(1, n))
        order = [0]
        current = 0
        while unvisited:
            next_idx = min(
                unvisited,
                key=lambda idx: calculate_haversine_distance(
                    points[current]['lat'], points[current]['lng'],
                    points[idx]['lat'], points[idx]['lng']
                )
            )
            order.append(next_idx)
            unvisited.remove(next_idx)
            current = next_idx
        order.append(0)
        return order

    def _two_opt(self, order: List[int], points: List[Dict]) -> List[int]:
        improved = True
        best = order
        while improved:
            improved = False
            for i in range(1, len(best) - 2):
                for j in range(i + 1, len(best) - 1):
                    if j - i == 1:
                        continue
                    new_route = best[:]
                    new_route[i:j] = reversed(new_route[i:j])
                    if self._route_distance(new_route, points) < self._route_distance(best, points):
                        best = new_route
                        improved = True
            order = best
        return best

    def _route_distance(self, order: List[int], points: List[Dict]) -> float:
        total = 0.0
        for i in range(len(order) - 1):
            a = points[order[i]]
            b = points[order[i + 1]]
            total += calculate_haversine_distance(a['lat'], a['lng'], b['lat'], b['lng'])
        return total

    def _compute_total_distance(self, route: List[Dict]) -> float:
        total = 0.0
        for i in range(len(route) - 1):
            total += calculate_haversine_distance(
                route[i]['lat'], route[i]['lng'],
                route[i + 1]['lat'], route[i + 1]['lng']
            )
        return total

    def _estimate_eta_minutes(self, distance_m: float) -> int:
        speed_kmh = max(5.0, self.config.DISPATCH_SPEED_KMH)
        hours = (distance_m / 1000) / speed_kmh
        return int(round(hours * 60))

    def _build_load_profile(self, route: List[Dict], bins: List[Dict]) -> List[Dict]:
        bin_lookup = {b['id']: b for b in bins}
        cumulative = 0.0
        profile = []
        for stop in route:
            if stop.get('type') != 'bin':
                continue
            bin_data = bin_lookup.get(stop['id'])
            if not bin_data:
                continue
            cumulative += self._estimate_load_liters(bin_data)
            profile.append({
                'bin_id': bin_data['id'],
                'cumulative_load_liters': round(cumulative, 2)
            })
        return profile

    def _find_bin(self, bins: List[Dict], bin_id: str) -> Optional[Dict]:
        for bin_data in bins:
            if bin_data.get('id') == bin_id:
                return bin_data
        return None