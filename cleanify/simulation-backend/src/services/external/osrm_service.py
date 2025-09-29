import requests
from typing import Dict, List, Optional, Tuple
from config.settings import Config

class OSRMService:
    """Centralized OSRM routing service for all external routing calls"""
    
    def __init__(self, config: Config = None):
        self.config = config or Config()
        self.osrm_url = self.config.OSRM_URL
        self.timeout = 5
        # Simple in-memory caches
        self._route_cache: Dict[Tuple, Dict] = {}
        self._distance_cache: Dict[Tuple, float] = {}
        self._travel_cache: Dict[Tuple, float] = {}
        # Instrumentation counters
        self.stats = {
            'route_requests_total': 0,
            'route_cache_hits': 0,
            'distance_requests_total': 0,
            'distance_cache_hits': 0,
            'travel_requests_total': 0,
            'travel_cache_hits': 0,
            'last_reset': None
        }
        import time
        self.stats['last_reset'] = time.time()

    def reset_stats(self):
        import time
        for k in list(self.stats.keys()):
            if k != 'last_reset':
                if k.endswith('_total') or k.endswith('_hits'):
                    self.stats[k] = 0
        self.stats['last_reset'] = time.time()
    
    def get_distance_between_points(self, lat1: float, lng1: float, 
                                   lat2: float, lng2: float) -> float:
        """Get road distance between two points in meters"""
        try:
            key = (round(lat1,5), round(lng1,5), round(lat2,5), round(lng2,5))
            if key in self._distance_cache:
                self.stats['distance_cache_hits'] += 1
                return self._distance_cache[key]
            self.stats['distance_requests_total'] += 1
            url = f"{self.osrm_url}/route/v1/driving/{lng1},{lat1};{lng2},{lat2}"
            params = {'overview': 'false'}
            
            response = requests.get(url, params=params, timeout=self.timeout)
            data = response.json()
            
            if data['code'] == 'Ok':
                dist = data['routes'][0]['distance']
                self._distance_cache[key] = dist
                return dist
            else:
                raise Exception(f"OSRM error: {data.get('message', 'Unknown')}")
                
        except Exception as e:
            # Fallback to haversine distance
            from utils.distance import calculate_haversine_distance
            return calculate_haversine_distance(lat1, lng1, lat2, lng2)
    
    def get_route_with_geometry(self, from_lat: float, from_lng: float,
                              to_lat: float, to_lng: float) -> Dict:
        """Get full route with geometry and steps"""
        try:
            key = (round(from_lat,5), round(from_lng,5), round(to_lat,5), round(to_lng,5), 'full')
            if key in self._route_cache:
                self.stats['route_cache_hits'] += 1
                return self._route_cache[key]
            self.stats['route_requests_total'] += 1
            url = f"{self.osrm_url}/route/v1/driving/{from_lng},{from_lat};{to_lng},{to_lat}"
            params = {
                'overview': 'full',
                'geometries': 'geojson',
                'steps': 'true'
            }
            
            response = requests.get(url, params=params, timeout=self.timeout)
            data = response.json()
            
            if data['code'] != 'Ok':
                raise Exception(f"OSRM error: {data.get('message', 'Unknown error')}")
            
            route = data['routes'][0]
            result = {
                'distance': route['distance'],
                'duration': route['duration'],
                'geometry': route['geometry'],
                'success': True
            }
            self._route_cache[key] = result
            return result
            
        except Exception as e:
            # Return fallback data
            from utils.distance import calculate_haversine_distance
            distance = calculate_haversine_distance(from_lat, from_lng, to_lat, to_lng)
            return {
                'distance': distance,
                'duration': distance / 10,  # Rough estimate
                'geometry': None,
                'success': False,
                'error': str(e)
            }
    
    def get_travel_time_with_traffic(self, lat1: float, lng1: float,
                                   lat2: float, lng2: float,
                                   traffic_multiplier: float = 1.0) -> float:
        """Get travel time in minutes with traffic consideration"""
        try:
            key = (round(lat1,5), round(lng1,5), round(lat2,5), round(lng2,5), round(traffic_multiplier,2))
            if key in self._travel_cache:
                self.stats['travel_cache_hits'] += 1
                return self._travel_cache[key]
            self.stats['travel_requests_total'] += 1
            route_data = self.get_route_with_geometry(lat1, lng1, lat2, lng2)
            base_duration_seconds = route_data['duration']
            base_duration_minutes = base_duration_seconds / 60
            value = base_duration_minutes * traffic_multiplier
            self._travel_cache[key] = value
            return value
            
        except Exception:
            # Fallback calculation
            from utils.distance import calculate_distance_km
            distance_km = calculate_distance_km(lat1, lng1, lat2, lng2)
            base_time_minutes = (distance_km / 50) * 60  # 50 km/h average
            return base_time_minutes * traffic_multiplier
    
    def is_service_available(self) -> bool:
        """Check if OSRM service is available"""
        try:
            response = requests.get(f"{self.osrm_url}/health", timeout=2)
            return response.status_code == 200
        except:
            return False