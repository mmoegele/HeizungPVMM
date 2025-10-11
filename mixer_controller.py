#!/usr/bin/env python3
"""
Mixer Controller Module - Controls heating circuit mixers
"""

import time
import logging
import threading
from typing import Dict, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
from config import HeatingConfig
from hardware import HeatingHardware
from sensors import SensorManager

@dataclass
class MixerState:
    """Represents the current state of a mixer"""
    current_temperature: float
    target_temperature: float
    max_temperature: float
    is_pump_active: bool
    last_movement: datetime
    last_direction: Optional[str]  # 'open', 'close', or None
    error_state: Optional[str]
    last_temperature: float = 0.0  # Previous temperature reading
    temperature_trend: float = 0.0  # Rate of temperature change
    last_adjustment_time: datetime = datetime.now()  # Last time we made an adjustment
    consecutive_movements: int = 0  # Count of movements in same direction

class MixerController:
    """Controls individual heating circuit mixers"""
    
    @staticmethod
    def get_default_control_parameters() -> dict:
        """Get default control parameters if not specified in config"""
        return {
            'initial_check_interval': 5,
            'stable_check_interval': 20,
            'min_temp_difference': 1.0,
            'movement_duration': 1.0,
            'safety_delay': 1.0,
            'max_consecutive_movements': 3,
            'temperature_change_threshold': 0.1
        }

    def __init__(self, mixer_id: str, config: dict, hardware: HeatingHardware, 
                 sensor_manager: SensorManager, logger: logging.Logger):
        self.mixer_id = mixer_id
        self.config = config
        self.hardware = hardware
        self.sensor_manager = sensor_manager
        self.logger = logger
        
        # Extract configuration
        self.temperature_sensor = config['sensor']
        self.max_temperature = config['max_temperature']
        self.auf_port = config['auf_port']
        self.zu_port = config['zu_port']
        
        # Initialize state
        self.state = MixerState(
            current_temperature=0.0,
            target_temperature=0.0,
            max_temperature=self.max_temperature,
            is_pump_active=False,
            last_movement=datetime.now(),
            last_direction=None,
            error_state=None
        )
        
        # Control parameters from configuration
        control_params = self.config.get('control_parameters', {})
        if not control_params:
            # Use defaults if not configured
            control_params = self.get_default_control_parameters()
            self.logger.warning(f"No control parameters found for mixer {mixer_id}, using defaults")
        
        self.initial_check_interval = timedelta(seconds=control_params.get('initial_check_interval', 5))
        self.stable_check_interval = timedelta(seconds=control_params.get('stable_check_interval', 20))
        self.min_temp_difference = float(control_params.get('min_temp_difference', 1.0))
        self.movement_duration = float(control_params.get('movement_duration', 1.0))
        self.safety_delay = float(control_params.get('safety_delay', 1.0))
        self.max_consecutive_movements = int(control_params.get('max_consecutive_movements', 3))
        self.temperature_change_threshold = float(control_params.get('temperature_change_threshold', 0.1))
        
        self.logger.info(f"Initialized mixer controller for {mixer_id}")
    
    def update_state(self, target_temperature: float) -> None:
        """Update mixer state with current sensor readings and calculate trends"""
        try:
            temps = self.sensor_manager.get_valid_temperatures()
            if self.temperature_sensor in temps:
                current_temp = temps[self.temperature_sensor]
                
                # Calculate temperature trend
                if self.state.last_temperature != 0:
                    time_diff = (datetime.now() - self.state.last_adjustment_time).total_seconds()
                    if time_diff > 0:
                        self.state.temperature_trend = (
                            current_temp - self.state.last_temperature) / time_diff
                
                # Update state
                self.state.last_temperature = self.state.current_temperature
                self.state.current_temperature = current_temp
                self.state.target_temperature = target_temperature
                self.state.error_state = None
            else:
                self.state.error_state = f"Temperature sensor {self.temperature_sensor} not available"
                self.logger.error(self.state.error_state)
        except Exception as e:
            self.state.error_state = f"Error reading temperature: {e}"
            self.logger.error(self.state.error_state)
    
    def adjust_mixer(self) -> None:
        """Adjust mixer position based on current temperature and trends"""
        now = datetime.now()
        
        # Determine check interval based on stability
        check_interval = self.initial_check_interval if self.state.consecutive_movements > 0 \
            else self.stable_check_interval
        
        # Check if enough time has passed since last movement
        if (now - self.state.last_movement) < check_interval:
            return
        
        # Safety check
        if self.state.error_state:
            self.logger.warning(f"Skipping mixer adjustment due to error: {self.state.error_state}")
            return
        
        temp_difference = self.state.current_temperature - self.state.target_temperature
        
        # Reset consecutive movements if temperature is moving in right direction
        if self.state.temperature_trend != 0:
            if (temp_difference > 0 and self.state.temperature_trend < 0) or \
               (temp_difference < 0 and self.state.temperature_trend > 0):
                self.state.consecutive_movements = 0
                self.logger.debug(f"Temperature moving in correct direction, trend: {self.state.temperature_trend:0.3f}°C/s")
                return
        
        # Determine if adjustment is needed
        if abs(temp_difference) < self.min_temp_difference:
            self.state.consecutive_movements = 0
            return
        
        try:
            # Check if we've made too many adjustments in the same direction
            if self.state.consecutive_movements >= self.max_consecutive_movements:
                self.logger.warning(f"Maximum consecutive movements ({self.max_consecutive_movements}) reached")
                self.state.consecutive_movements = 0
                return
            
            # Determine direction
            if temp_difference > 0:
                # Too hot - close mixer
                if self.state.last_direction == 'open':
                    time.sleep(self.safety_delay)
                    self.state.consecutive_movements = 0
                self._move_mixer('close')
                self.state.consecutive_movements += 1
            else:
                # Too cold - open mixer
                if self.state.last_direction == 'close':
                    time.sleep(self.safety_delay)
                    self.state.consecutive_movements = 0
                self._move_mixer('open')
                self.state.consecutive_movements += 1
            
            self.state.last_movement = now
            self.state.last_adjustment_time = now
            
        except Exception as e:
            self.state.error_state = f"Mixer movement error: {e}"
            self.logger.error(self.state.error_state)
    
    def _move_mixer(self, direction: str) -> None:
        """Move mixer in specified direction"""
        if direction not in ('open', 'close'):
            raise ValueError(f"Invalid direction: {direction}")
        
        # Determine active and opposite ports
        active_port = self.auf_port if direction == 'open' else self.zu_port
        opposite_port = self.zu_port if direction == 'open' else self.auf_port
        
        try:
            # First ensure opposite direction is off
            self.hardware.set_output(opposite_port, False)
            # Small delay to ensure the relay has time to switch off
            time.sleep(0.1)
            
            # Activate movement in desired direction
            self.hardware.set_output(active_port, True)
            time.sleep(self.movement_duration)
            
            # Stop movement
            self.hardware.set_output(active_port, False)
            
            self.state.last_direction = direction
            self.logger.debug(f"Mixer {self.mixer_id} moved {direction}")
            
        except Exception as e:
            # Try to ensure both outputs are off in case of error
            try:
                self.hardware.set_output(active_port, False)
                self.hardware.set_output(opposite_port, False)
            except:
                pass
            raise RuntimeError(f"Failed to move mixer: {e}") from e
        
    def get_state(self) -> Dict:
        """Get current mixer state"""
        return {
            'mixer_id': self.mixer_id,
            'current_temperature': self.state.current_temperature,
            'target_temperature': self.state.target_temperature,
            'max_temperature': self.state.max_temperature,
            'is_pump_active': self.state.is_pump_active,
            'last_movement': self.state.last_movement.isoformat(),
            'last_direction': self.state.last_direction,
            'error_state': self.state.error_state
        }

