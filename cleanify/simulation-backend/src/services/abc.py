def should_dispatch_early(bin_fill, current_hour):
    # Hardcoded traffic levels for each hour
    traffic_levels = {
        9: 'light',
        10: 'heavy',
        11: 'light'
    }
    # Hardcoded dynamic threshold
    dynamic_threshold = 90
    # Hardcoded early dispatch threshold
    early_dispatch_threshold = 80

    # Predict when bin will reach early dispatch threshold
    # For demo, assume bin_fill is current fill level and will reach 80 next hour
    next_hour = current_hour + 1 if current_hour < 12 else 9

    # If bin will reach 80 and traffic at that hour is heavy, dispatch early
    if bin_fill < early_dispatch_threshold:
        print("No dispatch needed yet.")
        return False
    elif bin_fill >= early_dispatch_threshold and traffic_levels.get(next_hour, 'light') == 'heavy':
        print(f"Traffic at hour {next_hour} is heavy. Dispatch truck early!")
        # Optionally, lower the dynamic threshold to force early dispatch
        dynamic_threshold = early_dispatch_threshold
        return True
    elif bin_fill >= dynamic_threshold:
        print("Bin reached dynamic threshold. Dispatch truck now.")
        return True
    else:
        print("No dispatch needed.")
        return False

# Example usage:
should_dispatch_early(bin_fill=80, current_hour=9)  # Will dispatch early because traffic at 10 is heavy
should_dispatch_early(bin_fill=85, current_hour=10) # Will dispatch now because threshold is reached
should_dispatch_early(bin_fill=75, current_hour=11) # No dispatch needed