from typing import List, Optional, Dict, Any
import uuid
from dataclasses import asdict

from .base import BaseRepository
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from models.schedule import Schedule

# --- Singleton instance ---
_system_repository_instance = None

def get_system_repository():
    global _system_repository_instance
    if _system_repository_instance is None:
        _system_repository_instance = SystemRepository()
    return _system_repository_instance

class SystemRepository:
    """Central repository managing all system data"""
    
    def __init__(self):
        self._bins: List[Dict] = []
        self._trucks: List[Dict] = []
        self._depots: List[Dict] = []
        self._schedules: List[Dict] = []
        self._id_counters = {
            'bin': 0,
            'truck': 0,
            'depot': 0,
            'schedule': 0
        }
    
    def get_bins(self) -> List[Dict]:
        return self._bins.copy()
    
    def get_trucks(self) -> List[Dict]:
        return self._trucks.copy()
    
    def get_depots(self) -> List[Dict]:
        return self._depots.copy()
    
    def get_schedules(self) -> List[Dict]:
        return self._schedules.copy()
    
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
        self._schedules.clear()
        self._id_counters = {
            'bin': 0,
            'truck': 0,
            'depot': 0,
            'schedule': 0
        }
    
    def get_state(self) -> Dict:
        """Get complete system state"""
        return {
            'bins': self._bins.copy(),
            'trucks': self._trucks.copy(),
            'depots': self._depots.copy(),
            'schedules': self._schedules.copy(),
            'id_counters': self._id_counters.copy()
        }

    def set_state(self, state: Dict):
        """Restore system state from dict (including schedules)"""
        self._bins = state.get('bins', []).copy()
        self._trucks = state.get('trucks', []).copy()
        self._depots = state.get('depots', []).copy()
        loaded_schedules = state.get('schedules', [])
        self._schedules = []
        for sched in loaded_schedules:
            try:
                schedule_obj = Schedule(**sched)
                self._schedules.append(asdict(schedule_obj))
            except Exception as e:
                print(f"⚠️ Error restoring schedule: {e} - {sched}")
        self._id_counters = state.get('id_counters', {
            'bin': 0,
            'truck': 0,
            'depot': 0,
            'schedule': 0
        }).copy()
    
    # Schedule management methods
    def add_schedule(self, schedule_data: Dict) -> Dict:
        """Add a new schedule"""
        self._id_counters['schedule'] += 1
        schedule_data['id'] = f"SCHEDULE_{self._id_counters['schedule']}"
        schedule_data['created_at'] = schedule_data.get('created_at', 0)
        
        # Create Schedule model instance to ensure proper validation and defaults
        schedule = Schedule(**schedule_data)
        schedule_dict = asdict(schedule)
        
        self._schedules.append(schedule_dict)
        return schedule_dict
    
    def update_schedule(self, schedule_data: Dict) -> Optional[Dict]:
        """Update an existing schedule"""
        for i, schedule in enumerate(self._schedules):
            if schedule['id'] == schedule_data['id']:
                self._schedules[i] = schedule_data
                return schedule_data
        return None
    
    def delete_schedule(self, schedule_id: str) -> bool:
        """Delete a schedule by ID"""
        for i, schedule in enumerate(self._schedules):
            if schedule['id'] == schedule_id:
                self._schedules.pop(i)
                return True
        return False
    
    def get_schedule_by_id(self, schedule_id: str) -> Optional[Dict]:
        """Get a schedule by ID"""
        for schedule in self._schedules:
            if schedule['id'] == schedule_id:
                return schedule.copy()
        return None
    
    def get_pending_schedules(self) -> List[Dict]:
        """Get all pending schedules"""
        return [s.copy() for s in self._schedules if s.get('status') == 'pending']
    
    def get_schedules_by_truck(self, truck_id: str) -> List[Dict]:
        """Get all schedules for a specific truck"""
        return [s.copy() for s in self._schedules if s.get('truck_id') == truck_id]