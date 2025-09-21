from flask import Blueprint, jsonify, request, current_app
from typing import Dict, List
import uuid
from models.schedule import Schedule

bp = Blueprint('schedule', __name__, url_prefix='/api')

@bp.route('/schedules', methods=['GET'])
def get_schedules():
    """Get all schedules"""
    try:
        repo = current_app.system_repository
        schedules = repo.get_schedules()
        return jsonify({
            "status": "success",
            "schedules": schedules
        })
        
    except Exception as e:
        print(f"⚠️ Error getting schedules: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/schedules', methods=['POST'])
def create_schedule():
    """Create a new schedule"""
    try:
        data = request.json
        repo = current_app.system_repository
        
        # Validate required fields
        required_fields = ['truck_id', 'depot_id', 'target_bin_ids', 'scheduled_hour', 'scheduled_minute']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    "status": "error",
                    "message": f"Missing required field: {field}"
                }), 400
        
        # Validate truck exists
        trucks = repo.get_trucks()
        if not any(truck['id'] == data['truck_id'] for truck in trucks):
            return jsonify({
                "status": "error",
                "message": f"Truck {data['truck_id']} not found"
            }), 404
        
        # Validate depot exists
        depots = repo.get_depots()
        if not any(depot['id'] == data['depot_id'] for depot in depots):
            return jsonify({
                "status": "error",
                "message": f"Depot {data['depot_id']} not found"
            }), 404
        
        # Validate bins exist
        bins = repo.get_bins()
        bin_ids = [bin_data['id'] for bin_data in bins]
        for bin_id in data['target_bin_ids']:
            if bin_id not in bin_ids:
                return jsonify({
                    "status": "error",
                    "message": f"Bin {bin_id} not found"
                }), 404
        
        # Calculate scheduled_time in simulation seconds
        scheduled_hour = data['scheduled_hour']
        scheduled_minute = data['scheduled_minute']
        start_hour = 7  # Simulation starts at 7 AM
        
        if scheduled_hour < start_hour:
            return jsonify({
                "status": "error",
                "message": f"Scheduled hour must be >= {start_hour} (simulation start time)"
            }), 400
        
        scheduled_time = ((scheduled_hour - start_hour) * 3600) + (scheduled_minute * 60)
        
        # Create schedule
        schedule_data = {
            'truck_id': data['truck_id'],
            'depot_id': data['depot_id'],
            'target_bin_ids': data['target_bin_ids'],
            'scheduled_time': scheduled_time,
            'scheduled_hour': scheduled_hour,
            'scheduled_minute': scheduled_minute,
            'reason': data.get('reason', 'Scheduled dispatch'),
            'area_name': data.get('area_name', f"Area with {len(data['target_bin_ids'])} bins"),
            'status': 'pending',
            'recurrence_type': data.get('recurrence_type', 'once'),
            'recurrence_interval': data.get('recurrence_interval', 24),
            'max_occurrences': data.get('max_occurrences'),
            'total_executions': 0,
            'next_execution_time': scheduled_time  # Initial execution time
        }
        
        # Add to repository
        created_schedule = repo.add_schedule(schedule_data)
        
        return jsonify({
            "status": "success",
            "message": "Schedule created successfully",
            "schedule": created_schedule
        })
        
    except Exception as e:
        print(f"⚠️ Error creating schedule: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/schedules/<schedule_id>', methods=['PUT'])
def update_schedule(schedule_id):
    """Update an existing schedule"""
    try:
        data = request.json
        repo = current_app.system_repository
        
        # Get existing schedule
        schedules = repo.get_schedules()
        schedule = next((s for s in schedules if s['id'] == schedule_id), None)
        
        if not schedule:
            return jsonify({
                "status": "error",
                "message": f"Schedule {schedule_id} not found"
            }), 404
        
        # Only allow updates to pending schedules
        if schedule['status'] != 'pending':
            return jsonify({
                "status": "error",
                "message": f"Cannot update schedule with status: {schedule['status']}"
            }), 400
        
        # Update fields
        updatable_fields = ['scheduled_hour', 'scheduled_minute', 'reason', 'area_name', 'target_bin_ids']
        updated = False
        
        for field in updatable_fields:
            if field in data:
                schedule[field] = data[field]
                updated = True
        
        if updated and ('scheduled_hour' in data or 'scheduled_minute' in data):
            # Recalculate scheduled_time
            start_hour = 7
            scheduled_time = ((schedule['scheduled_hour'] - start_hour) * 3600) + (schedule['scheduled_minute'] * 60)
            schedule['scheduled_time'] = scheduled_time
        
        if updated:
            repo.update_schedule(schedule)
        
        return jsonify({
            "status": "success",
            "message": "Schedule updated successfully",
            "schedule": schedule
        })
        
    except Exception as e:
        print(f"⚠️ Error updating schedule: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/schedules/<schedule_id>', methods=['DELETE'])
def delete_schedule(schedule_id):
    """Delete a schedule"""
    try:
        repo = current_app.system_repository
        
        success = repo.delete_schedule(schedule_id)
        
        if success:
            return jsonify({
                "status": "success",
                "message": "Schedule deleted successfully"
            })
        else:
            return jsonify({
                "status": "error",
                "message": f"Schedule {schedule_id} not found"
            }), 404
        
    except Exception as e:
        print(f"⚠️ Error deleting schedule: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/schedules/active', methods=['GET'])
def get_active_schedules():
    """Get schedules that are ready for execution"""
    try:
        simulation_time = request.args.get('simulation_time', 0, type=float)
        repo = current_app.system_repository
        
        schedules = repo.get_schedules()
        active_schedules = []
        
        for schedule_data in schedules:
            if schedule_data['status'] == 'pending':
                # Check if ready for execution
                schedule = Schedule(**schedule_data)
                if schedule.is_ready_for_execution(simulation_time):
                    active_schedules.append(schedule_data)
        
        return jsonify({
            "status": "success",
            "active_schedules": active_schedules,
            "count": len(active_schedules)
        })
        
    except Exception as e:
        print(f"⚠️ Error getting active schedules: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/schedules/<schedule_id>/execute', methods=['POST'])
def execute_schedule(schedule_id):
    """Manually execute a schedule"""
    try:
        data = request.json
        simulation_time = data.get('simulation_time', 0)
        repo = current_app.system_repository
        
        # Get schedule
        schedules = repo.get_schedules()
        schedule_data = next((s for s in schedules if s['id'] == schedule_id), None)
        
        if not schedule_data:
            return jsonify({
                "status": "error",
                "message": f"Schedule {schedule_id} not found"
            }), 404
        
        if schedule_data['status'] != 'pending':
            return jsonify({
                "status": "error",
                "message": f"Schedule is not pending (status: {schedule_data['status']})"
            }), 400
        
        # Mark as executing
        schedule_data['status'] = 'executing'
        schedule_data['executed_at'] = simulation_time
        repo.update_schedule(schedule_data)
        
        return jsonify({
            "status": "success",
            "message": "Schedule execution initiated",
            "schedule": schedule_data
        })
        
    except Exception as e:
        print(f"⚠️ Error executing schedule: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500