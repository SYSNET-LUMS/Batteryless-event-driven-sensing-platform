"""
Minimalist VROOM Service
Single responsibility: Convert bins/trucks to VROOM format and return optimized routes
Handles String-to-Integer ID mapping for VROOM compatibility
"""

import requests
from typing import Dict, List, Optional, Tuple
from config.settings import Config


class VROOMService:
    """Minimalist VROOM optimizer with ID mapping"""
    
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
        Send bins and trucks to VROOM, get optimized routes
        
        Args:
            bins: Bins to collect (already filtered by traffic service)
            trucks: Available trucks
            depot: Depot location for start/end
            
        Returns:
            {
                'status': 'success' | 'error',
                'routes': [
                    {
                        'truck_id': 'TRUCK_1',
                        'bin_ids': ['BIN_1', 'BIN_2'],
                        'distance': 5000,  # meters
                        'duration': 600    # seconds
                    },
                    ...
                ]
            }
        """
        if not self.is_available():
            print("⚠️ VROOM unavailable, using fallback")
            return {'status': 'error', 'message': 'VROOM unavailable'}
        
        # Build payload with ID mapping
        payload, vehicle_map, job_map = self._build_vroom_payload(bins, trucks, depot)
        
        try:
            response = requests.post(
                self.vroom_url,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            vroom_result = response.json()
            return self._parse_vroom_response(vroom_result, vehicle_map, job_map)
            
        except Exception as e:
            print(f"⚠️ VROOM error: {e}")
            return {'status': 'error', 'message': str(e)}
    
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
            jobs.append({
                "id": int_id,  # Integer ID for VROOM
                "location": [bin_data['lng'], bin_data['lat']],
                "service": 300  # 5 min collection time in seconds
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