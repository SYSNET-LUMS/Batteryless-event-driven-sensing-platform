#!/usr/bin/env python3
"""
Serial Data Logger for ESP32 Bin Monitor
Generates CSV file matching SSE.xlsx format
"""

import serial
import csv
import re
from datetime import datetime
import sys

# ============ CONFIGURATION ============
SERIAL_PORT = 'COM10'  # Change this to your port (COM3, /dev/ttyUSB0, etc.)
BAUD_RATE = 115200
CSV_FILENAME = f'bin_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

# ============ CSV COLUMNS ============
CSV_HEADERS = [
    'Opening_Number',
    'Opening_Time_ms',
    'Closing_Time_ms',
    'Start_Angle_deg',
    'Max_Angle_deg',
    'Packet_Count',
    'Identifiers',
    'Distances_cm',
    'RSSIs_dBm',
    'Max_Voltage_V'
]

class BinDataLogger:
    def __init__(self, port, baud_rate, csv_file):
        self.port = port
        self.baud_rate = baud_rate
        self.csv_file = csv_file
        self.serial_conn = None
        self.csv_writer = None
        self.file_handle = None
        
        # Temporary storage for current cycle
        self.current_cycle = {}
        self.in_summary = False
        
    def connect_serial(self):
        """Connect to serial port"""
        try:
            self.serial_conn = serial.Serial(self.port, self.baud_rate, timeout=1)
            print(f"✓ Connected to {self.port} at {self.baud_rate} baud")
            return True
        except Exception as e:
            print(f"✗ Failed to connect: {e}")
            return False
    
    def init_csv(self):
        """Initialize CSV file with headers"""
        try:
            self.file_handle = open(self.csv_file, 'w', newline='')
            self.csv_writer = csv.DictWriter(self.file_handle, fieldnames=CSV_HEADERS)
            self.csv_writer.writeheader()
            self.file_handle.flush()
            print(f"✓ CSV file created: {self.csv_file}")
            return True
        except Exception as e:
            print(f"✗ Failed to create CSV: {e}")
            return False
    
    def parse_cycle_summary(self, line):
        """Parse cycle summary lines and extract data"""
        
        # Start of summary section
        if "CYCLE SUMMARY" in line:
            self.in_summary = True
            return
        
        # End of summary section
        if "===================================" in line and self.in_summary:
            self.in_summary = False
            return
        
        # Parse individual fields
        if not self.in_summary:
            return
        
        # New cycle starts
        if line.startswith("-----------------------------------"):
            if self.current_cycle:  # Save previous cycle
                self.save_cycle()
            self.current_cycle = {}
            return
        
        # Extract data fields
        if line.startswith("Opening #:"):
            self.current_cycle['Opening_Number'] = int(line.split(":")[1].strip())
        
        elif line.startswith("Open Time:"):
            # Extract time in seconds, convert to ms
            time_str = line.split(":")[1].strip().split()[0]
            self.current_cycle['Opening_Time_ms'] = int(float(time_str) * 1000)
        
        elif line.startswith("Close Time:"):
            time_str = line.split(":")[1].strip().split()[0]
            self.current_cycle['Closing_Time_ms'] = int(float(time_str) * 1000)
        
        elif line.startswith("Max Angle:"):
            angle_str = line.split(":")[1].strip().split()[0]
            self.current_cycle['Max_Angle_deg'] = int(angle_str)
            self.current_cycle['Start_Angle_deg'] = 0  # Always 0 based on your data
        
        elif line.startswith("Max Voltage:"):
            voltage_str = line.split(":")[1].strip().split()[0]
            self.current_cycle['Max_Voltage_V'] = float(voltage_str)
        
        elif line.startswith("LoRa Packets:"):
            count_str = line.split(":")[1].strip()
            self.current_cycle['Packet_Count'] = int(count_str)
        
        elif line.startswith("Avg Distance:"):
            # Extract average distance (single value)
            dist_str = line.split(":")[1].strip().split()[0]
            self.current_cycle['Distances_cm'] = int(float(dist_str))
        
        elif line.startswith("Avg RSSI:"):
            # Extract average RSSI (single value)
            rssi_str = line.split(":")[1].strip().split()[0]
            self.current_cycle['RSSIs_dBm'] = int(float(rssi_str))
            
            # For identifiers, we'll use a placeholder since ESP code shows avg
            # but doesn't print individual identifiers
            # You can modify this based on your needs
            if 'Packet_Count' in self.current_cycle and self.current_cycle['Packet_Count'] > 0:
                # Use a placeholder - you might want to modify ESP code to print this
                self.current_cycle['Identifiers'] = 0.0  # Placeholder
    
    def save_cycle(self):
        """Save current cycle to CSV"""
        # Check if we have minimum required data
        required_fields = ['Opening_Number', 'Opening_Time_ms', 'Closing_Time_ms', 
                          'Max_Angle_deg', 'Max_Voltage_V']
        
        if all(field in self.current_cycle for field in required_fields):
            # Fill in missing fields with defaults
            if 'Start_Angle_deg' not in self.current_cycle:
                self.current_cycle['Start_Angle_deg'] = 0
            if 'Packet_Count' not in self.current_cycle:
                self.current_cycle['Packet_Count'] = 0
            if 'Identifiers' not in self.current_cycle:
                self.current_cycle['Identifiers'] = 0.0
            if 'Distances_cm' not in self.current_cycle:
                self.current_cycle['Distances_cm'] = 0
            if 'RSSIs_dBm' not in self.current_cycle:
                self.current_cycle['RSSIs_dBm'] = 0
            
            # Write to CSV
            self.csv_writer.writerow(self.current_cycle)
            self.file_handle.flush()
            
            print(f"✓ Saved Opening #{self.current_cycle['Opening_Number']}")
    
    def run(self):
        """Main loop - read serial data and log to CSV"""
        if not self.connect_serial():
            return
        
        if not self.init_csv():
            return
        
        print("\n=== Logging Started ===")
        print(f"Press Ctrl+C to stop\n")
        
        try:
            while True:
                if self.serial_conn.in_waiting > 0:
                    try:
                        line = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()
                        
                        if line:
                            # Print to console for monitoring
                            print(line)
                            
                            # Parse cycle summary data
                            self.parse_cycle_summary(line)
                            
                    except UnicodeDecodeError:
                        pass  # Skip invalid characters
                        
        except KeyboardInterrupt:
            print("\n\n=== Logging Stopped ===")
            # Save any remaining cycle
            if self.current_cycle:
                self.save_cycle()
            print(f"Data saved to: {self.csv_file}")
        
        finally:
            if self.serial_conn:
                self.serial_conn.close()
            if self.file_handle:
                self.file_handle.close()

def main():
    """Main entry point"""
    print("=== ESP32 Bin Monitor Data Logger ===\n")
    
    # Allow port override from command line
    port = SERIAL_PORT
    if len(sys.argv) > 1:
        port = sys.argv[1]
    
    logger = BinDataLogger(port, BAUD_RATE, CSV_FILENAME)
    logger.run()

if __name__ == "__main__":
    main()