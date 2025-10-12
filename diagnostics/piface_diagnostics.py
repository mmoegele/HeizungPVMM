#!/usr/bin/env python3
"""
Complete PiFace Diagnostic Script
================================

This script performs comprehensive diagnostics for PiFace Digital I/O boards
and helps identify initialization issues.

Usage on Raspberry Pi:
    python3 piface_diagnostics.py
    python3 piface_diagnostics.py --mock  # Test without hardware
"""

import argparse
import logging
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

def test_imports():
    """Test if all required modules can be imported."""
    print("📦 Testing Imports:")
    
    try:
        import gpio
        print("   ✅ gpio module imported")
        
        # Check if GPIO patch was applied
        if hasattr(gpio, '_patch_applied'):
            if gpio._patch_applied:
                print("   ✅ GPIO patch was applied successfully")
            else:
                print("   ⚠️  GPIO patch was not applied")
        
    except ImportError as e:
        print(f"   ❌ gpio module import failed: {e}")
    
    try:
        import pifacecommon
        print("   ✅ pifacecommon imported")
    except ImportError as e:
        print(f"   ❌ pifacecommon import failed: {e}")
        return False
    
    try:
        import pifacedigitalio
        print("   ✅ pifacedigitalio imported")
        return True
    except ImportError as e:
        print(f"   ❌ pifacedigitalio import failed: {e}")
        return False

def test_direct_piface(board_count: int = 2):
    """Test PiFace initialization directly without our wrapper."""
    print(f"\n🔌 Testing Direct PiFace Initialization ({board_count} boards):")
    
    try:
        import pifacedigitalio
        
        boards = []
        for i in range(board_count):
            try:
                print(f"   Initializing board {i}...", end=" ")
                board = pifacedigitalio.PiFaceDigital(i)
                boards.append(board)
                print("✅")
            except Exception as e:
                print(f"❌ Error: {e}")
                boards.append(None)
        
        return boards
        
    except ImportError:
        print("   ❌ pifacedigitalio not available")
        return []
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
        return []

def test_hardware_wrapper(board_count: int = 2, mock: bool = False):
    """Test our hardware wrapper."""
    print(f"\n🔧 Testing Hardware Wrapper (mock={mock}):")
    
    try:
        from hardware import create_hardware_controller
        
        # Setup logger
        logger = logging.getLogger("diagnostic")
        
        hw = create_hardware_controller(
            board_count=board_count,
            logger=logger,
            mock_mode=mock
        )
        
        print(f"   ✅ Hardware controller created: {type(hw).__name__}")
        
        # Run diagnostics if available
        if hasattr(hw, 'run_board_diagnostics'):
            diag = hw.run_board_diagnostics()
            print("   📊 Diagnostics:")
            print(f"      GPIO patch: {diag['gpio_patch_applied']}")
            print(f"      Mock mode: {diag['mock_mode']}")
            print(f"      Board count: {diag['board_count']}")
            
            for board_id, status in diag['boards'].items():
                available = "✅" if status['available'] else "❌"
                responsive = "✅" if status.get('responsive', False) else "❌"
                print(f"      Board {board_id}: Available {available}, Responsive {responsive}")
        
        return hw
        
    except Exception as e:
        print(f"   ❌ Hardware wrapper failed: {e}")
        return None

def test_basic_io(hw, board_count: int = 2):
    """Test basic I/O operations."""
    if hw is None:
        return False
        
    print(f"\n🧪 Testing Basic I/O Operations:")
    
    success_count = 0
    total_tests = 0
    
    for board in range(board_count):
        print(f"   Board {board}:")
        
        for port in range(8):
            total_tests += 1
            try:
                # Test output operations
                on_result = hw.turn_on(board, port)
                time.sleep(0.01)  # Small delay
                state = hw.get_output(board, port)
                off_result = hw.turn_off(board, port)
                
                if on_result and off_result:
                    print(f"      Port {port}: ✅ (ON:{on_result}, State:{state}, OFF:{off_result})")
                    success_count += 1
                else:
                    print(f"      Port {port}: ❌ (ON:{on_result}, State:{state}, OFF:{off_result})")
                    
            except Exception as e:
                print(f"      Port {port}: ❌ Exception: {e}")
    
    print(f"   📈 Success rate: {success_count}/{total_tests} ({100*success_count/total_tests:.1f}%)")
    return success_count == total_tests

def main():
    parser = argparse.ArgumentParser(description="Complete PiFace diagnostic")
    parser.add_argument("--boards", type=int, default=2, help="Number of boards to test")
    parser.add_argument("--mock", action="store_true", help="Use mock hardware")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("🔍 PiFace Digital I/O Complete Diagnostics")
    print("=" * 50)
    
    # Test 1: Import test
    imports_ok = test_imports()
    
    # Test 2: Direct PiFace test (only if not mock and imports work)
    if not args.mock and imports_ok:
        boards = test_direct_piface(args.boards)
        direct_ok = any(board is not None for board in boards)
    else:
        direct_ok = True  # Skip this test
        
    # Test 3: Hardware wrapper test
    hw = test_hardware_wrapper(args.boards, args.mock)
    wrapper_ok = hw is not None
    
    # Test 4: Basic I/O test
    io_ok = test_basic_io(hw, args.boards) if hw else False
    
    # Summary
    print("\n" + "=" * 50)
    print("📋 DIAGNOSTIC SUMMARY:")
    print(f"   Import test: {'✅' if imports_ok else '❌'}")
    print(f"   Direct PiFace: {'✅' if direct_ok else '❌'}")
    print(f"   Hardware wrapper: {'✅' if wrapper_ok else '❌'}")
    print(f"   Basic I/O: {'✅' if io_ok else '❌'}")
    
    if imports_ok and wrapper_ok and io_ok:
        print("\n🎉 All tests passed! PiFace appears to be working correctly.")
        return True
    else:
        print(f"\n⚠️  Some tests failed. Check the details above.")
        
        if not imports_ok:
            print("\n💡 Import issues suggest:")
            print("   - PiFace libraries not installed: pip install pifacedigitalio")
            print("   - SPI not enabled: sudo raspi-config -> Interface Options -> SPI")
            
        if not args.mock and not direct_ok:
            print("\n💡 Direct PiFace issues suggest:")
            print("   - Hardware not connected properly")
            print("   - SPI interface issues")
            print("   - Permission problems (try with sudo)")
            
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)