class MixerManager:
    """Manages all heating circuit mixers"""
    
    def __init__(self, config: HeatingConfig, hardware: HeatingHardware, 
                 sensor_manager: SensorManager):
        self.config = config
        self.hardware = hardware
        self.sensor_manager = sensor_manager
        self.logger = logging.getLogger("mixers")
        
        # Initialize controllers
        self.mixers: Dict[str, MixerController] = {}
        self._initialize_mixers()
        
        # Control parameters
        self.pump_activation_temp = config.mixers.pump_activation_temperature
        self.temperature_tolerance = config.mixers.temperature_tolerance
        self.fixed_temp_mode = config.mixers.enable_fixed_temperature
        self.update_interval = getattr(config.mixers, 'update_interval', 5)  # Default 5 seconds
        self.last_update = datetime.now()
    
    def _initialize_mixers(self) -> None:
        """Initialize mixer controllers from configuration"""
        if not hasattr(self.config, 'mixers') or not hasattr(self.config.mixers, 'mixer_controllers'):
            self.logger.warning("No mixer configuration found")
            return
        
        for mixer_id, mixer_config in self.config.mixers.mixer_controllers.items():
            try:
                # Merge global control parameters with mixer-specific config
                mixer_config = dict(mixer_config)
                if hasattr(self.config.mixers, 'control_parameters'):
                    mixer_config['control_parameters'] = self.config.mixers.control_parameters
                
                controller = MixerController(
                    mixer_id=mixer_id,
                    config=mixer_config,
                    hardware=self.hardware,
                    sensor_manager=self.sensor_manager,
                    logger=self.logger
                )
                self.mixers[mixer_id] = controller
                self.logger.info("Initialized mixer controller: %s", mixer_id)
            except Exception as e:
                self.logger.error("Failed to initialize mixer %s: %s", mixer_id, str(e))
    
    def update(self) -> None:
        """Update all mixer controllers"""
        if not self.mixers:
            return
        
        try:
            # Get current temperatures
            temperatures = self.sensor_manager.get_valid_temperatures()
            if not temperatures:
                self.logger.warning("No valid temperature readings available")
                return
            
            # Update each mixer
            for mixer_id, controller in self.mixers.items():
                try:
                    # Calculate target temperature based on mode
                    if self.fixed_temp_mode:
                        target_temp = controller.config['max_temperature']
                    else:
                        # TODO: Implement variable temperature calculation based on outdoor temperature
                        target_temp = controller.config['max_temperature']
                    
                    # Update and adjust mixer
                    controller.update_state(target_temp)
                    controller.adjust_mixer()
                    
                except Exception as e:
                    self.logger.error("Error updating mixer %s: %s", mixer_id, str(e))
        
        except Exception as e:
            self.logger.error("Error in mixer update cycle: %s", str(e))
    
    def get_states(self) -> Dict:
        """Get states of all mixers"""
        states = {
            mixer_id: controller.get_state()
            for mixer_id, controller in self.mixers.items()
        }
        states['update_interval'] = self.update_interval
        return states
    
    def update(self) -> bool:
        """
        Update all mixer controllers.
        Returns True if update was performed, False if skipped due to interval.
        """
        now = datetime.now()
        
        # Check if enough time has passed since last update
        if (now - self.last_update).total_seconds() < self.update_interval:
            return False  # Skip update, not enough time passed
        
        self.last_update = now
        
        if not self.mixers:
            return True
        
        try:
            # Get current temperatures
            temperatures = self.sensor_manager.get_valid_temperatures()
            if not temperatures:
                self.logger.warning("No valid temperature readings available")
                return True
            
            # Update each mixer
            for mixer_id, controller in self.mixers.items():
                try:
                    # Calculate target temperature based on mode
                    if self.fixed_temp_mode:
                        target_temp = controller.config['max_temperature']
                    else:
                        # TODO: Implement variable temperature calculation based on outdoor temperature
                        target_temp = controller.config['max_temperature']
                    
                    # Update and adjust mixer
                    controller.update_state(target_temp)
                    controller.adjust_mixer()
                    
                except Exception as e:
                    self.logger.error("Error updating mixer %s: %s", mixer_id, str(e))
            
            return True
        
        except Exception as e:
            self.logger.error("Error in mixer update cycle: %s", str(e))
            return True
    
    def get_update_interval(self) -> float:
        """Get the update interval in seconds"""
        return self.update_interval
        
    def dispose(self) -> None:
        """Clean up and shut down"""
        pass  # No cleanup needed

# For testing
if __name__ == "__main__":
    import json
    # HeatingConfig already imported
    
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("test")
    
    try:
        # Load configuration
        config = HeatingConfig.from_yaml("heating_config.yaml")
        
        # Create mock hardware and sensor manager for testing
        class MockHardware:
            def set_output(self, port, value):
                print(f"Setting {port} to {value}")
        
        class MockSensorManager:
            def get_valid_temperatures(self):
                return {
                    "mischer_fussboden": 25.0,
                    "mischer_heizung": 40.0
                }
        
        # Initialize mixer manager
        mixer_manager = MixerManager(
            config=config,
            hardware=MockHardware(),
            sensor_manager=MockSensorManager()
        )
        
        # Test update cycle
        mixer_manager.update()
        
        # Print states
        states = mixer_manager.get_states()
        print("\nMixer States:")
        print(json.dumps(states, indent=2))
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
    else:
        logger.info("Test completed successfully")