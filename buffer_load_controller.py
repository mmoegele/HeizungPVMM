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
            
            # Extract valid temperatures manually
            konrad_temp = None
            michael_temp = None
            
            if self.konrad_sensor in all_temps:
                reading = all_temps[self.konrad_sensor]
                if reading.is_valid and reading.error_message is None:
                    konrad_temp = reading.value
                else:
                    self.logger.debug(f"Konrad sensor {self.konrad_sensor}: valid={reading.is_valid}, error={reading.error_message}")
            
            if self.michael_sensor in all_temps:
                reading = all_temps[self.michael_sensor]
                if reading.is_valid and reading.error_message is None:
                    michael_temp = reading.value
                else:
                    self.logger.debug(f"Michael sensor {self.michael_sensor}: valid={reading.is_valid}, error={reading.error_message}")
            
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
            
            if should_pump_run and not self.state.pump_active:
                # Turn pump ON
                try:
                    self.logger.info(f"Attempting to turn ON pump at port '{self.pump_port}'...")
                    
                    # Check hardware health before attempting control
                    if hasattr(self.hardware, 'boards') and hasattr(self.hardware, 'port_mapping'):
                        if self.pump_port in self.hardware.port_mapping:
                            board, port = self.hardware.port_mapping[self.pump_port]
                            self.logger.info(f"Pump port '{self.pump_port}' maps to board {board}, port {port}")
                            
                            # Check if board is available
                            if hasattr(self.hardware, 'boards') and board < len(self.hardware.boards):
                                board_status = self.hardware.boards[board] is not None
                                self.logger.info(f"PiFace board {board} status: {'Available' if board_status else 'NOT AVAILABLE'}")
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
                    
                    result = self.hardware.set_output(self.pump_port, True)
                    if result:
                        self.state.pump_active = True
                        self.state.last_action = "start"
                        self.logger.info(f"✅ Buffer pump ON: Konrad={konrad_temp:.1f}°C - Michael={michael_temp:.1f}°C = {temp_difference:.1f}°C > {self.min_temp_difference}°C")
                    else:
                        self.logger.error(f"❌ Hardware command failed to turn ON pump (returned False)")
                        self.state.error_message = "Hardware command failed (PiFace not responding?)"
                except Exception as e:
                    self.logger.error(f"❌ Exception turning ON buffer pump: {e}")
                    self.state.error_message = f"Exception turning ON pump: {e}"
                
            elif not should_pump_run and self.state.pump_active:
                # Turn pump OFF
                try:
                    self.logger.info(f"Attempting to turn OFF pump at port '{self.pump_port}'...")
                    result = self.hardware.set_output(self.pump_port, False)
                    if result:
                        self.state.pump_active = False
                        self.state.last_action = "stop"
                        self.logger.info(f"✅ Buffer pump OFF: Konrad={konrad_temp:.1f}°C - Michael={michael_temp:.1f}°C = {temp_difference:.1f}°C <= {self.min_temp_difference}°C")
                    else:
                        self.logger.error(f"❌ Hardware command failed to turn OFF pump (returned False)")
                        self.state.error_message = "Hardware command failed (PiFace not responding?)"
                except Exception as e:
                    self.logger.error(f"❌ Exception turning OFF buffer pump: {e}")
                    self.state.error_message = f"Exception turning OFF pump: {e}"
            
            # Log status every check (even if no change)
            status = "ON" if self.state.pump_active else "OFF"
            self.logger.debug(f"Buffer pump {status}: Konrad={konrad_temp:.1f}°C, Michael={michael_temp:.1f}°C, Diff={temp_difference:.1f}°C")
                
        except Exception as e:
            self.logger.error(f"Error in temperature check: {e}")
            self.state.error_message = f"Control error: {e}"
    
    def get_state(self) -> Dict:
        """Get current controller state"""
        temp_difference = self.state.konrad_temp - self.state.michael_temp
        
        # Add hardware diagnostics
        hardware_status = "unknown"
        if hasattr(self.hardware, 'boards') and hasattr(self.hardware, 'port_mapping'):
            if self.pump_port in self.hardware.port_mapping:
                board, port = self.hardware.port_mapping[self.pump_port]
                if hasattr(self.hardware, 'boards') and board < len(self.hardware.boards):
                    board_available = self.hardware.boards[board] is not None
                    hardware_status = f"Board {board}: {'OK' if board_available else 'FAILED'}"
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