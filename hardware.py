#!/usr/bin/env python3
"""Hardware Control Module - PiFace and GPIO Management"""

__all__ = ['HeatingHardware', 'create_hardware_controller']

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any



class HeatingHardware(ABC):
    def __init__(self):
        # Default hardware configuration mapping for outputs
        self.port_mapping = {
            'puffer_lade_pumpe': (0, 6),
            'mischer_1_auf': (0, 1),
            'mischer_1_zu': (0, 0),
            'mischer_2_auf': (0, 4),
            'mischer_2_zu': (0, 3),
            'wt_pumpe': (1, 7),
            'bhkw_start': (0, 5),
            'heizstab_1': (1, 0),
            'heizstab_2': (1, 1),
            'heizstab_3': (1, 2)
        }
        
        # Default hardware configuration mapping for inputs
        self.input_mapping = {
            'bhkw_running_status': (0, 0)
        }
    
    def set_output(self, port_ref, state: bool) -> bool:
        """Set output state using either (board, port) tuple or string reference"""
        if isinstance(port_ref, str):
            if port_ref in self.port_mapping:
                board, port = self.port_mapping[port_ref]
            else:
                raise ValueError(f"Unknown port reference: {port_ref}")
        elif isinstance(port_ref, tuple) and len(port_ref) == 2:
            board, port = port_ref
        else:
            raise ValueError(f"Invalid port reference: {port_ref}")
        
        if state:
            return self.turn_on(board, port)
        else:
            return self.turn_off(board, port)
    
    def get_input_by_name(self, input_ref) -> bool:
        """Get input state using either (board, port) tuple or string reference"""
        if isinstance(input_ref, str):
            if input_ref in self.input_mapping:
                board, port = self.input_mapping[input_ref]
            else:
                raise ValueError(f"Unknown input reference: {input_ref}")
        elif isinstance(input_ref, tuple) and len(input_ref) == 2:
            board, port = input_ref
        else:
            raise ValueError(f"Invalid input reference: {input_ref}")
        
        return self.get_input(board, port)
    
    def get_input(self, board: int, port: int) -> bool:
        """Get current input state - override in subclasses"""
        return False
    
    def get_input(self, board: int, port: int) -> bool:
        """Get input state - alias for read_input"""
        return self.read_input(board, port)
    
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
    
    def turn_off_all_outputs(self) -> None:
        """Turn off all outputs on all boards"""
        # Get all configured outputs from port_mapping
        for port_name, (board, port) in self.port_mapping.items():
            try:
                self.turn_off(board, port)
            except Exception as e:
                # Continue with other ports even if one fails
                print(f"Warning: Failed to turn off {port_name} (board {board}, port {port}): {e}")
        print("🔄 All outputs turned OFF")

class MockHardwareController(HeatingHardware):
    def __init__(self, board_count: int, logger: logging.Logger):
        super().__init__()
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
    
    def get_output(self, board: int, port: int) -> bool:
        return self.output_states.get((board, port), False)
    
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

