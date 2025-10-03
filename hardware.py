#!/usr/bin/env python3
"""Hardware Control Module - PiFace and GPIO Management"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any
from gpio_fix import apply_gpio_patch

_gpio_patch_applied = apply_gpio_patch()

class HardwareController(ABC):
    @abstractmethod
    def turn_on(self, board: int, port: int) -> bool:
        pass
    
    @abstractmethod
    def turn_off(self, board: int, port: int) -> bool:
        pass
    
    @abstractmethod
    def read_input(self, board: int, port: int) -> bool:
        pass
    
    @abstractmethod
    def get_board_status(self) -> Dict[int, Dict[str, Any]]:
        pass
    
    @abstractmethod
    def dispose(self) -> None:
        pass

class MockHardwareController(HardwareController):
    def __init__(self, board_count: int, logger: logging.Logger):
        self.logger = logger
        self.board_count = board_count
        self.output_states = {}
        
    def turn_on(self, board: int, port: int) -> bool:
        self.output_states[(board, port)] = True
        self.logger.debug(f"MOCK: Turned ON board {board}, port {port}")
        return True
    
    def turn_off(self, board: int, port: int) -> bool:
        self.output_states[(board, port)] = False
        self.logger.debug(f"MOCK: Turned OFF board {board}, port {port}")
        return True
    
    def read_input(self, board: int, port: int) -> bool:
        return False
    
    def get_board_status(self) -> Dict[int, Dict[str, Any]]:
        return {i: {"available": True, "mock": True} for i in range(self.board_count)}
    
    def dispose(self) -> None:
        """Properly dispose of all resources"""
        if self.mock_mode:
            if hasattr(self, 'mock_controller'):
                self.mock_controller.dispose()
            return
        
        # Turn off all outputs safely
        for i, board in enumerate(getattr(self, 'boards', [])):
            if board:
                try:
                    for port in range(8):
                        board.output_pins[port].turn_off()
                    # Properly deinitialize board if method exists
                    if hasattr(board, 'deinit'):
                        board.deinit()
                except Exception as e:
                    self.logger.warning(f"Error disposing board {i}: {e}")
        
        # Clear board references
        if hasattr(self, 'boards'):
            self.boards = []
        self.logger.info("PiFace controller disposed")

class PiFaceController(HardwareController):
    def __init__(self, board_count: int, logger: logging.Logger, mock_mode: bool = False):
        self.logger = logger
        self.board_count = board_count
        self.mock_mode = mock_mode
        self.gpio_patch_applied = _gpio_patch_applied
        
        if mock_mode:
            self.mock_controller = MockHardwareController(board_count, logger)
        else:
            self._initialize_boards()
    
    def _initialize_boards(self):
        try:
            if self.gpio_patch_applied:
                self.logger.info("🔧 GPIO patch applied - PiFace should initialize cleanly")
            
            import pifacedigitalio
            self.boards = []
            
            for i in range(self.board_count):
                try:
                    board = pifacedigitalio.PiFaceDigital(i)
                    self.boards.append(board)
                    self.logger.info(f"✅ PiFace board {i} initialized")
                except Exception as e:
                    self.logger.error(f"Failed to initialize board {i}: {e}")
                    self.boards.append(None)
            
        except ImportError:
            self.logger.warning("PiFace library not available, using mock mode")
            self.mock_mode = True
            self.mock_controller = MockHardwareController(self.board_count, self.logger)
    
    def turn_on(self, board: int, port: int) -> bool:
        if self.mock_mode:
            return self.mock_controller.turn_on(board, port)
        
        try:
            if self.boards[board]:
                self.boards[board].output_pins[port].turn_on()
                return True
        except Exception as e:
            self.logger.error(f"Failed to turn on board {board}, port {port}: {e}")
        return False
    
    def turn_off(self, board: int, port: int) -> bool:
        if self.mock_mode:
            return self.mock_controller.turn_off(board, port)
        
        try:
            if self.boards[board]:
                self.boards[board].output_pins[port].turn_off()
                return True
        except Exception as e:
            self.logger.error(f"Failed to turn off board {board}, port {port}: {e}")
        return False
    
    def read_input(self, board: int, port: int) -> bool:
        if self.mock_mode:
            return self.mock_controller.read_input(board, port)
        
        try:
            if self.boards[board]:
                return bool(self.boards[board].input_pins[port].value)
        except Exception as e:
            self.logger.error(f"Failed to read input board {board}, port {port}: {e}")
        return False
    
    def get_board_status(self) -> Dict[int, Dict[str, Any]]:
        if self.mock_mode:
            return self.mock_controller.get_board_status()
        
        status = {}
        for i, board in enumerate(getattr(self, 'boards', [])):
            status[i] = {
                "available": board is not None,
                "responsive": True if board else False
            }
        return status
    
    def run_board_diagnostics(self) -> Dict[str, Any]:
        return {
            "gpio_patch_applied": self.gpio_patch_applied,
            "mock_mode": self.mock_mode,
            "board_count": self.board_count,
            "boards": self.get_board_status()
        }
    
    def dispose(self) -> None:
        if self.mock_mode:
            self.mock_controller.dispose()
            return
        
        # Turn off all outputs
        for i, board in enumerate(getattr(self, 'boards', [])):
            if board:
                try:
                    for port in range(8):
                        board.output_pins[port].turn_off()
                except:
                    pass
        self.logger.info("PiFace controller disposed")

def create_hardware_controller(board_count: int, logger: logging.Logger, mock_mode: bool = False):
    return PiFaceController(board_count, logger, mock_mode)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("hardware_test")
    print("🔧 Hardware Module Test")
    hw = PiFaceController(2, logger)
    print("✅ Hardware test completed")
