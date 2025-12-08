"""
VROOM Service with Global Optimization
Supports sending all bins with priorities and time window constraints
"""
import json
import requests
from typing import Dict, List, Optional, Tuple
from config.settings import Config


class VROOMService:
    """VROOM optimizer with priority weights and time windows"""
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.vroom_url = self.config.VROOM_URL
        self.timeout = self.config.VROOM_TIMEOUT
    
    def optimize_routes(
        self, 
        bins: List[Dict], 
        trucks: List[Dict], 
        depot: Dict
    ) -> Dict:
        """
        Legacy method: Send filtered bins and trucks to VROOM.
        (Kept for backward compatibility)
        """
        if not self.is_available():
            print("⚠️ VROOM unavailable")
            return {'status': 'error', 'message': 'VROOM unavailable'}
        
        payload, vehicle_map, job_map = self._build_vroom_payload(bins, trucks, depot)
        
        try:
            print(f"[VROOM] request payload:\n{json.dumps(payload, indent=2)}")
            response = requests.post(
                self.vroom_url,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            print(f"[VROOM] response status={response.status_code}\n{response.text}")

            vroom_result = response.json()
            return self._parse_vroom_response(vroom_result, vehicle_map, job_map)
            
        except Exception as e:
            print(f"⚠️ VROOM error: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def optimize_routes_with_constraints(
        self,
        bins: List[Dict],
        trucks: List[Dict],
        depot: Dict,
        critical_bins: List[Dict],
        simulation_time: float
    ) -> Dict:
        """
        NEW: Send ALL bins with priorities + time windows for critical bins.
        
        Args:
            bins: ALL non-dispatched bins (not filtered)
            trucks: Available trucks
            depot: Depot location
            critical_bins: Bins that MUST be collected soon (>90% or overflow < 1hr)
            simulation_time: Current simulation time in seconds
        """
        if not self.is_available():
            print("⚠️ VROOM unavailable")
            return {'status': 'error', 'message': 'VROOM unavailable'}
        
        payload, vehicle_map, job_map = self._build_vroom_payload_with_constraints(
            bins, trucks, depot, critical_bins, simulation_time
        )
        
        try:
            print(f"[VROOM] request payload (with constraints):\n{json.dumps(payload, indent=2)}")
            response = requests.post(
                self.vroom_url,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            print(f"[VROOM] response status={response.status_code}\n{response.text}")

            vroom_result = response.json()
            return self._parse_vroom_response(vroom_result, vehicle_map, job_map)
            
        except Exception as e:
            print(f"⚠️ VROOM error: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def _build_vroom_payload_with_constraints(
        self,
        bins: List[Dict],
        trucks: List[Dict],
        depot: Dict,
        critical_bins: List[Dict],
        simulation_time: float
    ) -> Tuple[Dict, Dict, Dict]:
        """
        Build VROOM payload with ALL bins, priority weights, and time windows.
        
        Time windows for critical bins: must visit within 1 hour (60 minutes)
        Priority weights: higher fill/rate = higher priority (visit first)
        """
        jobs = []
        job_map = {}
        
        # Create a set of critical bin IDs for quick lookup
        critical_ids = {b['id'] for b in critical_bins}
        
        for idx, bin_data in enumerate(bins):
            int_id = idx + 1
            job_map[int_id] = bin_data['id']
            
            # Priority: use urgency score if available, else fill level
            priority = int(bin_data.get('urgency_score', bin_data.get('fillLevel', 0)))
            priority = min(100, max(0, priority))
            
            # Build job object
            job = {
                "id": int_id,
                "location": [bin_data['lng'], bin_data['lat']],
                "service": 300,  # 5 min collection time
                "delivery": [int(bin_data.get('fillLevel', 0))],
                "priority": priority
            }
            
            # Add time window for critical bins (must visit within 1 hour = 60 minutes)
            if bin_data['id'] in critical_ids:
                # Time window: now to now+60 minutes
                current_hour = int(simulation_time / 3600) % 24
                current_minute = int((simulation_time % 3600) / 60)
                
                start_time = current_hour * 60 + current_minute
                end_time = start_time + 60  # 60 minute window
                
                job["time_window"] = [start_time, end_time]
                print(f"   🔴 CRITICAL: {bin_data['id']} with time_window [{start_time}, {end_time}]")
            
            jobs.append(job)
        
        # Build vehicles
        vehicles = []
        vehicle_map = {}
        
        for idx, truck in enumerate(trucks):
            int_id = idx + 1
            vehicle_map[int_id] = truck['id']
            vehicles.append({
                "id": int_id,
                "start": [depot['lng'], depot['lat']],
                "end": [depot['lng'], depot['lat']],
                "capacity": [int(truck.get('capacity', 100))],
                "profile": "car"
            })
        
        payload = {
            "jobs": jobs,
            "vehicles": vehicles
        }
        
        print(f"🔧 VROOM payload (global): {len(vehicles)} vehicles, {len(jobs)} jobs, "
              f"{len(critical_ids)} CRITICAL")
        print(f"   Vehicle map: {vehicle_map}")
        
        return payload, vehicle_map, job_map
    
    def _build_vroom_payload(
        self, 
        bins: List[Dict], 
        trucks: List[Dict], 
        depot: Dict
    ) -> Tuple[Dict, Dict, Dict]:
        """
        Convert to VROOM JSON format with Integer ID mapping
        
        Returns:
            (payload, vehicle_map, job_map)
            vehicle_map: {int_id: string_truck_id}
            job_map: {int_id: string_bin_id}
        """
        jobs = []
        job_map = {}  # {int_id: string_bin_id}
        
        for idx, bin_data in enumerate(bins):
            int_id = idx + 1  # Start from 1
            job_map[int_id] = bin_data['id']
            
            # Calculate priority based on fill level (higher fill = higher priority)
            # VROOM priority: higher value = higher priority (visit earlier)
            fill_level = bin_data.get('fillLevel', 0)
            priority = int(fill_level)  # 90% fill = priority 90
            
            jobs.append({
                "id": int_id,  # Integer ID for VROOM
                "location": [bin_data['lng'], bin_data['lat']],
                "service": 300,  # 5 min collection time in seconds
                "delivery": [int(fill_level)],  # VROOM requires integer
                "priority": priority  # Higher fill = visit earlier
            })
        
        vehicles = []
        vehicle_map = {}  # {int_id: string_truck_id}
        
        for idx, truck in enumerate(trucks):
            int_id = idx + 1  # Start from 1
            vehicle_map[int_id] = truck['id']
            vehicles.append({
                "id": int_id,  # Integer ID for VROOM
                "start": [depot['lng'], depot['lat']],
                "end": [depot['lng'], depot['lat']],
                "capacity": [int(truck.get('capacity', 100))],  # VROOM requires integer
                "profile": "car"
            })
        
        payload = {
            "jobs": jobs,
            "vehicles": vehicles
        }
        
        print(f"🔧 VROOM payload: {len(vehicles)} vehicles, {len(jobs)} jobs")
        print(f"   Vehicle map: {vehicle_map}")
        print(f"   Job map: {job_map}")
        
        return payload, vehicle_map, job_map
    
    def _parse_vroom_response(
        self, 
        vroom_result: Dict, 
        vehicle_map: Dict, 
        job_map: Dict
    ) -> Dict:
        """
        Extract routes from VROOM response and map IDs back to strings
        
        Args:
            vroom_result: VROOM API response
            vehicle_map: {int_id: string_truck_id}
            job_map: {int_id: string_bin_id}
        """
        routes = []
        
        for route_data in vroom_result.get('routes', []):
            int_vehicle_id = route_data['vehicle']
            
            # Map vehicle ID back to string
            truck_id = vehicle_map.get(int_vehicle_id)
            if not truck_id:
                print(f"⚠️ Unknown vehicle ID: {int_vehicle_id}")
                continue
            
            # Map bin IDs back to strings
            bin_ids = []
            for step in route_data.get('steps', []):
                if step['type'] == 'job':
                    int_job_id = step['id']
                    bin_id = job_map.get(int_job_id)
                    if bin_id:
                        bin_ids.append(bin_id)
                    else:
                        print(f"⚠️ Unknown job ID: {int_job_id}")
            
            if bin_ids:  # Only include routes with bins
                routes.append({
                    'truck_id': truck_id,
                    'bin_ids': bin_ids,
                    'distance': route_data.get('distance', 0),
                    'duration': route_data.get('duration', 0)
                })
                print(f"✅ Route: {truck_id} → {bin_ids}")
        
        return {
            'status': 'success',
            'routes': routes
        }
    
    def is_available(self) -> bool:
        """Check if VROOM is running"""
        try:
            response = requests.get(f"{self.vroom_url}/health", timeout=2)
            return response.status_code == 200
        except:
            return False