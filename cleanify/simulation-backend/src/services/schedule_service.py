from typing import Dict, List, Optional, Tuple
from models.schedule import Schedule
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class ScheduleService:
    """Service for managing truck dispatch schedules"""
    
    def __init__(self):
        self.executed_schedules = set()  # Track executed schedule IDs to prevent re-execution
    
    def validate_schedule(self, schedule_data: Dict, trucks: List[Dict], 
                         depots: List[Dict], bins: List[Dict]) -> Tuple[bool, str]:
        """
        Validate a schedule against current system state
        Returns (is_valid, error_message)
        """
        try:
            # Check truck exists and is available
            truck = next((t for t in trucks if t['id'] == schedule_data['truck_id']), None)
            if not truck:
                return False, f"Truck {schedule_data['truck_id']} not found"
            
            # Check depot exists
            depot = next((d for d in depots if d['id'] == schedule_data['depot_id']), None)
            if not depot:
                return False, f"Depot {schedule_data['depot_id']} not found"
            
            # Check all target bins exist
            bin_ids = [b['id'] for b in bins]
            for bin_id in schedule_data['target_bin_ids']:
                if bin_id not in bin_ids:
                    return False, f"Bin {bin_id} not found"
            
            # Check time validity
            if schedule_data['scheduled_hour'] < 7 or schedule_data['scheduled_hour'] > 23:
                return False, "Scheduled hour must be between 7 and 23"
            
            if schedule_data['scheduled_minute'] < 0 or schedule_data['scheduled_minute'] > 59:
                return False, "Scheduled minute must be between 0 and 59"
            
            return True, ""
            
        except Exception as e:
            return False, f"Validation error: {str(e)}"
    
    def check_truck_conflicts(self, schedule_data: Dict, existing_schedules: List[Dict]) -> Tuple[bool, str]:
        """
        Check if the truck is already scheduled at the same time
        Returns (has_conflict, conflict_message)
        """
        truck_id = schedule_data['truck_id']
        scheduled_hour = schedule_data['scheduled_hour']
        scheduled_minute = schedule_data['scheduled_minute']
        
        for existing in existing_schedules:
            if (existing['truck_id'] == truck_id and 
                existing['status'] == 'pending' and
                existing['scheduled_hour'] == scheduled_hour and
                existing['scheduled_minute'] == scheduled_minute):
                return True, f"Truck {truck_id} is already scheduled at {scheduled_hour:02d}:{scheduled_minute:02d}"
        
        return False, ""
    
    def find_ready_schedules(self, schedules: List[Dict], current_simulation_time: float) -> List[Dict]:
        """
        Find schedules that are ready for execution
        Returns list of schedules ready to execute
        """
        ready_schedules = []
        
        for schedule_data in schedules:
            if (schedule_data['status'] == 'pending' and 
                schedule_data['id'] not in self.executed_schedules):
                
                try:
                    schedule = Schedule(**schedule_data)
                    if schedule.is_ready_for_execution(current_simulation_time):
                        ready_schedules.append(schedule_data)
                except Exception as e:
                    logger.warning(f"Error checking schedule {schedule_data.get('id', 'unknown')}: {e}")
        
        return ready_schedules
    
    def execute_schedule(self, schedule_data: Dict, trucks: List[Dict], 
                        current_simulation_time: float) -> Tuple[bool, str, Optional[Dict]]:
        """
        Execute a schedule by preparing truck for dispatch
        Returns (success, message, dispatch_data)
        """
        try:
            # Find the truck
            truck = next((t for t in trucks if t['id'] == schedule_data['truck_id']), None)
            if not truck:
                return False, f"Truck {schedule_data['truck_id']} not found", None
            
            # Check if truck is available
            if truck.get('status') != 'idle':
                return False, f"Truck {schedule_data['truck_id']} is not idle (status: {truck.get('status')})", None
            
            # Mark schedule as executed to prevent re-execution
            self.executed_schedules.add(schedule_data['id'])
            
            # Prepare dispatch data
            dispatch_data = {
                'truck_id': schedule_data['truck_id'],
                'route': schedule_data['target_bin_ids'],
                'dispatch': 'now',
                'delay_min': 0,
                'reason': f"Scheduled dispatch: {schedule_data.get('reason', 'Scheduled')}",
                'schedule_id': schedule_data['id'],
                'area_name': schedule_data.get('area_name', 'Scheduled area'),
                'is_recurring': schedule_data.get('recurrence_type', 'once') != 'once'
            }
            
            logger.info(f"Executing schedule {schedule_data['id']}: Truck {schedule_data['truck_id']} → {schedule_data['target_bin_ids']}")
            
            return True, f"Schedule executed successfully", dispatch_data
            
        except Exception as e:
            logger.error(f"Error executing schedule {schedule_data.get('id', 'unknown')}: {e}")
            return False, f"Execution error: {str(e)}", None
    
    def complete_schedule_execution(self, schedule_data: Dict, completion_time: float, 
                                  repository) -> Tuple[bool, str]:
        """
        Complete schedule execution and handle recurrence
        Returns (success, message)
        """
        try:
            schedule = Schedule(**schedule_data)
            schedule.complete_execution(completion_time)
            
            # Update in repository
            updated_data = {
                'id': schedule_data['id'],
                'status': schedule.status,
                'total_executions': schedule.total_executions,
                'next_execution_time': schedule.next_execution_time,
                'executed_at': schedule.executed_at
            }
            
            repository.update_schedule({**schedule_data, **updated_data})
            
            if schedule.status == 'pending':
                # Remove from executed set so it can execute again
                self.executed_schedules.discard(schedule_data['id'])
                message = f"Recurring schedule regenerated, next execution at {schedule.next_execution_time}"
            else:
                message = f"Schedule completed after {schedule.total_executions} executions"
            
            logger.info(f"Completed schedule {schedule_data['id']}: {message}")
            return True, message
            
        except Exception as e:
            logger.error(f"Error completing schedule {schedule_data.get('id', 'unknown')}: {e}")
            return False, f"Completion error: {str(e)}"
    
    def get_reserved_trucks(self, schedules: List[Dict], current_simulation_time: float) -> List[str]:
        """
        Get list of truck IDs that should be reserved for upcoming scheduled dispatches
        Returns list of truck_ids that should not be assigned by AI routing
        """
        reserved_trucks = []
        
        for schedule_data in schedules:
            if schedule_data['status'] == 'pending':
                try:
                    schedule = Schedule(**schedule_data)
                    if schedule.should_reserve_truck(current_simulation_time):
                        reserved_trucks.append(schedule_data['truck_id'])
                        logger.debug(f"Reserving truck {schedule_data['truck_id']} for upcoming schedule")
                except Exception as e:
                    logger.warning(f"Error checking truck reservation for schedule {schedule_data.get('id', 'unknown')}: {e}")
        
        return reserved_trucks
    
    def get_next_scheduled_dispatch(self, schedules: List[Dict], current_simulation_time: float) -> Optional[Dict]:
        """Get the next upcoming scheduled dispatch"""
        pending_schedules = [s for s in schedules if s['status'] == 'pending']
        if not pending_schedules:
            return None
        
        # Sort by next execution time
        next_schedules = []
        for schedule_data in pending_schedules:
            try:
                schedule = Schedule(**schedule_data)
                execution_time = schedule.next_execution_time if schedule.next_execution_time is not None else schedule.scheduled_time
                if execution_time > current_simulation_time:
                    next_schedules.append((execution_time, schedule_data))
            except Exception as e:
                logger.warning(f"Error processing schedule {schedule_data.get('id', 'unknown')}: {e}")
        
        if next_schedules:
            next_schedules.sort(key=lambda x: x[0])  # Sort by execution time
            return next_schedules[0][1]  # Return the schedule data
        
        return None
    
    def get_schedule_status_summary(self, schedules: List[Dict]) -> Dict:
        """Get summary of schedule statuses"""
        summary = {
            'total': len(schedules),
            'pending': 0,
            'executing': 0,
            'completed': 0,
            'cancelled': 0
        }
        
        for schedule in schedules:
            status = schedule.get('status', 'unknown')
            if status in summary:
                summary[status] += 1
        
        return summary
    
    def reset_execution_tracking(self):
        """Reset execution tracking (useful for simulation reset)"""
        self.executed_schedules.clear()
        logger.info("Schedule execution tracking reset")