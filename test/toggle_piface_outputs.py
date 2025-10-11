#!/usr/bin/env python3
"""Toggle all PiFace outputs on then off for testing.

Usage:
  python scripts/toggle_piface_outputs.py --boards 2 --duration 2 --mock

This will turn on ports 0..7 for each board, wait `duration` seconds, then turn them off.
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


def toggle_all(board_count: int, duration: float, mock: bool = False, delay_between: float = 0.05):
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("toggle_piface")

    hw = create_hardware_controller(board_count=board_count, logger=logger, mock_mode=mock)

    logger.info("Turning all outputs ON")
    for b in range(board_count):
        for p in range(8):
            ok = hw.turn_on(b, p)
            logger.debug(f"Turn ON board {b} port {p}: {ok}")
            time.sleep(delay_between)

    logger.info(f"All outputs ON — waiting {duration} seconds")
    time.sleep(duration)

    logger.info("Turning all outputs OFF")
    for b in range(board_count):
        for p in range(8):
            ok = hw.turn_off(b, p)
            logger.debug(f"Turn OFF board {b} port {p}: {ok}")
            time.sleep(delay_between)

    logger.info("Completed toggling outputs")


def main():
    parser = argparse.ArgumentParser(description="Toggle all PiFace outputs on then off")
    parser.add_argument("--boards", type=int, default=2, help="Number of PiFace boards")
    parser.add_argument("--duration", type=float, default=2.0, help="Seconds to wait while outputs are ON")
    parser.add_argument("--mock", action="store_true", help="Use mock hardware (no PiFace required)")
    parser.add_argument("--delay", type=float, default=0.03, help="Delay between toggling individual pins")

    args = parser.parse_args()
    toggle_all(board_count=args.boards, duration=args.duration, mock=args.mock, delay_between=args.delay)


if __name__ == "__main__":
    main()
