#!/usr/bin/env python3
"""
Buffer Loading Controller Module

Controls the buffer loading pump based on temperature differences between buffers.
Activates when Konrad's buffer is warmer than Michael's buffer to transfer heat.
"""

import logging
import threading
import time
from typing import Optional, Dict, Union, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from hardware import HeatingHardware
from sensors import SensorManager

@dataclass
class BufferLoadConfig:
    """Buffer loading pump configuration"""
    min_temperature_difference: float = 2.0  # Minimum temperature difference to start transfer
    hysteresis: float = 1.0                 # Hysteresis to prevent rapid cycling
    min_run_time: int = 60                  # Minimum pump run time in seconds
    min_off_time: int = 120                 # Minimum time pump stays off
    check_interval: int = 30                # How often to check temperatures
    source_sensor: str = "puffer_k_mitte"   # Source buffer sensor (Konrad)
    target_sensor: str = "puffer_m_mitte"   # Target buffer sensor (Michael)
    pump_port: Union[str, Tuple[int, int]] = "puffer_lade_pumpe"  # Port reference or (Board, Port) tuple

class BufferLoadController:
    """Controls buffer loading pump based on temperature differences"""
    
    def __init__(self, config: BufferLoadConfig, hardware: HeatingHardware, 
                 sensor_manager: SensorManager, logger: Optional[logging.Logger] = None):
        self.config = config
        self.hardware = hardware
        self.sensor_manager = sensor_manager
        self.logger = logger or logging.getLogger("buffer_load")
        
        self.is_pump_active = False
        self.last_state_change = datetime.now()
        self.last_check = datetime.now()
        self.error_state: Optional[str] = None
        self.last_temps: Dict[str, float] = {}
    
    def check_temperatures(self) -> tuple[Optional[float], Optional[float]]:
        """Read current temperatures from both buffers"""
        try:
            temps = self.sensor_manager.get_valid_temperatures()
            source_temp = temps.get(self.config.source_sensor)
            target_temp = temps.get(self.config.target_sensor)
            
            if source_temp is not None and target_temp is not None:
                self.last_temps = {
                    self.config.source_sensor: source_temp,
                    self.config.target_sensor: target_temp
                }
                self.error_state = None
                return source_temp, target_temp
            else:
                missing = []
                if source_temp is None:
                    missing.append(self.config.source_sensor)
                if target_temp is None:
                    missing.append(self.config.target_sensor)
                self.error_state = f"Missing temperature readings: {', '.join(missing)}"
                self.logger.warning(self.error_state)
                return None, None
                
        except Exception as e:
            self.error_state = f"Error reading temperatures: {e}"
            self.logger.error(self.error_state)
            return None, None
    
    def should_start_pump(self, source_temp: float, target_temp: float) -> bool:
        """Determine if pump should be started"""
        # Check temperature difference
        temp_diff = source_temp - target_temp
        
        if not self.is_pump_active:
            # When pump is off, need larger difference to start
            if temp_diff >= self.config.min_temperature_difference:
                # Check minimum off time
                time_off = (datetime.now() - self.last_state_change).total_seconds()
                return time_off >= self.config.min_off_time
        else:
            # When pump is running, use hysteresis for stop decision
            return temp_diff >= (self.config.min_temperature_difference - self.config.hysteresis)
        
        return False
    
    def should_stop_pump(self, source_temp: float, target_temp: float) -> bool:
        """Determine if pump should be stopped"""
        if not self.is_pump_active:
            return True
            
        # Check if minimum run time has elapsed
        run_time = (datetime.now() - self.last_state_change).total_seconds()
        if run_time < self.config.min_run_time:
            return False
            
        # Check temperature difference including hysteresis
        temp_diff = source_temp - target_temp
        return temp_diff < (self.config.min_temperature_difference - self.config.hysteresis)
    
    def start_pump(self) -> None:
        """Start the buffer loading pump"""
        try:
            if not self.is_pump_active:
                self.hardware.set_output(self.config.pump_port, True)
                self.is_pump_active = True
                self.last_state_change = datetime.now()
                self.logger.info(
                    "Buffer loading pump started. Temps: %s=%.1f°C, %s=%.1f°C", 
                    self.config.source_sensor, self.last_temps.get(self.config.source_sensor, 0),
                    self.config.target_sensor, self.last_temps.get(self.config.target_sensor, 0)
                )
        except Exception as e:
            self.error_state = f"Failed to start pump: {e}"
            self.logger.error(self.error_state)
    
    def stop_pump(self) -> None:
        """Stop the buffer loading pump"""
        try:
            if self.is_pump_active:
                self.hardware.set_output(self.config.pump_port, False)
                self.is_pump_active = False
                self.last_state_change = datetime.now()
                self.logger.info(
                    "Buffer loading pump stopped. Temps: %s=%.1f°C, %s=%.1f°C",
                    self.config.source_sensor, self.last_temps.get(self.config.source_sensor, 0),
                    self.config.target_sensor, self.last_temps.get(self.config.target_sensor, 0)
                )
        except Exception as e:
            self.error_state = f"Failed to stop pump: {e}"
            self.logger.error(self.error_state)
    
    def update(self) -> None:
        """Main update function - should be called regularly"""
        now = datetime.now()
        
        # Only check at configured interval
        if (now - self.last_check).total_seconds() < self.config.check_interval:
            return
        
        self.last_check = now
        
        try:
            # Get current temperatures
            source_temp, target_temp = self.check_temperatures()
            if source_temp is None or target_temp is None:
                self.stop_pump()  # Safety: stop pump if no valid readings
                return
            
            # Determine if pump state should change
            if self.is_pump_active:
                if self.should_stop_pump(source_temp, target_temp):
                    self.stop_pump()
            else:
                if self.should_start_pump(source_temp, target_temp):
                    self.start_pump()
                    
        except Exception as e:
            self.error_state = f"Error in buffer load controller update: {e}"
            self.logger.error(self.error_state)
            self.stop_pump()  # Safety: stop pump on error
    
    def get_state(self) -> Dict:
        """Get current controller state"""
        return {
            "is_pump_active": self.is_pump_active,
            "last_state_change": self.last_state_change.isoformat(),
            "error_state": self.error_state,
            "last_temperatures": self.last_temps,
            "source_sensor": self.config.source_sensor,
            "target_sensor": self.config.target_sensor
        }
    
    def update(self) -> bool:
        """
        Main update function - should be called regularly from main thread.
        Returns True if update was performed, False if skipped due to interval.
        """
        now = datetime.now()
        
        # Only check at configured interval
        if (now - self.last_check).total_seconds() < self.config.check_interval:
            return False  # Skip update, not enough time passed
        
        self.last_check = now
        
        try:
            # Get current temperatures
            source_temp, target_temp = self.check_temperatures()
            if source_temp is None or target_temp is None:
                self.stop_pump()  # Safety: stop pump if no valid readings
                return True
            
            # Determine if pump state should change
            if self.is_pump_active:
                if self.should_stop_pump(source_temp, target_temp):
                    self.stop_pump()
            else:
                if self.should_start_pump(source_temp, target_temp):
                    self.start_pump()
                    
            return True
                    
        except Exception as e:
            self.error_state = f"Error in buffer load controller update: {e}"
            self.logger.error(self.error_state)
            self.stop_pump()  # Safety: stop pump on error
            return True
    
    def get_update_interval(self) -> float:
        """Get the update interval in seconds"""
        return self.config.check_interval
    
    def dispose(self) -> None:
        """Clean up and shut down"""
        self.stop_pump()
        self.logger.info("Buffer load controller disposed")


def create_buffer_load_controller(config, hardware, sensor_manager, logger=None) -> BufferLoadController:
    """Factory function to create a buffer load controller"""
    
    buffer_config = BufferLoadConfig(
        min_temperature_difference=config.buffer_load.min_temperature_difference,
        hysteresis=config.buffer_load.hysteresis,
        min_run_time=config.buffer_load.min_run_time,
        min_off_time=config.buffer_load.min_off_time,
        check_interval=config.buffer_load.check_interval,
        source_sensor=config.buffer_load.source_sensor,
        target_sensor=config.buffer_load.target_sensor,
        pump_port=config.buffer_load.pump_port  # Use port reference as-is
    )
    
    return BufferLoadController(
        config=buffer_config,
        hardware=hardware,
        sensor_manager=sensor_manager,
        logger=logger
    )