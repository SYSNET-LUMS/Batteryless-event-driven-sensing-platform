# src/repositories/system_repository.py
from typing import List, Optional, Dict, Any
from .base import BaseRepository

class SystemRepository:
    """Central repository managing all system data"""
    
    def __init__(self):
        self._bins: List[Dict] = []
        self._trucks: List[Dict] = []
        self._depots: List[Dict] = []
        self._id_counters = {
            'bin': 0,
            'truck': 0,
            'depot': 0
        }
    
    def get_bins(self) -> List[Dict]:
        return self._bins.copy()
    
    def get_trucks(self) -> List[Dict]:
        return self._trucks.copy()
    
    def get_depots(self) -> List[Dict]:
        return self._depots.copy()
    
    def add_bin(self, bin_data: Dict) -> Dict:
        self._id_counters['bin'] += 1
        bin_data['id'] = f"BIN_{self._id_counters['bin']}"
        self._bins.append(bin_data)
        return bin_data
    
    def add_truck(self, truck_data: Dict) -> Dict:
        self._id_counters['truck'] += 1
        truck_data['id'] = f"TRUCK_{self._id_counters['truck']}"
        
        # Place truck at nearest depot if available
        if self._depots:
            nearest_depot = self._depots[0]
            truck_data['lat'] = nearest_depot['lat']
            truck_data['lng'] = nearest_depot['lng']
        
        self._trucks.append(truck_data)
        return truck_data
    
    def add_depot(self, depot_data: Dict) -> Dict:
        self._id_counters['depot'] += 1
        depot_data['id'] = f"DEPOT_{self._id_counters['depot']}"
        self._depots.append(depot_data)
        return depot_data
    
    def update_bin(self, bin_id: str, data: Dict) -> Optional[Dict]:
        for bin_item in self._bins:
            if bin_item['id'] == bin_id:
                bin_item.update(data)
                return bin_item
        return None
    
    def update_truck(self, truck_id: str, data: Dict) -> Optional[Dict]:
        for truck in self._trucks:
            if truck['id'] == truck_id:
                truck.update(data)
                return truck
        return None
    
    def update_depot(self, depot_id: str, data: Dict) -> Optional[Dict]:
        for depot in self._depots:
            if depot['id'] == depot_id:
                depot.update(data)
                return depot
        return None
    
    def delete_bin(self, bin_id: str) -> Optional[Dict]:
        for i, bin_item in enumerate(self._bins):
            if bin_item['id'] == bin_id:
                return self._bins.pop(i)
        return None
    
    def delete_truck(self, truck_id: str) -> Optional[Dict]:
        for i, truck in enumerate(self._trucks):
            if truck['id'] == truck_id:
                return self._trucks.pop(i)
        return None
    
    def delete_depot(self, depot_id: str) -> Optional[Dict]:
        for i, depot in enumerate(self._depots):
            if depot['id'] == depot_id:
                return self._depots.pop(i)
        return None
    
    def clear_all(self):
        """Clear all data"""
        self._bins.clear()
        self._trucks.clear()
        self._depots.clear()
        self._id_counters = {
            'bin': 0,
            'truck': 0,
            'depot': 0
        }
    
    def get_state(self) -> Dict:
        """Get complete system state"""
        return {
            'bins': self._bins.copy(),
            'trucks': self._trucks.copy(),
            'depots': self._depots.copy()
        }