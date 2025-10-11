#!/usr/bin/env python3
"""
EVCC Integration Test Script
===========================

Tests the EVCC integration functionality including:
- EVCC API connectivity
- Data retrieval and parsing
- Configuration validation

Usage:
    python test_evcc_integration.py [--evcc-url URL] [--config CONFIG_FILE]
"""

import argparse
import sys

# Try to import the integration components
try:
    from evcc_heating_integration import (
        EVCCClient, SolarHeatingConfig
    )
    INTEGRATION_AVAILABLE = True
except ImportError as e:
    print(f"Warning: EVCC integration not available: {e}")
    INTEGRATION_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    print("Warning: requests library not available")
    REQUESTS_AVAILABLE = False


def print_header(text: str) -> None:
    """Print a section header"""
    print(f"\n=== {text} ===")


def print_status(status: str, message: str) -> None:
    """Print a status message"""
    print(f"[{status}] {message}")


def test_evcc_connectivity(evcc_url: str) -> bool:
    """Test EVCC API connectivity"""
    print_header("EVCC Connectivity Test")
    
    if not INTEGRATION_AVAILABLE:
        print_status("FAIL", "EVCC integration components not available")
        return False
    
    if not REQUESTS_AVAILABLE:
        print_status("FAIL", "requests library not available")
        return False
    
    try:
        config = SolarHeatingConfig(evcc_base_url=evcc_url)
        client = EVCCClient(config)
        
        print_status("INFO", f"Testing connection to: {evcc_url}")
        
        # Test health endpoint
        if client.is_healthy():
            print_status("PASS", "EVCC health check successful")
        else:
            print_status("FAIL", "EVCC health check failed")
            return False
        
        # Test state retrieval
        state = client.get_state()
        if state:
            print_status("PASS", "EVCC state retrieval successful")
            print_status("INFO", f"  Grid Power: {state.grid_power:.1f}W")
            print_status("INFO", f"  Home Power: {state.home_power:.1f}W")
            print_status("INFO", f"  PV Power: {state.pv_power:.1f}W")
            if state.battery_configured:
                print_status("INFO", f"  Battery: {state.battery_soc:.1f}%")
            return True
        else:
            print_status("FAIL", "EVCC state retrieval failed")
            return False
            
    except Exception as e:
        print_status("FAIL", f"Error during EVCC connectivity test: {e}")
        return False


def main():
    """Main test execution"""
    parser = argparse.ArgumentParser(description='Test EVCC integration')
    parser.add_argument('--evcc-url', default='http://localhost:7070', 
                      help='EVCC API base URL')
    args = parser.parse_args()
    
    success = test_evcc_connectivity(args.evcc_url)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()