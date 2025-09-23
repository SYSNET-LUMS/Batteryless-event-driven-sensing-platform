def get_dispatch_time(bin_fill, current_hour):
    # Hardcoded traffic levels and travel times (in minutes)
    traffic_levels = {
        9: ('light', 20),   # (traffic, travel_time)
        10: ('heavy', 40),
        11: ('light', 20)
    }
    dynamic_threshold = 90
    fill_rate_per_min = 10 / 60  # 10% per hour => 0.1667% per minute

    # Predict when bin will reach dynamic threshold
    minutes_to_dynamic = max(0, int((dynamic_threshold - bin_fill) / fill_rate_per_min))

    # Check next hour traffic and travel time
    next_hour = current_hour + 1 if current_hour < 11 else 9
    traffic_next_hour, travel_time_next_hour = traffic_levels.get(next_hour, ('light', 20))

    # If next hour is heavy traffic, dispatch 40 min before traffic gets heavy
    if traffic_next_hour == 'heavy':
        # Predict when traffic gets heavy (at next_hour:00)
        # Dispatch 40 min before next_hour:00
        dispatch_hour = current_hour
        dispatch_minute = 60 - travel_time_next_hour
        print(f"Traffic will be heavy at {next_hour}:00, travel time will be {travel_time_next_hour} min.")
        print(f"Dispatch at {dispatch_hour}:{dispatch_minute:02d} to arrive before heavy traffic.")
        return f"Dispatch at {dispatch_hour}:{dispatch_minute:02d}"
    # If bin will reach dynamic threshold before heavy traffic, dispatch at that time
    elif minutes_to_dynamic < 60:
        print(f"Bin will reach dynamic threshold ({dynamic_threshold}%) in {minutes_to_dynamic} minutes.")
        print(f"Dispatch at {current_hour}:{minutes_to_dynamic:02d}")
        return f"Dispatch at {current_hour}:{minutes_to_dynamic:02d}"
    else:
        print("No dispatch needed now.")
        return None

def predict_dispatch_for_hours(bin_fill, start_hour, end_hour):
    # Hardcoded traffic levels and travel times (in minutes)
    traffic_levels = {
        9: ('light', 20),   # (traffic, travel_time)
        10: ('heavy', 40),
        11: ('light', 20)
    }
    dynamic_threshold = 90
    fill_rate_per_min = 10 / 60  # 10% per hour => 0.1667% per minute

    current_fill = bin_fill
    dispatches = []
    for hour in range(start_hour, end_hour + 1):
        # Predict when bin will reach dynamic threshold
        minutes_to_dynamic = max(0, int((dynamic_threshold - current_fill) / fill_rate_per_min))
        next_hour = hour + 1 if hour < 11 else 9
        traffic_next_hour, travel_time_next_hour = traffic_levels.get(next_hour, ('light', 20))

        # If next hour is heavy traffic, dispatch 40 min before traffic gets heavy
        if traffic_next_hour == 'heavy':
            dispatch_hour = hour
            dispatch_minute = 60 - travel_time_next_hour
            dispatches.append(f"Dispatch at {dispatch_hour}:{dispatch_minute:02d} to arrive before heavy traffic at {next_hour}:00 (bin fill: {current_fill:.1f}%)")
        elif minutes_to_dynamic < 60:
            dispatches.append(f"Dispatch at {hour}:{minutes_to_dynamic:02d} (bin will reach {dynamic_threshold}% in {minutes_to_dynamic} min, traffic: {traffic_levels[hour][0]})")
        else:
            dispatches.append(f"No dispatch needed at {hour}:00 (bin fill: {current_fill:.1f}%, traffic: {traffic_levels[hour][0]})")
        # Update bin fill for next hour
        current_fill += 10  # assume bin fills by 10% per hour
    for d in dispatches:
        print(d)
    return dispatches

def predict_dispatch_for_exact_time(bin_fill, current_hour, minute):
    # Hardcoded traffic levels and travel times (in minutes)
    traffic_levels = { 
        9: ('light', 20),
        10: ('heavy', 40),
        11: ('light', 20)
    }
    dynamic_threshold = 90
    fill_rate_per_min = 10 / 60  # 10% per hour => 0.1667% per minute

    # Calculate bin fill at the exact minute
    minutes_since_hour = minute
    projected_fill = bin_fill + fill_rate_per_min * minutes_since_hour

    # Get traffic and travel time for the hour
    traffic, travel_time = traffic_levels.get(current_hour, ('light', 20))

    # If projected fill at that time will reach threshold, and traffic is heavy, dispatch early
    if projected_fill >= dynamic_threshold and traffic == 'heavy':
        dispatch_minute = minute - travel_time
        dispatch_minute = max(0, dispatch_minute)
        print(f"Bin will reach {projected_fill:.1f}% at {current_hour}:{minute:02d} with heavy traffic.")
        print(f"Dispatch at {current_hour}:{dispatch_minute:02d} to arrive at {current_hour}:{minute:02d}.")
        return f"Dispatch at {current_hour}:{dispatch_minute:02d}"
    elif projected_fill >= dynamic_threshold:
        print(f"Bin will reach {projected_fill:.1f}% at {current_hour}:{minute:02d} with light traffic.")
        print(f"Dispatch at {current_hour}:{minute:02d}.")
        return f"Dispatch at {current_hour}:{minute:02d}"
    else:
        print(f"No dispatch needed at {current_hour}:{minute:02d} (bin fill: {projected_fill:.1f}%).")
        return None

# Example usage:
get_dispatch_time(bin_fill=89, current_hour=9)  # Should dispatch at 9:06
get_dispatch_time(bin_fill=90, current_hour=10) # Should dispatch at 10:00
get_dispatch_time(bin_fill=70, current_hour=10) # No dispatch needed
predict_dispatch_for_hours(bin_fill=80, start_hour=9, end_hour=11)
predict_dispatch_for_exact_time(bin_fill=80, current_hour=10, minute=45)