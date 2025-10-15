#!/usr/bin/env python3
"""
Simple Mixer Controller - Simplified logic for reliable mixer control
"""

import time
import logging
import threading
from typing import Dict, Optional
from dataclasses import dataclass
from datetime import datetime
from config import HeatingConfig
from hardware import HeatingHardware
from sensors import SensorManager

@dataclass
class MixerState:
    """Simple mixer state"""
    current_temperature: float = 0.0
    target_temperature: float = 0.0
    max_temperature: float = 0.0
    last_action: str = "none"  # "open", "close", "none"
    last_action_time: datetime = None
    error_message: Optional[str] = None

class MixerController:
    """Simplified mixer controller with basic on/off logic"""
    
    def __init__(self, mixer_id: str, config: dict, hardware: HeatingHardware, 
                 sensor_manager: SensorManager, logger: logging.Logger):
        self.mixer_id = mixer_id
        self.hardware = hardware
        self.sensor_manager = sensor_manager
        self.logger = logger
        
        # Configuration
        self.temperature_sensor = config['sensor']
        self.max_temperature = config['max_temperature']
        self.auf_port = config['auf_port']  # Open port
        self.zu_port = config['zu_port']    # Close port
        
        # Simple control parameters - configurable from mixer config
        mixer_config = config.get('control_parameters', {})
        self.movement_duration = mixer_config.get('movement_duration', 2.0)       # Base movement duration (seconds)
        self.check_interval = mixer_config.get('check_interval', 15.0)            # Time between checks (seconds)
        self.temp_tolerance = mixer_config.get('temp_tolerance', 1.0)             # Temperature tolerance (°C)
        self.temp_threshold = mixer_config.get('temp_threshold', 3.0)             # Threshold for action (°C)
        self.dynamic_timing = mixer_config.get('dynamic_timing', True)            # Enable dynamic timing
        self.max_movement_duration = mixer_config.get('max_movement_duration', 10.0)  # Max movement time (seconds)
        self.safety_off_delay = mixer_config.get('safety_off_delay', 0.5)        # Delay after turning ports off (seconds)
        
        # State
        self.state = MixerState(
            max_temperature=self.max_temperature,
            last_action_time=datetime.now()
        )
        
        # Running flag
        self.running = False
        self.thread = None
        
        self.logger.info(f"Mixer controller initialized: {mixer_id}")
        self.logger.info(f"  Sensor: {self.temperature_sensor}")
        self.logger.info(f"  Max temp: {self.max_temperature}°C")
        self.logger.info(f"  Open port: {self.auf_port}")
        self.logger.info(f"  Close port: {self.zu_port}")
        self.logger.info(f"  Movement duration: {self.movement_duration}s (max: {self.max_movement_duration}s)")
        self.logger.info(f"  Check interval: {self.check_interval}s")
        self.logger.info(f"  Temp tolerance: {self.temp_tolerance}°C")
        self.logger.info(f"  Temp threshold: {self.temp_threshold}°C")
        self.logger.info(f"  Dynamic timing: {self.dynamic_timing}")
    
    def start(self):
        """Start the mixer control loop"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._control_loop, daemon=True)
        self.thread.start()
        self.logger.info(f"Started mixer controller: {self.mixer_id}")
    
    def stop(self):
        """Stop the mixer control loop"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        self.logger.info(f"Stopped mixer controller: {self.mixer_id}")
    
    def _control_loop(self):
        """Main control loop - runs continuously"""
        self.logger.info(f"Mixer {self.mixer_id}: Starting control loop")
        
        while self.running:
            try:
                # Step 1: Check temperature
                self._update_temperature()
                
                # Step 2: Determine action needed
                action = self._determine_action()
                
                # Step 3: Execute action if needed
                if action != "none":
                    self._execute_action(action)
                
                # Step 4: Wait for next cycle
                time.sleep(self.check_interval)
                
            except Exception as e:
                self.logger.error(f"Mixer {self.mixer_id} control loop error: {e}")
                self.state.error_message = str(e)
                time.sleep(self.check_interval)  # Continue despite errors
    
    def _update_temperature(self):
        """Update current temperature reading"""
        try:
            temps = self.sensor_manager.get_valid_temperatures()
            
            if self.temperature_sensor in temps:
                self.state.current_temperature = temps[self.temperature_sensor]
                self.state.target_temperature = self.max_temperature
                self.state.error_message = None
                
                self.logger.debug(f"Mixer {self.mixer_id}: Temp {self.state.current_temperature}°C → {self.state.target_temperature}°C")
            else:
                self.state.error_message = f"Sensor {self.temperature_sensor} not available"
                self.logger.warning(f"Mixer {self.mixer_id}: {self.state.error_message}")
                
        except Exception as e:
            self.state.error_message = f"Temperature read error: {e}"
            self.logger.error(f"Mixer {self.mixer_id}: {self.state.error_message}")
    
    def _determine_action(self):
        """Determine what action to take based on temperature"""
        if self.state.error_message:
            return "none"  # Don't move if we have sensor errors
        
        temp_diff = self.state.current_temperature - self.state.target_temperature
        
        # Use configurable threshold for action decision
        if temp_diff > self.temp_threshold:
            # Too hot - need to close mixer (reduce flow)
            return "close"
        elif temp_diff < -self.temp_threshold:
            # Too cold - need to open mixer (increase flow)
            return "open"
        else:
            # Temperature within acceptable range
            return "none"
    
    def _execute_action(self, action: str):
        """Execute mixer movement action with safety and dynamic timing"""
        try:
            if action == "open":
                port_on = self.auf_port
                port_off = self.zu_port
            elif action == "close":
                port_on = self.zu_port
                port_off = self.auf_port
            else:
                return
            
            # Calculate dynamic movement duration based on temperature difference
            temp_diff = abs(self.state.current_temperature - self.state.target_temperature)
            movement_duration = self.movement_duration
            
            if self.dynamic_timing and temp_diff > 10.0:
                # Increase movement time for large temperature differences
                # For every 5°C above 10°C, add 1 second (up to max)
                extra_time = (temp_diff - 10.0) / 5.0
                movement_duration = min(self.movement_duration + extra_time, self.max_movement_duration)
                self.logger.debug(f"Mixer {self.mixer_id}: Large temp diff ({temp_diff:.1f}°C), "
                                f"extending movement to {movement_duration:.1f}s")
            
            self.logger.info(f"Mixer {self.mixer_id}: {action.upper()} for {movement_duration:.1f}s "
                           f"(temp: {self.state.current_temperature:.1f}°C → {self.state.target_temperature:.1f}°C, "
                           f"diff: {temp_diff:+.1f}°C)")
            
            # SAFETY: First turn off BOTH ports to ensure no conflicts
            self.logger.debug(f"Mixer {self.mixer_id}: Safety - turning off both ports first")
            self.hardware.set_output(self.auf_port, False)  # Open port OFF
            self.hardware.set_output(self.zu_port, False)   # Close port OFF
            time.sleep(self.safety_off_delay)  # Safety delay
            
            # Now turn on the desired direction
            self.logger.debug(f"Mixer {self.mixer_id}: Activating {action} port: {port_on}")
            self.hardware.set_output(port_on, True)
            time.sleep(movement_duration)
            
            # Turn off movement
            self.logger.debug(f"Mixer {self.mixer_id}: Deactivating {action} port: {port_on}")
            self.hardware.set_output(port_on, False)
            
            # Update state
            self.state.last_action = action
            self.state.last_action_time = datetime.now()
            
            self.logger.info(f"Mixer {self.mixer_id}: {action.upper()} completed "
                           f"(moved for {movement_duration:.1f}s)")
            
        except Exception as e:
            self.logger.error(f"Mixer {self.mixer_id}: Action {action} failed: {e}")
            self.state.error_message = f"Movement error: {e}"
            
            # Safety: Turn off all ports on error
            try:
                self.hardware.set_output(self.auf_port, False)
                self.hardware.set_output(self.zu_port, False)
            except:
                pass  # Ignore secondary errors
    
    def get_state(self) -> Dict:
        """Get current mixer state"""
        temp_diff = self.state.current_temperature - self.state.target_temperature
        return {
            'mixer_id': self.mixer_id,
            'current_temperature': self.state.current_temperature,
            'target_temperature': self.state.target_temperature,
            'max_temperature': self.state.max_temperature,
            'temperature_difference': temp_diff,
            'last_action': self.state.last_action,
            'last_action_time': self.state.last_action_time.isoformat() if self.state.last_action_time else None,
            'error_message': self.state.error_message,
            'running': self.running,
            'settings': {
                'temp_threshold': self.temp_threshold,
                'movement_duration': self.movement_duration,
                'max_movement_duration': self.max_movement_duration,
                'check_interval': self.check_interval,
                'dynamic_timing': self.dynamic_timing
            }
        }

