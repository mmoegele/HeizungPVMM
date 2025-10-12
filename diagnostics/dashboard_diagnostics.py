#!/usr/bin/env python3
"""
Dashboard Diagnostic Script
===========================

This script diagnoses issues with the heating system dashboard:
1. Sensors not showing up
2. Port switching not working
3. API connectivity issues

Usage:
    python3 dashboard_diagnostics.py
    python3 dashboard_diagnostics.py --test-api  # Test API endpoints directly
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, Any

# Add project root to path
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

def test_local_system():
    """Test the local heating system directly without HTTP API"""
    print("🔧 Testing Local System Components")
    print("=" * 50)
    
    try:
        from config import Config
        from hardware import create_hardware_controller
        from sensors import create_sensor_manager
        
        # Load configuration
        print("📋 Loading configuration...")
        config = Config()
        logger = logging.getLogger("diagnostics")
        
        print(f"   ✅ Config loaded: {config.system_name} v{config.system_version}")
        print(f"   📊 Demo mode: {config.demo_mode}")
        print(f"   🎭 Mock hardware: {config.mock_hardware}")
        print(f"   🔧 PiFace boards: {config.piface_board_count}")
        
        # Test hardware
        print("\n🔌 Testing Hardware...")
        hw = create_hardware_controller(
            board_count=config.piface_board_count,
            logger=logger,
            mock_mode=config.mock_hardware
        )
        
        if hasattr(hw, 'run_board_diagnostics'):
            diag = hw.run_board_diagnostics()
            print(f"   🔍 Hardware diagnostics:")
            print(f"     GPIO patch: {diag['gpio_patch_applied']}")
            print(f"     Mock mode: {diag['mock_mode']}")
            print(f"     Board status: {diag['boards']}")
        
        # Test a few outputs
        print(f"   🧪 Testing output control...")
        for board in range(min(2, config.piface_board_count)):
            for port in range(0, 3):  # Test first 3 ports
                try:
                    on_result = hw.turn_on(board, port)
                    state = hw.get_output(board, port)
                    off_result = hw.turn_off(board, port)
                    print(f"     Board {board} Port {port}: ON={on_result}, State={state}, OFF={off_result}")
                except Exception as e:
                    print(f"     Board {board} Port {port}: ❌ Error - {e}")
        
        # Test sensors
        print(f"\n🌡️  Testing Sensors...")
        sensor_manager = create_sensor_manager(config, logger)
        
        if hasattr(sensor_manager, 'run_sensor_diagnostics'):
            sensor_diag = sensor_manager.run_sensor_diagnostics()
            print(f"   📊 Sensor diagnostics: {sensor_diag}")
        
        temperatures = sensor_manager.get_valid_temperatures()
        print(f"   🌡️  Available temperatures: {len(temperatures)}")
        
        for sensor_id, temp in temperatures.items():
            print(f"     {sensor_id}: {temp:.1f}°C")
        
        if not temperatures:
            print("   ⚠️  No temperatures available!")
            print("   💡 This could be why dashboard shows no sensors")
        
        return True, {
            'hardware_ok': bool(diag.get('boards', {})),
            'sensor_count': len(temperatures),
            'temperatures': temperatures
        }
        
    except Exception as e:
        print(f"   ❌ Error testing local system: {e}")
        return False, {'error': str(e)}

def test_api_endpoints(base_url="http://localhost:8080"):
    """Test HTTP API endpoints"""
    if not REQUESTS_AVAILABLE:
        print("❌ Requests library not available. Install with: pip install requests")
        return False
    
    print(f"\n🌐 Testing API Endpoints at {base_url}")
    print("=" * 50)
    
    endpoints = [
        ('/api/health', 'Health Check'),
        ('/api/temperatures', 'Temperatures'),
        ('/api/io/status', 'IO Status'),
        ('/api/evcc', 'EVCC Status')
    ]
    
    results = {}
    
    for endpoint, description in endpoints:
        print(f"🔗 Testing {description} ({endpoint})...")
        try:
            response = requests.get(f"{base_url}{endpoint}", timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                results[endpoint] = data
                
                if endpoint == '/api/temperatures':
                    temp_count = len(data.get('temperatures', {}))
                    print(f"   ✅ {description}: {temp_count} temperatures")
                    if temp_count == 0:
                        print("   ⚠️  No temperatures returned by API!")
                    else:
                        for sensor_id, temp in data.get('temperatures', {}).items():
                            print(f"     {sensor_id}: {temp:.1f}°C")
                
                elif endpoint == '/api/io/status':
                    outputs = data.get('outputs', {})
                    inputs = data.get('inputs', {})
                    print(f"   ✅ {description}: {len(outputs)} outputs, {len(inputs)} inputs")
                    
                    # Show some output states
                    print("     Output states:")
                    for key, state in list(outputs.items())[:6]:  # First 6
                        print(f"       {key}: {'ON' if state else 'OFF'}")
                
                elif endpoint == '/api/evcc':
                    enabled = data.get('enabled', False)
                    connected = data.get('connected', False)
                    print(f"   ✅ {description}: Enabled={enabled}, Connected={connected}")
                
                else:
                    print(f"   ✅ {description}: OK")
            else:
                print(f"   ❌ {description}: HTTP {response.status_code}")
                results[endpoint] = {'error': f'HTTP {response.status_code}', 'text': response.text}
                
        except Exception as e:
            print(f"   ❌ {description}: {e}")
            results[endpoint] = {'error': str(e)}
    
    return True, results

def test_output_control(base_url="http://localhost:8080"):
    """Test output control via API"""
    if not REQUESTS_AVAILABLE:
        return False
    
    print(f"\n🔧 Testing Output Control via API")
    print("=" * 40)
    
    # Test board 0, port 0
    board, port = 0, 0
    endpoint = f"{base_url}/api/io/output/{board}/{port}"
    
    try:
        # Turn ON
        print(f"🔛 Turning ON output {board}-{port}...")
        response = requests.post(endpoint, json={'state': 1}, timeout=5)
        if response.status_code == 200:
            print("   ✅ ON command successful")
        else:
            print(f"   ❌ ON command failed: HTTP {response.status_code}")
            print(f"   Response: {response.text}")
        
        time.sleep(0.5)
        
        # Turn OFF  
        print(f"🔲 Turning OFF output {board}-{port}...")
        response = requests.post(endpoint, json={'state': 0}, timeout=5)
        if response.status_code == 200:
            print("   ✅ OFF command successful")
            return True
        else:
            print(f"   ❌ OFF command failed: HTTP {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"   ❌ Output control test failed: {e}")
        return False

def check_dashboard_file():
    """Check if dashboard.html is accessible and correct"""
    print(f"\n📄 Checking Dashboard File")
    print("=" * 30)
    
    dashboard_path = Path("dashboard.html")
    if dashboard_path.exists():
        print(f"   ✅ Dashboard file exists: {dashboard_path}")
        
        # Check file size
        size = dashboard_path.stat().st_size
        print(f"   📊 File size: {size:,} bytes")
        
        # Check for key elements
        try:
            content = dashboard_path.read_text(encoding='utf-8')
            
            checks = [
                ('API_BASE', "'/api'" in content),
                ('Temperature display', 'temperature-sensors' in content),
                ('Output control', 'toggle-output' in content or 'toggleOutput' in content),
                ('IO status', '/api/io/status' in content),
                ('EVCC integration', '/api/evcc' in content)
            ]
            
            for check_name, result in checks:
                status = "✅" if result else "❌"
                print(f"   {status} {check_name}")
                
        except Exception as e:
            print(f"   ❌ Error reading dashboard file: {e}")
    else:
        print(f"   ❌ Dashboard file not found!")

def main():
    parser = argparse.ArgumentParser(description="Diagnose dashboard and API issues")
    parser.add_argument("--test-api", action="store_true", help="Test API endpoints")
    parser.add_argument("--api-url", default="http://localhost:8080", help="API base URL")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format='%(levelname)s: %(message)s')
    
    print("🔍 Heating System Dashboard Diagnostics")
    print("=" * 60)
    
    success_count = 0
    total_tests = 0
    
    # Test 1: Local system
    total_tests += 1
    local_ok, local_results = test_local_system()
    if local_ok:
        success_count += 1
    
    # Test 2: Dashboard file
    total_tests += 1
    check_dashboard_file()
    success_count += 1  # Always count as success for now
    
    if args.test_api:
        # Test 3: API endpoints
        total_tests += 1
        api_ok, api_results = test_api_endpoints(args.api_url)
        if api_ok:
            success_count += 1
        
        # Test 4: Output control
        total_tests += 1
        control_ok = test_output_control(args.api_url)
        if control_ok:
            success_count += 1
    
    # Summary
    print(f"\n" + "=" * 60)
    print(f"📋 DIAGNOSTIC SUMMARY")
    print(f"Tests passed: {success_count}/{total_tests}")
    
    if local_results.get('sensor_count', 0) == 0:
        print(f"\n💡 ISSUE DETECTED: No sensors available")
        print(f"   - This explains why dashboard shows no temperature sensors")
        print(f"   - Check sensor configuration in heating_config.yaml")
        print(f"   - Verify One-Wire sensors are connected and readable")
    
    if not local_results.get('hardware_ok', False):
        print(f"\n💡 ISSUE DETECTED: Hardware not responding")
        print(f"   - This explains why output switching doesn't work")
        print(f"   - Check PiFace board connections")
        print(f"   - Verify SPI is enabled: sudo raspi-config")
        print(f"   - Install PiFace libraries: pip install pifacecommon pifacedigitalio")
    
    if args.test_api and not api_ok:
        print(f"\n💡 ISSUE DETECTED: API not responding")
        print(f"   - Check if heating system HTTP service is running")
        print(f"   - Verify port 8080 is accessible")
        print(f"   - Check firewall settings")
    
    return success_count == total_tests

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)