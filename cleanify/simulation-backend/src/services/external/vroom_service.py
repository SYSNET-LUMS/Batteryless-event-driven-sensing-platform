"""
Minimalist VROOM Service
Single responsibility: Convert bins/trucks to VROOM format and return optimized routes
"""

import requests
from typing import Dict, List, Optional
from config.settings import Config


class VROOMService:
    """Minimalist VROOM optimizer"""
    
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
        
        payload = self._build_vroom_payload(bins, trucks, depot)
        
        try:
            response = requests.post(
                self.vroom_url,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            vroom_result = response.json()
            return self._parse_vroom_response(vroom_result)
            
        except Exception as e:
            print(f"⚠️ VROOM error: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def _build_vroom_payload(
        self, 
        bins: List[Dict], 
        trucks: List[Dict], 
        depot: Dict
    ) -> Dict:
        """Convert to VROOM JSON format"""
        jobs = []
        for bin_data in bins:
            jobs.append({
                "id": bin_data['id'],
                "location": [bin_data['lng'], bin_data['lat']],
                "service": 300  # 5 min collection time in seconds
            })
        
        vehicles = []
        for truck in trucks:
            vehicles.append({
                "id": truck['id'],
                "start": [depot['lng'], depot['lat']],
                "end": [depot['lng'], depot['lat']],
                "profile": "car"
            })
        
        return {
            "jobs": jobs,
            "vehicles": vehicles
        }
    
    def _parse_vroom_response(self, vroom_result: Dict) -> Dict:
        """Extract routes from VROOM response"""
        routes = []
        
        for route_data in vroom_result.get('routes', []):
            truck_id = route_data['vehicle']
            bin_ids = [step['id'] for step in route_data.get('steps', []) 
                      if step['type'] == 'job']
            
            if bin_ids:  # Only include routes with bins
                routes.append({
                    'truck_id': truck_id,
                    'bin_ids': bin_ids,
                    'distance': route_data.get('distance', 0),
                    'duration': route_data.get('duration', 0)
                })
        
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