class MixerManager:
    """Simple mixer manager"""
    
    def __init__(self, config: HeatingConfig, hardware: HeatingHardware, 
                 sensor_manager: SensorManager):
        self.config = config
        self.hardware = hardware
        self.sensor_manager = sensor_manager
        self.logger = logging.getLogger("mixers")
        
        # Initialize controllers
        self.mixers: Dict[str, MixerController] = {}
        self._initialize_mixers()
    
    def _initialize_mixers(self):
        """Initialize simple mixer controllers"""
        if not hasattr(self.config, 'mixers') or not hasattr(self.config.mixers, 'mixer_controllers'):
            self.logger.warning("No mixer configuration found")
            return
        
        # Get global control parameters
        global_control_params = {}
        if hasattr(self.config.mixers, 'control_parameters'):
            global_control_params = self.config.mixers.control_parameters
        
        for mixer_id, mixer_config in self.config.mixers.mixer_controllers.items():
            try:
                # Merge global and mixer-specific config
                config_dict = dict(mixer_config)
                config_dict['control_parameters'] = global_control_params
                
                controller = MixerController(
                    mixer_id=mixer_id,
                    config=config_dict,
                    hardware=self.hardware,
                    sensor_manager=self.sensor_manager,
                    logger=self.logger
                )
                self.mixers[mixer_id] = controller
                self.logger.info(f"Initialized mixer: {mixer_id}")
            except Exception as e:
                self.logger.error(f"Failed to initialize mixer {mixer_id}: {e}")
    
    def start_all(self):
        """Start all mixer controllers"""
        for mixer_id, controller in self.mixers.items():
            controller.start()
        self.logger.info(f"Started {len(self.mixers)} mixer controllers")
    
    def stop_all(self):
        """Stop all mixer controllers"""
        for mixer_id, controller in self.mixers.items():
            controller.stop()
        self.logger.info("Stopped all mixer controllers")
    
    def get_states(self) -> Dict:
        """Get states of all mixers"""
        return {
            mixer_id: controller.get_state()
            for mixer_id, controller in self.mixers.items()
        }
    
    def check_and_restart_threads(self) -> Dict[str, bool]:
        """Check health of all mixer threads and restart if needed
        
        Returns:
            Dict mapping mixer_id to whether it was restarted (True) or healthy (False)
        """
        restart_status = {}
        
        for mixer_id, controller in self.mixers.items():
            restarted = False
            try:
                if controller.running and (
                    not controller.thread or 
                    not controller.thread.is_alive()
                ):
                    self.logger.warning(f"🔄 Mixer controller '{mixer_id}' thread died, restarting...")
                    try:
                        controller.stop()  # Clean stop
                        import time
                        time.sleep(1)
                        controller.start()  # Restart
                        self.logger.info(f"✅ Mixer controller '{mixer_id}' thread restarted successfully")
                        restarted = True
                    except Exception as e:
                        self.logger.error(f"❌ Failed to restart mixer controller '{mixer_id}': {e}")
                        restarted = False
            except Exception as e:
                self.logger.error(f"❌ Error checking mixer '{mixer_id}' thread: {e}")
                restarted = False
                
            restart_status[mixer_id] = restarted
            
        return restart_status