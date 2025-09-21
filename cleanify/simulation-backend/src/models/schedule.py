from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

@dataclass
class Schedule:
    """Represents a scheduled truck dispatch with recurring capability"""
    id: str = ""  # Will be set by repository
    truck_id: str = ""
    depot_id: str = ""
    target_bin_ids: List[str] = field(default_factory=list)  # Area defined by bin IDs
    scheduled_time: float = 0.0  # Simulation time in seconds (from simulation start)
    scheduled_hour: int = 7  # Hour of day (7-23)
    scheduled_minute: int = 0  # Minute of hour (0-59)
    status: str = 'pending'  # pending, executing, completed, cancelled
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    executed_at: Optional[float] = None
    reason: str = 'Scheduled dispatch'
    area_name: Optional[str] = None  # Optional human-readable area name
    
    # Recurring schedule fields
    recurrence_type: str = 'once'  # 'once', 'daily', 'weekly'
    recurrence_interval: int = 24  # hours between repetitions (24 for daily)
    max_occurrences: Optional[int] = None  # unlimited if None
    total_executions: int = 0  # count of how many times this has executed
    next_execution_time: Optional[float] = None  # calculated next execution time
    
    def __post_init__(self):
        # Validate scheduled time
        if self.scheduled_hour < 7 or self.scheduled_hour > 23:
            raise ValueError("Scheduled hour must be between 7 and 23")
        if self.scheduled_minute < 0 or self.scheduled_minute > 59:
            raise ValueError("Scheduled minute must be between 0 and 59")
        
        # Initialize next_execution_time if not set
        if self.next_execution_time is None:
            self.next_execution_time = self.scheduled_time
    
    def get_time_display(self) -> str:
        """Get human-readable time display"""
        return f"{self.scheduled_hour:02d}:{self.scheduled_minute:02d}"
    
    def get_recurrence_display(self) -> str:
        """Get human-readable recurrence display"""
        if self.recurrence_type == 'once':
            return "One-time"
        elif self.recurrence_type == 'daily':
            return "Daily"
        elif self.recurrence_type == 'weekly':
            return "Weekly"
        else:
            return f"Every {self.recurrence_interval} hours"
    
    def is_ready_for_execution(self, current_simulation_time: float) -> bool:
        """Check if schedule is ready for execution based on current simulation time"""
        if self.status != 'pending':
            return False
        
        # Check if max occurrences reached
        if self.max_occurrences is not None and self.total_executions >= self.max_occurrences:
            return False
        
        # Use next_execution_time for recurring schedules
        execution_time = self.next_execution_time if self.next_execution_time is not None else self.scheduled_time
        
        return current_simulation_time >= execution_time
    
    def calculate_next_execution_time(self, current_time: float) -> float:
        """Calculate the next execution time for recurring schedules"""
        if self.recurrence_type == 'once':
            return self.scheduled_time
        
        interval_seconds = self.recurrence_interval * 3600  # Convert hours to seconds
        next_time = current_time + interval_seconds
        
        # For daily schedules, ensure we maintain the same time of day
        if self.recurrence_type == 'daily':
            # Calculate how many full days have passed since simulation start
            start_hour = 7  # Simulation starts at 7 AM
            current_sim_hours = current_time / 3600
            current_day = int(current_sim_hours / 24)
            
            # Next execution should be at the same time tomorrow
            next_day = current_day + 1
            next_execution_hour = next_day * 24 + (self.scheduled_hour - start_hour)
            next_time = next_execution_hour * 3600 + (self.scheduled_minute * 60)
        
        return next_time
    
    def mark_executing(self, execution_time: float):
        """Mark schedule as executing"""
        self.status = 'executing'
        self.executed_at = execution_time
    
    def complete_execution(self, completion_time: float):
        """Complete execution and handle recurrence"""
        self.total_executions += 1
        
        if self.recurrence_type == 'once' or (self.max_occurrences and self.total_executions >= self.max_occurrences):
            # No more executions needed
            self.status = 'completed'
        else:
            # Calculate next execution for recurring schedule
            self.next_execution_time = self.calculate_next_execution_time(completion_time)
            self.status = 'pending'  # Reset to pending for next execution
            self.executed_at = None  # Clear execution time for next run
    
    def mark_cancelled(self):
        """Mark schedule as cancelled"""
        self.status = 'cancelled'
    
    def should_reserve_truck(self, current_time: float, reservation_window: float = 3600) -> bool:
        """Check if truck should be reserved for upcoming execution (within reservation_window seconds)"""
        if self.status != 'pending':
            return False
        
        execution_time = self.next_execution_time if self.next_execution_time is not None else self.scheduled_time
        time_until_execution = execution_time - current_time
        
        return 0 <= time_until_execution <= reservation_window  # Reserve if execution is within window