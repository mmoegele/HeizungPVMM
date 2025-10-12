#!/usr/bin/env python3
"""Cycle through PiFace outputs one by one for testing.

Usage:
  python test/toggle_piface_outputs.py --boards 2 --duration 1.0 --mock

This will cycle through each port (0-7) on each board, turning each on for 
`duration` seconds, then off, before moving to the next port. This makes it 
easy to visually verify which outputs are working.
"""

import argparse
import logging
import time
import sys
from pathlib import Path

# Ensure project root is on sys.path so imports work when running this file directly
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from hardware import create_hardware_controller


def toggle_sequential(board_count: int, duration: float, mock: bool = False, delay_between: float = 0.05):
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger("toggle_piface")

    print(f"🔧 Starting PiFace test with {board_count} boards")
    print(f"   Mock mode: {mock}")
    print(f"   Duration: {duration}s")
    print(f"   Delay between pins: {delay_between}s")

    hw = create_hardware_controller(board_count=board_count, logger=logger, mock_mode=mock)
    
    # Check hardware status
    if hasattr(hw, 'run_board_diagnostics'):
        diagnostics = hw.run_board_diagnostics()
        print(f"🔍 Hardware diagnostics:")
        print(f"   GPIO patch applied: {diagnostics['gpio_patch_applied']}")
        print(f"   Mock mode active: {diagnostics['mock_mode']}")
        print(f"   Board status: {diagnostics['boards']}")
    else:
        print("⚠️  No diagnostics available")
        print(f"   Hardware type: {type(hw).__name__}")

    print("\n� Cycling through outputs (one at a time)")
    logger.info("Starting sequential output cycling")
    
    for b in range(board_count):
        print(f"\n📋 Testing Board {b}:")
        for p in range(8):
            print(f"   Port {p}: ", end="", flush=True)
            
            # Turn on this port
            on_result = hw.turn_on(b, p)
            if on_result:
                print(f"ON ✅", end="", flush=True)
            else:
                print(f"ON ❌", end="", flush=True)
            
            logger.debug(f"Board {b} Port {p} turned ON: {on_result}")
            
            # Wait for the specified duration
            print(f" (waiting {duration}s)", end="", flush=True)
            time.sleep(duration)
            
            # Turn off this port
            off_result = hw.turn_off(b, p)
            if off_result:
                print(f" OFF ✅")
            else:
                print(f" OFF ❌")
            
            logger.debug(f"Board {b} Port {p} turned OFF: {off_result}")
            
            # Small delay between pins
            time.sleep(delay_between)

    print(f"\n✅ Completed cycling through all {board_count * 8} outputs")
    logger.info("Completed output cycling test")


def main():
    parser = argparse.ArgumentParser(description="Cycle through PiFace outputs one by one")
    parser.add_argument("--boards", type=int, default=2, help="Number of PiFace boards")
    parser.add_argument("--duration", type=float, default=1.0, help="Seconds each output stays ON")
    parser.add_argument("--mock", action="store_true", help="Use mock hardware (no PiFace required)")
    parser.add_argument("--delay", type=float, default=1, help="Delay between switching to next pin")

    args = parser.parse_args()
    toggle_sequential(board_count=args.boards, duration=args.duration, mock=args.mock, delay_between=args.delay)


if __name__ == "__main__":
    main()