class PiFaceController(HeatingHardware):
    def __init__(self, board_count: int, logger: logging.Logger, mock_mode: bool = False):
        super().__init__()
        self.logger = logger
        self.board_count = board_count
        self.mock_mode = mock_mode
        
        # Periodic reinitialization tracking
        import time
        import threading
        self.last_init_time = time.time()
        self.reinit_interval = 6 * 60 * 60  # 6 hours in seconds
        self.reinit_lock = threading.Lock()
        
        if mock_mode:
            self.mock_controller = MockHardwareController(board_count, logger)
        else:
            self._initialize_boards()
    
    def _initialize_boards(self):
        try:
            if self.mock_mode:
                self.logger.info("Running in demo/mock mode - using simulated hardware")
                return
            
            self.logger.info("🔄 Starting PiFace board initialization...")
            import pifacedigitalio as pfdio
            import pifacecommon.interrupts
            
            # Override the enable_interrupts method - EXACT copy from working test
            # Replace problematic interrupt functions with safe no-ops
            def dummy_gpio_interrupts_enable():
                pass
                
            def dummy_gpio_interrupts_disable():
                pass
                
            def dummy_bring_gpio_interrupt_into_userspace():
                pass
            
            # Apply the monkey patches
            pifacecommon.interrupts.gpio_interrupts_enable = dummy_gpio_interrupts_enable
            pifacecommon.interrupts.gpio_interrupts_disable = dummy_gpio_interrupts_disable
            pifacecommon.interrupts.bring_gpio_interrupt_into_userspace = dummy_bring_gpio_interrupt_into_userspace
            
            self.logger.info("✅ GPIO interrupt monkey patch applied successfully")
            
            self.boards = []
            
            for i in range(self.board_count):
                try:
                    self.logger.info(f"🔄 Initializing PiFace board {i} with interrupt patch...")
                    
                    # Now initialize normally - interrupts will be skipped - EXACT copy from working test
                    board = pfdio.PiFaceDigital(hardware_addr=i)
                    
                    self.boards.append(board)
                    self.logger.info(f"✅ PiFace board {i} initialized with interrupt patch")
                        
                except Exception as e:
                    # Log specific error details for diagnosis
                    self.logger.error(f"❌ PiFace board {i} initialization error: {e}")
                    self.boards.append(None)
            
            # Check if any boards were successfully initialized
            working_boards = [b for b in self.boards if b is not None]
            total_boards = len(self.boards)
            
            if working_boards:
                self.logger.info(f"✅ PiFace initialization completed - {len(working_boards)}/{total_boards} boards active")
            else:
                self.logger.error(f"❌ No PiFace boards initialized successfully ({total_boards} attempted)")
                self.logger.error("   System will continue but hardware control will be unavailable")
                self.logger.error("   Check SPI configuration and hardware connections")
            
        except ImportError:
            self.logger.error("❌ PiFace library not available")
            self.logger.error("   Install with: sudo apt-get install python3-pifacedigitalio")
            # Initialize empty boards list so system can continue
            self.boards = [None] * self.board_count
    
    def _check_and_reinitialize_if_needed(self):
        """Check if boards need reinitialization and do it if necessary"""
        if self.mock_mode:
            return
        
        import time
        current_time = time.time()
        
        # Check if 6 hours have passed since last initialization
        if current_time - self.last_init_time >= self.reinit_interval:
            with self.reinit_lock:
                # Double-check after acquiring lock
                if current_time - self.last_init_time >= self.reinit_interval:
                    self.logger.info("🔄 6 hours passed - reinitializing PiFace boards for stability...")
                    
                    # Dispose of current boards safely
                    try:
                        if hasattr(self, 'boards'):
                            for i, board in enumerate(self.boards):
                                if board is not None:
                                    try:
                                        # Turn off all outputs before disposal
                                        for port in range(8):
                                            board.output_pins[port].turn_off()
                                    except Exception as e:
                                        self.logger.warning(f"Error turning off outputs on board {i} during reinit: {e}")
                    except Exception as e:
                        self.logger.warning(f"Error during board cleanup: {e}")
                    
                    # Reinitialize boards
                    self._initialize_boards()
                    self.last_init_time = current_time
                    self.logger.info("✅ PiFace boards reinitialized successfully")
    
    def force_reinitialize(self):
        """Force immediate reinitialization of PiFace boards"""
        if self.mock_mode:
            self.logger.info("Mock mode - skipping board reinitialization")
            return
        
        with self.reinit_lock:
            self.logger.info("🔄 Manual reinitialization of PiFace boards requested...")
            self.last_init_time = 0  # Reset timer
            self._check_and_reinitialize_if_needed()

    def turn_on(self, board: int, port: int) -> bool:
        if self.mock_mode:
            return self.mock_controller.turn_on(board, port)
        
        # Check if boards need reinitialization
        self._check_and_reinitialize_if_needed()
        
        try:
            if board < len(self.boards) and self.boards[board] is not None:
                self.boards[board].output_pins[port].turn_on()
                self.logger.debug(f"Board {board}, port {port} turned ON")
                return True
            else:
                self.logger.warning(f"Board {board} not available - cannot turn on port {port}")
                return False
        except Exception as e:
            self.logger.error(f"Failed to turn on board {board}, port {port}: {e}")
            # If command fails, try reinitialization on next call
            self.last_init_time = 0  # Force reinit on next call
        return False
    
    def turn_off(self, board: int, port: int) -> bool:
        if self.mock_mode:
            return self.mock_controller.turn_off(board, port)
        
        # Check if boards need reinitialization
        self._check_and_reinitialize_if_needed()
        
        try:
            if board < len(self.boards) and self.boards[board] is not None:
                self.boards[board].output_pins[port].turn_off()
                self.logger.debug(f"Board {board}, port {port} turned OFF")
                return True
            else:
                self.logger.warning(f"Board {board} not available - cannot turn off port {port}")
                return False
        except Exception as e:
            self.logger.error(f"Failed to turn off board {board}, port {port}: {e}")
            # If command fails, try reinitialization on next call
            self.last_init_time = 0  # Force reinit on next call
        return False
    
    def read_input(self, board: int, port: int) -> bool:
        if self.mock_mode:
            return self.mock_controller.read_input(board, port)
        
        try:
            if board < len(self.boards) and self.boards[board] is not None:
                return bool(self.boards[board].input_pins[port].value)
            else:
                self.logger.warning(f"Board {board} not available - cannot read input {port}")
                return False
        except Exception as e:
            self.logger.error(f"Failed to read input board {board}, port {port}: {e}")
        return False
    
    def get_output(self, board: int, port: int) -> bool:
        if self.mock_mode:
            return self.mock_controller.get_output(board, port)
        
        try:
            if board < len(self.boards) and self.boards[board] is not None:
                return bool(self.boards[board].output_pins[port].value)
            else:
                self.logger.warning(f"Board {board} not available - cannot get output state {port}")
                return False
        except Exception as e:
            self.logger.error(f"Failed to get output state board {board}, port {port}: {e}")
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

def create_hardware_controller(board_count: int, logger: logging.Logger, mock_mode: bool = False) -> HeatingHardware:
    """
    Create appropriate hardware controller based on mode. Returns a HeatingHardware instance.
    
    Args:
        board_count: Number of PiFace boards to control
        logger: Logger instance for output
        mock_mode: If True, uses simulated hardware (default in demo mode)
        
    Returns:
        HeatingHardware: Either a real PiFace controller or a mock controller for testing
    """
    if mock_mode:
        logger.info("Demo mode active - using simulated hardware controller")
    return PiFaceController(board_count, logger, mock_mode)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("hardware_test")
    print("🔧 Hardware Module Test")
    hw = PiFaceController(2, logger)
    print("✅ Hardware test completed")
