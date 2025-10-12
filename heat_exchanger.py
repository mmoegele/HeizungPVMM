#!/usr/bin/env python3
"""
Heat Exchanger Controller Module

Controls the heat exchanger pump based on BHKW temperature and configurable intervals.
Modern implementation of the original wtcontroller functionality.
"""

import time
import logging
import threading
from typing import Optional, Tuple, Union
from datetime import datetime, timedelta
from dataclasses import dataclass
from hardware import HeatingHardware
from sensors import SensorManager

@dataclass
class HeatExchangerConfig:
    """Heat exchanger configuration settings"""
    target_temperature: float = 65.0  # Target temperature (wtSollTemperatur)
    min_temperature: float = 50.0    # Minimum temperature (wtMinTemperatur)
    min_pump_interval: float = 0.15  # Minimum pump on time
    max_interval: float = 1.0       # Maximum interval between pump cycles (seconds)
    min_interval: float = 0.1       # Minimum interval between pump cycles (seconds)
    interval_multiplier: float = 1.5 # Multiplier for wait time between cycles
    control_interval: int = 10       # Read interval in seconds
    pump_port: Union[str, Tuple[int, int]] = "wt_pumpe"  # Port reference or (Board, Port) tuple
    temperature_sensor: str = "bhkw_vorlauf"  # Temperature sensor ID

