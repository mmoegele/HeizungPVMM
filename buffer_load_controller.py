#!/usr/bin/env python3
"""
Simple Buffer Loading Controller Module

Very simple buffer loading pump control:
1. Check if Konrad buffer temp > Michael buffer temp  
2. If yes: Turn pump ON
3. If no: Turn pump OFF
4. Wait 1 minute
5. Repeat
"""

import logging
import threading
import time
from typing import Optional, Dict
from datetime import datetime
from dataclasses import dataclass
from hardware import HeatingHardware
from sensors import SensorManager

@dataclass
class BufferState:
    """Simple buffer state"""
    konrad_temp: float = 0.0
    michael_temp: float = 0.0
    pump_active: bool = False
    last_action: str = "none"
    last_check_time: datetime = None
    error_message: Optional[str] = None

class BufferLoadController:
    """Very simple buffer loading pump controller"""
    
    def __init__(self, config: Dict, hardware: HeatingHardware, 
                 sensor_manager: SensorManager, logger: logging.Logger):
        self.hardware = hardware
        self.sensor_manager = sensor_manager
        self.logger = logger
        
        # Configuration
        self.konrad_sensor = config.get('source_sensor', 'puffer_k_mitte')
        self.michael_sensor = config.get('target_sensor', 'puffer_m_mitte') 
        self.pump_port = config.get('pump_port', 'puffer_lade_pumpe')
        self.min_temp_difference = config.get('min_temperature_difference', 3.0)  # Minimum temperature difference to start pump
        self.check_interval = 60.0  # 1 minute between checks
        
        # State
        self.state = BufferState(last_check_time=datetime.now())
        
        # Running flag
        self.running = False
        self.thread = None
        
        self.logger.info(f"Simple buffer load controller initialized")
        self.logger.info(f"  Konrad sensor: {self.konrad_sensor}")
        self.logger.info(f"  Michael sensor: {self.michael_sensor}")
        self.logger.info(f"  Pump port: {self.pump_port}")
        self.logger.info(f"  Min temp difference: {self.min_temp_difference}°C")
        self.logger.info(f"  Check interval: {self.check_interval}s")
    
    def start(self):
        """Start the buffer load control loop"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._control_loop, daemon=True)
        self.thread.start()
        self.logger.info("Started buffer load controller")
    
    def stop(self):
        """Stop the buffer load control loop"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        # Turn off pump when stopping
        try:
            self.hardware.set_output(self.pump_port, False)
            self.state.pump_active = False
            self.logger.info("Stopped buffer load controller and turned off pump")
        except Exception as e:
            self.logger.error(f"Error stopping pump: {e}")
    
    def _control_loop(self):
        """Main control loop - runs continuously"""
        self.logger.info("Buffer load controller: Starting control loop")
        
        while self.running:
            try:
                # Check temperatures and control pump
                self._check_and_control()
                
                # Wait for next cycle
                time.sleep(self.check_interval)
                
            except Exception as e:
                self.logger.error(f"Buffer load controller error: {e}")
                # Safety: turn off pump on error
                try:
                    self.hardware.set_output(self.pump_port, False)
                    self.state.pump_active = False
                    self.state.error_message = str(e)
                except:
                    pass
                time.sleep(self.check_interval)
    
    def _check_and_control(self):
        """Check temperatures and control pump"""
        try:
            # Get all temperature readings (like System Data Reporter does)
            all_temps = self.sensor_manager.read_all_temperatures()
            
            # Enhanced debug logging for sensor diagnostics
            self.logger.info(f"Buffer controller sensor debug:")
            self.logger.info(f"  Total sensors available: {len(all_temps)}")
            self.logger.info(f"  Looking for: {self.konrad_sensor}, {self.michael_sensor}")
            
            # Debug: Show all available sensors
            available_sensors = list(all_temps.keys())
            self.logger.info(f"  Available sensors: {available_sensors}")
            
            # Extract valid temperatures manually
            konrad_temp = None
            michael_temp = None
            
            if self.konrad_sensor in all_temps:
                reading = all_temps[self.konrad_sensor]
                self.logger.info(f"  {self.konrad_sensor}: exists={True}, is_valid={reading.is_valid}, value={reading.value}, error={reading.error_message}")
                if reading.is_valid and reading.error_message is None:
                    konrad_temp = reading.value
                else:
                    self.logger.debug(f"Konrad sensor {self.konrad_sensor}: valid={reading.is_valid}, error={reading.error_message}")
            else:
                self.logger.warning(f"  {self.konrad_sensor}: NOT FOUND in sensor manager")
            
            if self.michael_sensor in all_temps:
                reading = all_temps[self.michael_sensor]
                self.logger.info(f"  {self.michael_sensor}: exists={True}, is_valid={reading.is_valid}, value={reading.value}, error={reading.error_message}")
                if reading.is_valid and reading.error_message is None:
                    michael_temp = reading.value
                else:
                    self.logger.debug(f"Michael sensor {self.michael_sensor}: valid={reading.is_valid}, error={reading.error_message}")
            else:
                self.logger.warning(f"  {self.michael_sensor}: NOT FOUND in sensor manager")
            # Debug logging
            self.logger.debug(f"Temperature readings: {self.konrad_sensor}={konrad_temp}°C, {self.michael_sensor}={michael_temp}°C")
            
            if konrad_temp is None or michael_temp is None:
                # No valid temperatures - turn off pump for safety
                if self.state.pump_active:
                    self.hardware.set_output(self.pump_port, False)
                    self.state.pump_active = False
                    self.state.last_action = "stop"
                    self.logger.warning("Missing temperature readings - pump stopped")
                
                missing = []
                if konrad_temp is None:
                    missing.append(self.konrad_sensor)
                if michael_temp is None:
                    missing.append(self.michael_sensor)
                self.state.error_message = f"Missing sensors: {', '.join(missing)}"
                return
            
            # Update state
            self.state.konrad_temp = konrad_temp
            self.state.michael_temp = michael_temp
            self.state.last_check_time = datetime.now()
            self.state.error_message = None
            
            # Simple logic: If (Konrad - Michael) > min_temp_difference, turn pump ON, else turn pump OFF
            temp_difference = konrad_temp - michael_temp
            should_pump_run = temp_difference > self.min_temp_difference
            
            self.logger.info(f"Buffer control decision: Diff={temp_difference:.1f}°C, Min={self.min_temp_difference}°C, Should run={should_pump_run}, Currently active={self.state.pump_active}")
            
            # ALWAYS set the hardware state to ensure it matches desired state
            # This handles PiFace reinitialization that resets all outputs to OFF
            try:
                # Check hardware health before attempting control
                if hasattr(self.hardware, 'boards') and hasattr(self.hardware, 'port_mapping'):
                    if self.pump_port in self.hardware.port_mapping:
                        board, port = self.hardware.port_mapping[self.pump_port]
                        self.logger.debug(f"Pump port '{self.pump_port}' maps to board {board}, port {port}")
                        
                        # Check if board is available
                        if hasattr(self.hardware, 'boards') and board < len(self.hardware.boards):
                            board_status = self.hardware.boards[board] is not None
                            if not board_status:
                                self.state.error_message = f"PiFace board {board} not available - SPI/hardware issue"
                                self.logger.error(f"Cannot control pump: PiFace board {board} is not available (SPI issue?)")
                                return
                        else:
                            self.logger.warning(f"Board {board} index out of range or boards not initialized")
                    else:
                        self.logger.error(f"Pump port '{self.pump_port}' not found in port mapping")
                        self.state.error_message = f"Port '{self.pump_port}' not mapped"
                        return
                
                # Always set the hardware to the desired state
                result = self.hardware.set_output(self.pump_port, should_pump_run)
                
                if result:
                    # Update internal state tracking
                    state_changed = self.state.pump_active != should_pump_run
                    self.state.pump_active = should_pump_run
                    
                    if state_changed:
                        self.state.last_action = "start" if should_pump_run else "stop"
                    
                    # Verify the hardware actually set the output
                    actual_state = self._verify_hardware_state()
                    if actual_state is not None and actual_state != should_pump_run:
                        self.logger.error(f"❌ Hardware verification FAILED: commanded {should_pump_run} but actual state is {actual_state}")
                        self.state.error_message = "Hardware verification failed - state mismatch"
                    else:
                        action = "ON" if should_pump_run else "OFF"
                        change_note = " (state changed)" if state_changed else " (state maintained)"
                        self.logger.info(f"✅ Buffer pump {action}: Konrad={konrad_temp:.1f}°C - Michael={michael_temp:.1f}°C = {temp_difference:.1f}°C (verified: {actual_state}){change_note}")
                else:
                    self.logger.error(f"❌ Hardware command failed to set pump to {should_pump_run} (returned False)")
                    self.state.error_message = "Hardware command failed (PiFace not responding?)"
                    
            except Exception as e:
                self.logger.error(f"❌ Exception setting buffer pump to {should_pump_run}: {e}")
                self.state.error_message = f"Exception setting pump: {e}"
            
            # Log status every check (even if no change)
            status = "ON" if self.state.pump_active else "OFF"
            self.logger.debug(f"Buffer pump {status}: Konrad={konrad_temp:.1f}°C, Michael={michael_temp:.1f}°C, Diff={temp_difference:.1f}°C")
                
        except Exception as e:
            self.logger.error(f"Error in temperature check: {e}")
            self.state.error_message = f"Control error: {e}"
    
    def _verify_hardware_state(self) -> Optional[bool]:
        """Verify the actual hardware state by reading back the output"""
        try:
            if hasattr(self.hardware, 'port_mapping') and self.pump_port in self.hardware.port_mapping:
                board, port = self.hardware.port_mapping[self.pump_port]
                if hasattr(self.hardware, 'get_output'):
                    actual_state = self.hardware.get_output(board, port)
                    self.logger.debug(f"Hardware state verification: Board {board}, Port {port} = {actual_state}")
                    return actual_state
                else:
                    self.logger.debug("Hardware controller does not support get_output method")
                    return None
            else:
                self.logger.debug(f"Cannot verify hardware state - port '{self.pump_port}' not mapped")
                return None
        except Exception as e:
            self.logger.error(f"Error verifying hardware state: {e}")
            return None
    
    def get_state(self) -> Dict:
        """Get current controller state"""
        temp_difference = self.state.konrad_temp - self.state.michael_temp
        
        # Add hardware diagnostics
        hardware_status = "unknown"
        actual_pump_state = None
        
        if hasattr(self.hardware, 'boards') and hasattr(self.hardware, 'port_mapping'):
            if self.pump_port in self.hardware.port_mapping:
                board, port = self.hardware.port_mapping[self.pump_port]
                if hasattr(self.hardware, 'boards') and board < len(self.hardware.boards):
                    board_available = self.hardware.boards[board] is not None
                    hardware_status = f"Board {board}: {'OK' if board_available else 'FAILED'}"
                    
                    # Try to read actual pump state
                    if board_available:
                        try:
                            actual_pump_state = self.hardware.get_output(board, port)
                        except Exception as e:
                            hardware_status += f" (read error: {e})"
                else:
                    hardware_status = f"Board {board}: OUT_OF_RANGE"
            else:
                hardware_status = f"Port '{self.pump_port}': NOT_MAPPED"
        
        return {
            "konrad_temp": self.state.konrad_temp,
            "michael_temp": self.state.michael_temp,
            "temp_difference": temp_difference,
            "min_temp_difference": self.min_temp_difference,
            "pump_active": self.state.pump_active,
            "actual_pump_state": actual_pump_state,  # NEW: actual hardware state
            "pump_state_mismatch": actual_pump_state is not None and actual_pump_state != self.state.pump_active,  # NEW: detect mismatch
            "last_action": self.state.last_action,
            "last_check_time": self.state.last_check_time.isoformat() if self.state.last_check_time else None,
            "error_message": self.state.error_message,
            "running": self.running,
            "konrad_sensor": self.konrad_sensor,
            "michael_sensor": self.michael_sensor,
            "pump_port": self.pump_port,
            "hardware_status": hardware_status
        }
    
    def update(self) -> bool:
        """Compatibility method - not used in threaded version"""
        return True
    
    def test_pump_manual(self, state: bool) -> Dict:
        """Manual pump test for debugging - returns detailed results"""
        try:
            self.logger.info(f"🔧 Manual pump test: Setting pump to {'ON' if state else 'OFF'}")
            
            # Get hardware mapping info
            if hasattr(self.hardware, 'port_mapping') and self.pump_port in self.hardware.port_mapping:
                board, port = self.hardware.port_mapping[self.pump_port]
                self.logger.info(f"🔧 Pump port '{self.pump_port}' maps to board {board}, port {port}")
                
                # Check board availability
                if hasattr(self.hardware, 'boards') and board < len(self.hardware.boards):
                    board_available = self.hardware.boards[board] is not None
                    self.logger.info(f"🔧 Board {board} status: {'Available' if board_available else 'NOT AVAILABLE'}")
                    
                    if not board_available:
                        return {
                            "success": False,
                            "error": f"PiFace board {board} not available",
                            "board": board,
                            "port": port,
                            "requested_state": state,
                            "actual_state": None
                        }
                else:
                    return {
                        "success": False,
                        "error": f"Board {board} out of range",
                        "board": board,
                        "port": port,
                        "requested_state": state,
                        "actual_state": None
                    }
            else:
                return {
                    "success": False,
                    "error": f"Port '{self.pump_port}' not found in port mapping",
                    "requested_state": state,
                    "actual_state": None
                }
            
            # Execute command
            result = self.hardware.set_output(self.pump_port, state)
            self.logger.info(f"🔧 Hardware command result: {result}")
            
            # Verify result
            time.sleep(0.1)  # Small delay for hardware to settle
            actual_state = self._verify_hardware_state()
            self.logger.info(f"🔧 Actual hardware state after command: {actual_state}")
            
            return {
                "success": result,
                "board": board,
                "port": port,
                "requested_state": state,
                "actual_state": actual_state,
                "state_matches": actual_state == state if actual_state is not None else None,
                "error": None if result else "Hardware command returned False"
            }
            
        except Exception as e:
            self.logger.error(f"🔧 Manual pump test failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "requested_state": state,
                "actual_state": None
            }
    
    def dispose(self):
        """Clean up and shut down"""
        self.stop()

def create_buffer_load_controller(config, hardware, sensor_manager, logger=None) -> BufferLoadController:
    """Factory function to create a simple buffer load controller"""
    
    # Extract configuration from HeatingConfig
    buffer_config = {
        'source_sensor': config.buffer_load.source_sensor,
        'target_sensor': config.buffer_load.target_sensor,
        'pump_port': config.buffer_load.pump_port,
        'min_temperature_difference': config.buffer_load.min_temperature_difference
    }
    
    return BufferLoadController(
        config=buffer_config,
        hardware=hardware,
        sensor_manager=sensor_manager,
        logger=logger or logging.getLogger("buffer_load")
    )