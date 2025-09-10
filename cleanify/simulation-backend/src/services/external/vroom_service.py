import requests
import json
from typing import Dict, List, Optional, Tuple
from config.settings import Config

class VROOMService:
    """VROOM API service for vehicle routing optimization"""
    
    def __init__(self, config: Config = None):
        self.config = config or Config()
        self.vroom_url = getattr(self.config, 'VROOM_URL', 'http://localhost:3000')
        self.timeout = 10
    
    def optimize_vehicle_routes(self, trucks_data: List[Dict], selected_bins: List[Dict], 
                               depot_data: Optional[Dict] = None) -> Dict:
        """
        Optimize vehicle routes for pre-selected bins using VROOM
        
        Args:
            trucks_data: List of available trucks with locations
            selected_bins: Bins already selected by knapsack (capacity handled)
            depot_data: Depot location for start/end points
            
        Returns:
            VROOM solution with optimized routes
        """
        try:
            # Build VROOM problem
            vroom_problem = self._build_vroom_problem(trucks_data, selected_bins, depot_data)
            
            # Call VROOM API
            response = requests.post(
                f"{self.vroom_url}/",
                json=vroom_problem,
                headers={'Content-Type': 'application/json'},
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                vroom_solution = response.json()
                print(f"vroom called with {len(trucks_data)} trucks and {len(selected_bins)} bins")
                return self._parse_vroom_solution(vroom_solution, trucks_data, selected_bins)
            else:
                print(f"⚠️ VROOM API error: {response.status_code}")
                return self._fallback_assignment(trucks_data, selected_bins)
                
        except Exception as e:
            print(f"⚠️ VROOM service error: {e}")
            return self._fallback_assignment(trucks_data, selected_bins)
    
    def _build_vroom_problem(self, trucks_data: List[Dict], selected_bins: List[Dict], 
                           depot_data: Optional[Dict]) -> Dict:
        """Build VROOM problem JSON structure"""
        
        # Vehicles (trucks)
        vehicles = []
        for i, truck in enumerate(trucks_data):
            if truck.get('status') != 'idle':
                continue
                
            vehicle = {
                "id": i,
                "start": [truck['lng'], truck['lat']],  # VROOM uses [lng, lat] format
                "profile": "car"
            }
            
            # Add depot as end point if available
            if depot_data:
                vehicle["end"] = [depot_data['lng'], depot_data['lat']]
            
            vehicles.append(vehicle)
        
        # Jobs (bins to collect)
        jobs = []
        for i, bin_data in enumerate(selected_bins):
            job = {
                "id": i,
                "location": [bin_data['lng'], bin_data['lat']],
                "priority": self._get_vroom_priority(bin_data)
            }
            jobs.append(job)
        
        # Build complete problem
        vroom_problem = {
            "vehicles": vehicles,
            "jobs": jobs,
        }
        
        return vroom_problem
    
    def _get_vroom_priority(self, bin_data: Dict) -> int:
        """Convert urgency score to VROOM priority (higher = more important)"""
        fill_level = bin_data.get('fillLevel', 0)
        
        if fill_level >= 95:
            return 100  # Emergency
        elif fill_level >= 85:
            return 80   # Urgent
        elif fill_level >= 70:
            return 60   # High
        else:
            return 40   # Medium
    
    def _parse_vroom_solution(self, vroom_solution: Dict, trucks_data: List[Dict], 
                            selected_bins: List[Dict]) -> Dict:
        """Parse VROOM solution into our routing format"""
        try:
            routes = vroom_solution.get('routes', [])
            parsed_routes = []
            
            # Map job IDs back to bin IDs
            job_to_bin = {i: bin_data['id'] for i, bin_data in enumerate(selected_bins)}
            
            for route in routes:
                vehicle_id = route['vehicle']
                truck = trucks_data[vehicle_id] if vehicle_id < len(trucks_data) else None
                
                if not truck or not route.get('steps'):
                    continue
                
                # Extract bin IDs from route steps (excluding start/end depot steps)
                route_bins = []
                for step in route['steps']:
                    if step['type'] == 'job':
                        job_id = step['job']
                        if job_id in job_to_bin:
                            route_bins.append(job_to_bin[job_id])
                
                if route_bins:
                    parsed_route = {
                        "truck_id": truck['id'],
                        "route": route_bins,
                        "dispatch": "now",  # VROOM assumes immediate dispatch
                        "delay_min": 0,
                        "reason": f"VROOM optimized route: {len(route_bins)} bins",
                        "total_distance": route.get('distance', 0),
                        "total_duration": route.get('duration', 0),
                        "geometry": route.get('geometry', None)
                    }
                    parsed_routes.append(parsed_route)
            
            return {
                "status": "success",
                "routes": parsed_routes,
                "optimization_used": "VROOM",
                "total_cost": vroom_solution.get('summary', {}).get('cost', 0)
            }
            
        except Exception as e:
            print(f"⚠️ VROOM solution parsing error: {e}")
            return self._fallback_assignment(trucks_data, selected_bins)
    
    def _fallback_assignment(self, trucks_data: List[Dict], selected_bins: List[Dict]) -> Dict:
        """Fallback to simple assignment if VROOM fails"""
        routes = []
        idle_trucks = [t for t in trucks_data if t.get('status') == 'idle']
        
        for i, truck in enumerate(idle_trucks[:len(selected_bins)]):
            if i < len(selected_bins):
                routes.append({
                    "truck_id": truck['id'],
                    "route": [selected_bins[i]['id']],
                    "dispatch": "now",
                    "delay_min": 0,
                    "reason": "Fallback assignment (VROOM unavailable)",
                    "total_distance": 0,
                    "total_duration": 0
                })
        
        return {
            "status": "fallback",
            "routes": routes,
            "optimization_used": "Simple Assignment"
        }
    
    def is_service_available(self) -> bool:
        """Check if VROOM service is available"""
        try:
            response = requests.get(f"{self.vroom_url}/health", timeout=2)
            return response.status_code == 200
        except:
            try:
                # Alternative health check - send empty problem
                test_problem = {"vehicles": [], "jobs": []}
                response = requests.post(
                    f"{self.vroom_url}/",
                    json=test_problem,
                    timeout=2
                )
                return response.status_code in [200, 400]
            except:
                return False