class HeatExchangerController:
    """
    Controls heat exchanger pump based on BHKW temperature.
    Implements dynamic pump control with interval-based operation and safety features.
    
    Safety Features:
    - Enables pump on invalid temperature readings
    - Enables pump when temperature sensor is not available
    - Enables pump on any system errors or exceptions
    - Enables pump when temperature is outside valid range (0-150°C)
    
    This fail-safe behavior ensures continuous circulation in case of sensor
    or system failures, preventing potential overheating situations.
    """
    
    def __init__(self, config: HeatExchangerConfig, hardware: HeatingHardware, 
                 sensor_manager: SensorManager, logger: Optional[logging.Logger] = None):
        """Initialize the controller"""
        self.config = config
        self.hardware = hardware
        self.sensor_manager = sensor_manager
        self.logger = logger or logging.getLogger("heat_exchanger")
        
        self.last_temp_reading: Optional[float] = None
        self.last_temp_read_time = datetime.now()
        self.bhkw_status_count = 0
        self.is_pump_active = False
        self.last_state_change = datetime.now()
        self.last_update = datetime.now()
        self.config = config
        self.hardware = hardware
        self.sensor_manager = sensor_manager
        self.logger = logger or logging.getLogger("heat_exchanger")
        
        self.last_temp_reading: Optional[float] = None
        self.last_temp_read_time = datetime.now()
        self.bhkw_status_count = 0
        self.is_pump_active = False
        self.last_state_change = datetime.now()
    
    def read_bhkw_temperature(self) -> Optional[float]:
        """
        Read current BHKW temperature (uses sensor manager's caching).
        
        Returns:
            Optional[float]: The current temperature if valid, None if:
                - Temperature reading is invalid (< 0°C or > 150°C)
                - Temperature sensor is not available
                - Any error occurs during reading
                
        Safety:
            The pump will be automatically enabled in any error condition
            or when valid temperature cannot be obtained.
        """
        try:
            temps = self.sensor_manager.get_valid_temperatures()
            if self.config.temperature_sensor in temps:
                temp = temps[self.config.temperature_sensor]
                # Check for invalid temperature values
                if temp is None or not isinstance(temp, (int, float)) or temp < 0 or temp > 150:
                    self.logger.error(f"Invalid temperature reading: {temp}")
                    return None
                self.last_temp_reading = temp
                self.last_temp_read_time = datetime.now()
                return self.last_temp_reading
            else:
                self.logger.warning(f"Temperature sensor {self.config.temperature_sensor} not available")
                return None
        except Exception as e:
            self.logger.error(f"Error reading temperature: {e}")
            return None
    
    def calculate_interval(self, current_temp: float) -> float:
        """
        Calculate pump interval based on current temperature.
        
        The interval determines the wait time between pump cycles:
        - Below min_temperature: maximum interval (slower cycling)
        - At target_temperature: minimum interval (faster cycling)
        - In between: proportionally scaled interval
        
        Actual cycle timing:
        1. Pump runs for min_pump_interval (e.g., 0.15s)
        2. Waits for (calculated_interval * interval_multiplier) seconds
        3. Repeats
        
        Returns:
            float: Interval in seconds between pump cycles
        """
        temp_range = self.config.target_temperature - self.config.min_temperature
        if temp_range <= 0:
            self.logger.warning("Invalid temperature range configuration")
            return self.config.max_interval
        
        # Calculate relative position in temperature range
        interval = (current_temp - self.config.min_temperature) / temp_range
        
        # Apply control logic
        if interval < 0:
            # Below minimum temperature - use maximum interval
            return self.config.max_interval
        elif interval < 0.5:
            # In lower half of range - use medium interval
            return (self.config.max_interval + self.config.min_interval) / 2
        else:
            # In upper half of range - scale interval inversely with temperature
            scaled_interval = self.config.max_interval * (1.0 - interval)
            return max(self.config.min_interval, scaled_interval)
    
    def update_bhkw_status(self, is_running: bool) -> None:
        """Update BHKW running status"""
        if is_running:
            self.bhkw_status_count = 10
        else:
            self.bhkw_status_count = max(0, self.bhkw_status_count - 1)
    
    def is_bhkw_active(self) -> bool:
        """Check if BHKW is considered active"""
        return self.bhkw_status_count > 0
    
    def pump_on(self) -> None:
        """Turn pump on"""
        try:
            if not self.is_pump_active:
                self.hardware.set_output(self.config.pump_port, True)
                self.is_pump_active = True
                self.last_state_change = datetime.now()
                self.logger.debug("Heat exchanger pump turned ON")
        except Exception as e:
            self.logger.error(f"Failed to turn pump on: {e}")
    
    def pump_off(self) -> None:
        """Turn pump off"""
        try:
            if self.is_pump_active:
                self.hardware.set_output(self.config.pump_port, False)
                self.is_pump_active = False
                self.last_state_change = datetime.now()
                self.logger.debug("Heat exchanger pump turned OFF")
        except Exception as e:
            self.logger.error(f"Failed to turn pump off: {e}")
    
    def update(self) -> bool:
        """
        Update heat exchanger control logic.
        Returns True if update was performed, False if skipped due to interval.
        """
        now = datetime.now()
        
        # Check if enough time has passed since last update
        if (now - self.last_update).total_seconds() < self.config.control_interval:
            return False  # Skip update, not enough time passed
        
        self.last_update = now
        
        try:
            if not self.is_bhkw_active():
                self.pump_off()
                return True
            
            current_temp = self.read_bhkw_temperature()
            if current_temp is None:
                self.logger.warning("No temperature reading available or invalid temperature - enabling pump as safety measure")
                self.pump_on()  # Enable pump as safety measure when temperature is unknown
                return True
            
            interval = self.calculate_interval(current_temp)
            
            # If temperature is very low, run pump continuously
            if interval <= 0:
                self.pump_on()
                return True
            
            # Interval-based operation
            if self.is_pump_active:
                # Check if pump should be turned off
                if (now - self.last_state_change).total_seconds() >= self.config.min_pump_interval:
                    self.pump_off()
            else:
                # Check if pump should be turned on
                if (now - self.last_state_change).total_seconds() >= (interval * 1.5):
                    self.pump_on()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error in heat exchanger update: {e}")
            self.pump_off()  # Safety: turn off pump on error
            return True
    
    def get_state(self) -> dict:
        """Get current state information"""
        return {
            "is_pump_active": self.is_pump_active,
            "bhkw_active": self.is_bhkw_active(),
            "last_temperature": self.last_temp_reading,
            "target_temperature": self.config.target_temperature,
            "min_temperature": self.config.min_temperature,
            "last_state_change": self.last_state_change.isoformat(),
            "update_interval": self.config.control_interval
        }
    
    def get_update_interval(self) -> float:
        """Get the update interval in seconds"""
        return self.config.control_interval
    
    def dispose(self) -> None:
        """Clean up and shut down"""
        self.pump_off()
        self.logger.info("Heat exchanger controller disposed")


def create_heat_exchanger_controller(config, hardware, sensor_manager, logger=None) -> HeatExchangerController:
    """Factory function to create a heat exchanger controller"""
    
    heat_exchanger_config = HeatExchangerConfig(
        target_temperature=config.heat_exchanger.target_temperature,
        min_temperature=config.heat_exchanger.min_temperature,
        min_pump_interval=config.heat_exchanger.min_pump_interval,
        max_interval=getattr(config.heat_exchanger, 'max_interval', 1.0),
        min_interval=getattr(config.heat_exchanger, 'min_interval', 0.1),
        interval_multiplier=getattr(config.heat_exchanger, 'interval_multiplier', 1.5),
        control_interval=config.heat_exchanger.control_interval,
        pump_port=config.heat_exchanger.pump_port,  # Use port reference as-is
        temperature_sensor=config.heat_exchanger.temperature_sensor
    )
    
    return HeatExchangerController(
        config=heat_exchanger_config,
        hardware=hardware,
        sensor_manager=sensor_manager,
        logger=logger
    )