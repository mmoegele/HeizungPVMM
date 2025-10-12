#!/usr/bin/env python3
"""
One-Wire Sensor Diagnostic Script
=================================

This script helps diagnose and fix One-Wire sensor reading issues.
It checks the One-Wire filesystem and helps identify sensor problems.

Usage on Raspberry Pi:
    python3 onewire_diagnostics.py
    python3 onewire_diagnostics.py --fix-paths  # Attempt to fix sensor paths
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

def check_onewire_system():
    """Check if One-Wire system is properly set up"""
    print("🔍 Checking One-Wire System Setup")
    print("=" * 40)
    
    # Check kernel modules
    print("📋 Checking kernel modules...")
    try:
        with open('/proc/modules', 'r') as f:
            modules = f.read()
        
        required_modules = ['w1_gpio', 'w1_therm']
        for module in required_modules:
            if module in modules:
                print(f"   ✅ {module} loaded")
            else:
                print(f"   ❌ {module} not loaded")
                print(f"      Fix: sudo modprobe {module}")
    except Exception as e:
        print(f"   ❌ Error checking modules: {e}")
    
    # Check w1 devices
    print("\n🌡️  Checking W1 devices...")
    w1_devices_path = Path("/sys/bus/w1/devices")
    
    if not w1_devices_path.exists():
        print("   ❌ /sys/bus/w1/devices not found")
        print("   💡 One-Wire not enabled or no devices connected")
        return []
    
    devices = []
    for device_path in w1_devices_path.iterdir():
        if device_path.is_dir() and device_path.name.startswith('28-'):
            devices.append(device_path.name)
            print(f"   ✅ Found device: {device_path.name}")
            
            # Try to read temperature
            temp_file = device_path / "w1_slave"
            if temp_file.exists():
                try:
                    with open(temp_file, 'r') as f:
                        content = f.read()
                    
                    if 'YES' in content:
                        # Extract temperature
                        lines = content.strip().split('\n')
                        temp_line = lines[-1]
                        if 't=' in temp_line:
                            temp_raw = int(temp_line.split('t=')[1])
                            temp_c = temp_raw / 1000.0
                            print(f"      📊 Current reading: {temp_c:.1f}°C")
                        else:
                            print(f"      ⚠️  No temperature data in output")
                    else:
                        print(f"      ❌ CRC check failed - sensor may be faulty")
                except Exception as e:
                    print(f"      ❌ Error reading: {e}")
            else:
                print(f"      ❌ w1_slave file not found")
    
    if not devices:
        print("   ⚠️  No One-Wire temperature sensors found")
    
    return devices

def check_owfs_mount():
    """Check OWFS mount point"""
    print("\n📁 Checking OWFS Mount Point")
    print("=" * 30)
    
    owfs_path = Path("/mnt/1wire")
    
    if not owfs_path.exists():
        print("   ❌ /mnt/1wire does not exist")
        print("   💡 Create it with: sudo mkdir -p /mnt/1wire")
        return False
    
    print("   ✅ /mnt/1wire exists")
    
    # Check if it's mounted
    try:
        with open('/proc/mounts', 'r') as f:
            mounts = f.read()
        
        if '/mnt/1wire' in mounts:
            print("   ✅ /mnt/1wire is mounted")
            
            # List contents
            try:
                items = list(owfs_path.iterdir())
                print(f"   📊 Found {len(items)} items in /mnt/1wire")
                
                for item in items[:10]:  # Show first 10
                    if item.name.startswith('28.'):
                        print(f"      🌡️  {item.name}")
                    else:
                        print(f"      📁 {item.name}")
                        
            except Exception as e:
                print(f"   ❌ Error listing contents: {e}")
        else:
            print("   ⚠️  /mnt/1wire exists but is not mounted")
            print("   💡 Mount with OWFS or use direct w1 access")
    
    except Exception as e:
        print(f"   ❌ Error checking mounts: {e}")
    
    return owfs_path.exists()

def scan_for_sensors():
    """Scan for available temperature sensors"""
    print("\n🔍 Scanning for Temperature Sensors")
    print("=" * 40)
    
    sensors_found = {}
    
    # Method 1: Check w1 devices directly
    w1_path = Path("/sys/bus/w1/devices")
    if w1_path.exists():
        print("📍 Method 1: Direct W1 access")
        for device in w1_path.iterdir():
            if device.is_dir() and device.name.startswith('28-'):
                sensor_id = device.name.replace('-', '.')
                sensors_found[sensor_id] = {
                    'w1_path': str(device / "w1_slave"),
                    'owfs_path': f"/mnt/1wire/{sensor_id}",
                    'method': 'w1_direct'
                }
                print(f"   ✅ {sensor_id}")
    
    # Method 2: Check OWFS mount
    owfs_path = Path("/mnt/1wire")
    if owfs_path.exists():
        print("📍 Method 2: OWFS mount")
        try:
            for item in owfs_path.iterdir():
                if item.name.startswith('28.'):
                    if item.name not in sensors_found:
                        sensors_found[item.name] = {
                            'owfs_path': str(item),
                            'method': 'owfs'
                        }
                    print(f"   ✅ {item.name}")
        except Exception as e:
            print(f"   ❌ Error scanning OWFS: {e}")
    
    return sensors_found

def compare_with_config():
    """Compare found sensors with configuration"""
    print("\n📋 Comparing with Configuration")
    print("=" * 35)
    
    # Load configuration
    try:
        import yaml
        config_path = Path("heating_config.yaml")
        
        if not config_path.exists():
            print("   ❌ heating_config.yaml not found")
            return
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        configured_sensors = config.get('sensors', {}).get('temperature_sensors', {})
        print(f"   📊 {len(configured_sensors)} sensors configured")
        
        # Get actual sensors
        available_sensors = scan_for_sensors()
        
        print("\n   🔍 Configuration Analysis:")
        for sensor_id, sensor_config in configured_sensors.items():
            configured_path = sensor_config.get('path', '')
            print(f"      {sensor_id}:")
            print(f"        Configured: {configured_path}")
            
            # Try to find a match
            found_match = False
            for available_id, available_info in available_sensors.items():
                if available_id in configured_path or configured_path.endswith(available_id):
                    print(f"        ✅ Match found: {available_id}")
                    found_match = True
                    break
            
            if not found_match:
                print(f"        ❌ No match found")
                # Suggest alternatives
                if available_sensors:
                    print(f"        💡 Available alternatives:")
                    for avail_id in list(available_sensors.keys())[:3]:
                        print(f"          - {avail_id}")
    
    except ImportError:
        print("   ❌ PyYAML not available for config analysis")
    except Exception as e:
        print(f"   ❌ Error analyzing config: {e}")

def suggest_fixes(available_sensors: Dict):
    """Suggest configuration fixes"""
    print("\n💡 Suggested Fixes")
    print("=" * 20)
    
    if not available_sensors:
        print("❌ No sensors found. Check:")
        print("   1. One-Wire is enabled: sudo raspi-config → Interface Options → 1-Wire")
        print("   2. Sensors are properly connected")
        print("   3. Kernel modules loaded: sudo modprobe w1-gpio w1-therm")
        return
    
    print("✅ Sensors found! Update your heating_config.yaml:")
    print("\nsensors:")
    print("  temperature_sensors:")
    
    # Generate sample config
    sensor_names = [
        'puffer_k_mitte', 'puffer_k_rueck', 'puffer_k_vorlauf',
        'puffer_m_vorlauf', 'puffer_m_mitte', 'puffer_m_rueck',
        'solar_vorlauf', 'solar_ruecklauf', 'bhkw_vorlauf',
        'mischer_fussboden', 'mischer_heizung'
    ]
    
    for i, (sensor_id, sensor_info) in enumerate(available_sensors.items()):
        if i < len(sensor_names):
            name = sensor_names[i]
        else:
            name = f"sensor_{i+1}"
        
        path = sensor_info.get('owfs_path', f"/mnt/1wire/{sensor_id}")
        
        print(f"    {name}:")
        print(f"      path: \"{path}\"")
        print(f"      description: \"Temperature Sensor {i+1}\"")

def check_raspberry_pi_model():
    """Check what Raspberry Pi model we're running on"""
    print("\n🖥️  Raspberry Pi Model Detection")
    print("=" * 40)
    
    try:
        # Method 1: Check /proc/cpuinfo
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
        
        # Extract model and revision
        model_line = None
        revision_line = None
        
        for line in cpuinfo.split('\n'):
            if line.startswith('Model'):
                model_line = line
            elif line.startswith('Revision'):
                revision_line = line
        
        if model_line:
            print(f"   📋 {model_line}")
        
        if revision_line:
            print(f"   🔧 {revision_line}")
        
        # Method 2: Check device tree model
        try:
            with open('/sys/firmware/devicetree/base/model', 'r') as f:
                dt_model = f.read().strip()
            print(f"   🌳 Device Tree: {dt_model}")
        except Exception:
            pass
        
        # Method 3: Check for specific Pi characteristics
        print(f"\n   💡 I2C Bus Notes:")
        
        # Check which I2C bus should be used
        if 'Pi 1' in str(model_line) or 'Model A' in str(model_line) or 'Model B' in str(model_line):
            if 'Rev 1' in str(revision_line):
                print(f"      - Original Pi Rev 1: Use i2c-0")
            else:
                print(f"      - Pi 1 Rev 2+: Use i2c-1") 
        else:
            print(f"      - Pi 2/3/4/Zero: Use i2c-1")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Error detecting Pi model: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Diagnose One-Wire sensor issues")
    parser.add_argument("--fix-paths", action="store_true", help="Suggest configuration fixes")
    
    args = parser.parse_args()
    
    print("🌡️  One-Wire Temperature Sensor Diagnostics")
    print("=" * 50)
    
    # Check Pi model first
    check_raspberry_pi_model()
    
    # Check basic One-Wire system
    check_onewire_system()
    
    # Check OWFS mount
    check_owfs_mount()
    
    # Scan for sensors
    available_sensors = scan_for_sensors()
    
    # Compare with configuration
    compare_with_config()
    
    # Suggest fixes
    if args.fix_paths or not available_sensors:
        suggest_fixes(available_sensors)
    
    print("\n" + "=" * 50)
    print("📋 Summary:")
    print(f"   Found {len(available_sensors)} temperature sensors")
    
    if available_sensors:
        print("   ✅ Sensors detected - check configuration paths")
        print("   💡 Run with --fix-paths to see suggested config")
    else:
        print("   ❌ No sensors found - check hardware and One-Wire setup")

if __name__ == "__main__":
    main()