from typing import List, Dict, Optional
from models import Waypoint, RouteInfo
from config.settings import Config
from services.external.osrm_service import OSRMService

class RoutingService:
    """Route calculation and waypoint generation service"""
    
    def __init__(self, config: Config = None, osrm_service: OSRMService = None):
        self.config = config or Config()
        self.osrm_service = osrm_service or OSRMService()
    
    def get_route_with_waypoints(self, from_lat: float, from_lng: float,
                                to_lat: float, to_lng: float) -> RouteInfo:
        """Get route with waypoints using OSRM service"""
        try:
            # Use centralized OSRM service
            route_data = self.osrm_service.get_route_with_geometry(
                from_lat, from_lng, to_lat, to_lng
            )
            
            if route_data['success'] and route_data['geometry']:
                coordinates = route_data['geometry']['coordinates']
                waypoints = self.generate_waypoints_every_50m(coordinates)
            else:
                # Use fallback waypoints
                waypoints = self.generate_simple_waypoints(
                    from_lat, from_lng, to_lat, to_lng, route_data['distance']
                )
            
            return {
                'distance': route_data['distance'],
                'duration': route_data['duration'],
                'waypoints': waypoints
            }
            
        except Exception as e:
            print(f"⚠️ Route calculation error: {e}")
            # Fallback to simple calculation
            from utils.distance import calculate_haversine_distance
            distance = calculate_haversine_distance(from_lat, from_lng, to_lat, to_lng)
            duration = distance / 10
            
            waypoints = self.generate_simple_waypoints(
                from_lat, from_lng, to_lat, to_lng, distance
            )
            
            return {
                'distance': distance,
                'duration': duration,
                'waypoints': waypoints
            }
    
    def generate_waypoints_every_50m(self, coordinates: List[List[float]]) -> List[Dict]:
        """Generate waypoints at 50m intervals along the route"""
        if len(coordinates) < 2:
            return []
        
        waypoints = []
        total_route_distance = 0
        
        # Calculate segments
        segments = []
        for i in range(len(coordinates) - 1):
            start_point = coordinates[i]
            end_point = coordinates[i + 1]
            
            from utils.distance import calculate_haversine_distance
            segment_distance = calculate_haversine_distance(
                start_point[1], start_point[0],
                end_point[1], end_point[0]
            )
            
            segments.append({
                'start': start_point,
                'end': end_point,
                'distance': segment_distance,
                'start_total_distance': total_route_distance
            })
            
            total_route_distance += segment_distance
        
        # Create waypoints at exact 50m intervals
        current_distance = 0
        waypoint_interval = 50
        
        while current_distance <= total_route_distance:
            target_segment = None
            for segment in segments:
                segment_end_distance = segment['start_total_distance'] + segment['distance']
                if current_distance <= segment_end_distance:
                    target_segment = segment
                    break
            
            if target_segment is None:
                break
            
            distance_into_segment = current_distance - target_segment['start_total_distance']
            
            if target_segment['distance'] > 0:
                ratio = distance_into_segment / target_segment['distance']
                ratio = min(max(ratio, 0), 1)
                
                start_lat = target_segment['start'][1]
                start_lng = target_segment['start'][0]
                end_lat = target_segment['end'][1]
                end_lng = target_segment['end'][0]
                
                waypoint_lat = start_lat + ratio * (end_lat - start_lat)
                waypoint_lng = start_lng + ratio * (end_lng - start_lng)
                
                waypoints.append({
                    'lat': waypoint_lat,
                    'lng': waypoint_lng,
                    'distance_from_start': current_distance
                })
            
            current_distance += waypoint_interval
        
        # Add final destination
        if waypoints and total_route_distance > 0:
            final_point = coordinates[-1]
            final_waypoint = {
                'lat': final_point[1],
                'lng': final_point[0],
                'distance_from_start': total_route_distance
            }
            
            if len(waypoints) == 0 or total_route_distance - waypoints[-1]['distance_from_start'] >= 25:
                waypoints.append(final_waypoint)
        
        return waypoints
    
    def generate_simple_waypoints(self, from_lat: float, from_lng: float,
                                 to_lat: float, to_lng: float, distance: float) -> List[Dict]:
        """Generate simple straight-line waypoints as fallback"""
        waypoints = []
        num_waypoints = max(1, int(distance / 50))
        
        for i in range(num_waypoints + 1):
            ratio = i / num_waypoints if num_waypoints > 0 else 0
            lat = from_lat + ratio * (to_lat - from_lat)
            lng = from_lng + ratio * (to_lng - from_lng)
            
            waypoints.append({
                'lat': lat,
                'lng': lng,
                'distance_from_start': i * 50
            })
        
        return waypoints