#!/usr/bin/env python3
"""
Heat Exchanger Cooling Controller Module

Heat exchanger cooling operation - more runtime = more cooling:
1. Above target by >10°C -> Continuous cooling (too hot, run permanently) 
2. Above target (0 to +10°C) -> High duty PWM cooling (40-85% duty)
3. Below target (0 to -10°C) -> Low duty PWM cooling (5-20% duty)
4. Below target by >10°C -> No cooling (turn off completely)
5. Self-managed threading and automatic timing calculation

Heat exchanger cooling control:
- Delta = current_temp - target_temp  
- Above +10°C: Continuous cooling (100% duty) - TOO HOT
- Above 0°C: High duty cooling (40-85%) to bring temperature down
- Below 0°C: Low duty cooling (5-20%) to prevent overcooling  
- Below -10°C: No cooling (0% duty) - TOO COLD, let temperature rise
- Dynamic PWM switching: 1-4 second cycles with minimum 0.5s ON/OFF for pump reliability

Creates intelligent cooling control that cools more when hot and less when cold.
"""

import time
import logging
import threading
from typing import Optional, Dict
from datetime import datetime
from dataclasses import dataclass
from hardware import HeatingHardware
from sensors import SensorManager

@dataclass
class HeatExchangerState:
    """Heat exchanger state with PWM control"""
    current_temp: float = 0.0
    target_temp: float = 65.0
    temp_difference: float = 0.0
    pump_active: bool = False
    operation_mode: str = "off"  # "off", "continuous", "pwm", "safety", "bhkw_inactive"
    last_action: str = "none"
    last_check_time: datetime = None
    error_message: Optional[str] = None
    # BHKW status
    bhkw_active: bool = False
    # PWM control state
    current_pump_on_time: float = 0.0
    current_pump_off_time: float = 0.0
    duty_cycle_percent: float = 0.0
    pwm_frequency: float = 0.0  # Hz

# Note: Configuration is now passed as dict - no need for separate config class with PWM

class HeatExchangerController:
    """
    Heat Exchanger Cooling Controller with Self-Managed Threading
    
    Heat exchanger operates as COOLER - more runtime = more cooling:
    - Above target → Run more to cool down (higher duty cycles or continuous)
    - Below target → Run less to let temperature rise (lower duty cycles)
    - Far above target → Continuous operation for maximum cooling
    - Sensor errors: Pump ON for safety
    
    Cooling-based PWM provides intelligent control:
    - Above target: High duty cycles (55-85%) or continuous cooling
    - Near target: Balanced duty cycles (40%) for maintenance  
    - Below target: Low duty cycles (10-25%) to reduce cooling effect
    - Dynamic PWM switching: 1-4 second cycles with minimum 0.5s ON/OFF for pump reliability
    """
    
    def __init__(self, config: Dict, hardware: HeatingHardware, 
                 sensor_manager: SensorManager, logger: Optional[logging.Logger] = None):
        """Initialize the simplified heat exchanger controller"""
        self.logger = logger or logging.getLogger("heat_exchanger")
        self.hardware = hardware
        self.sensor_manager = sensor_manager
        
        # Rate limiting for log messages
        self._last_log_times = {}
        self._log_throttle_seconds = 30  # Only log similar messages every 30 seconds
        self._last_logged_state = {}  # Track last logged states
        
        # Configuration
        self.target_temp = config.get('target_temperature', 65.0)
        self.continuous_threshold = config.get('continuous_threshold', 10.0)  
        self.update_interval = config.get('update_interval', 5.0)
        self.pump_port = config.get('pump_port', 'wt_pumpe')
        self.temp_sensor = config.get('temperature_sensor', 'bhkw_vorlauf')
        
        # BHKW detection configuration
        self.bhkw_status_input = config.get('bhkw_status_input', 'bhkw_running_status')  # Input name to read BHKW status
        self.bhkw_temp_threshold = config.get('bhkw_temp_threshold', 30.0)  # Backup: Min temp to consider BHKW active
        self.require_bhkw_active = config.get('require_bhkw_active', True)  # Whether to require BHKW to be running
        
        # State
        self.state = HeatExchangerState(target_temp=self.target_temp)
        self.running = False
        self.thread = None
        
        # Interval mode timing
        self.last_pump_action = datetime.now()
        self.interval_pump_should_be_on = False
        
        # PWM control - Dynamic frequency for normal pump operation
        self.base_frequency = 1.0  # 1 Hz = 1 second base cycles, dynamically adjusted
        self.minimum_on_time = config.get('minimum_on_time', 0.5)  # Minimum 0.5 seconds ON
        self.minimum_off_time = config.get('minimum_off_time', 0.5)  # Minimum 0.5 seconds OFF
        self.minimum_duty_when_bhkw_running = config.get('minimum_duty_when_bhkw_running', 15.0)  # Minimum duty cycle when BHKW is active
    
    def _log_throttled(self, level: str, message: str, throttle_key: str):
        """Log message with throttling to prevent spam"""
        import time
        
        now = time.time()
        last_log_time = self._last_log_times.get(throttle_key, 0)
        
        if now - last_log_time >= self._log_throttle_seconds:
            self._last_log_times[throttle_key] = now
            getattr(self.logger, level)(message)
    
    def _is_bhkw_active(self) -> bool:
        """Check if BHKW is currently active using digital input port"""
        try:
            # Read BHKW status from digital input by name
            try:
                bhkw_input_state = self.hardware.get_input_by_name(self.bhkw_status_input)
                
                # Debug logging occasionally
                if not hasattr(self, '_bhkw_debug_counter'):
                    self._bhkw_debug_counter = 0
                self._bhkw_debug_counter += 1
                
                if self._bhkw_debug_counter % 20 == 0:  # Every 20 checks
                    self.logger.debug(f"BHKW status input '{self.bhkw_status_input}': {'ACTIVE' if bhkw_input_state else 'INACTIVE'}")
                
                return bhkw_input_state
                    
            except Exception as e:
                self.logger.warning(f"Could not read BHKW status input '{self.bhkw_status_input}': {e}")
                # Fallback to temperature method
                return self._check_bhkw_by_temperature()
            
        except Exception as e:
            self.logger.error(f"Error checking BHKW status: {e}")
            # Default to False for safety (don't run heat exchanger if unsure)
            return False
    
    def _check_bhkw_by_temperature(self) -> bool:
        """Fallback method: Check BHKW status by temperature threshold"""
        try:
            current_temp = self._read_temperature()
            if current_temp is not None and current_temp > self.bhkw_temp_threshold:
                return True
            return False
        except Exception as e:
            self.logger.debug(f"Error checking BHKW by temperature: {e}")
            return False
    
    def get_sensor_diagnostics(self) -> Dict:
        """Get sensor diagnostics information"""
        try:
            temps = self.sensor_manager.get_valid_temperatures()
            available_sensors = list(temps.keys())
            
            diagnostics = {
                'target_sensor': self.temp_sensor,
                'sensor_available': self.temp_sensor in temps,
                'available_sensors': available_sensors,
                'sensor_count': len(available_sensors)
            }
            
            if self.temp_sensor in temps:
                temp_value = temps[self.temp_sensor]
                diagnostics['sensor_value'] = temp_value
                diagnostics['sensor_valid'] = temp_value is not None and 0 <= temp_value <= 150
            
            # Add BHKW input status diagnostics
            try:
                bhkw_input_state = self.hardware.get_input_by_name(self.bhkw_status_input)
                diagnostics['bhkw_input'] = {
                    'name': self.bhkw_status_input,
                    'state': bhkw_input_state,
                    'active': bhkw_input_state
                }
            except Exception as e:
                diagnostics['bhkw_input'] = {
                    'name': self.bhkw_status_input,
                    'error': str(e),
                    'state': None
                }
            
            return diagnostics
            
        except Exception as e:
            return {
                'target_sensor': self.temp_sensor,
                'error': str(e),
                'sensor_available': False,
                'available_sensors': [],
                'bhkw_input': {'error': str(e)}
            }
    
    def start(self):
        """Start the heat exchanger control loop"""
        if self.running:
            self.logger.warning("Heat exchanger already running")
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._control_loop, daemon=True)
        self.thread.start()
        self.logger.info("🚀 Heat exchanger controller started")
    
    def stop(self):
        """Stop the heat exchanger control loop"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        # Turn off pump when stopping
        self._set_pump(False)
        self.logger.info("🛑 Heat exchanger controller stopped")
    
    def _read_temperature(self) -> Optional[float]:
        """Read current temperature from sensor with detailed error reporting"""
        try:
            temps = self.sensor_manager.get_valid_temperatures()
            
            # Debug: Show available sensors occasionally
            if not hasattr(self, '_sensor_debug_counter'):
                self._sensor_debug_counter = 0
            self._sensor_debug_counter += 1
            
            if self._sensor_debug_counter % 100 == 0:  # Every 100 calls
                available_sensors = list(temps.keys())
                self.logger.debug(f"Available temperature sensors: {available_sensors}")
            
            if self.temp_sensor in temps:
                temp = temps[self.temp_sensor]
                if temp is not None and 0 <= temp <= 150:  # Valid temperature range
                    return temp
                else:
                    # Throttled logging for invalid temperature readings
                    self._log_throttled("warning", f"Invalid temperature reading from '{self.temp_sensor}': {temp} (expected 0-150°C)", "invalid_temp")
                    return None
            else:
                # Throttled logging for missing sensors - provide available sensors info
                available_sensors = list(temps.keys()) if temps else []
                self._log_throttled("warning", f"Temperature sensor '{self.temp_sensor}' not available. Available sensors: {available_sensors}", "missing_sensor")
                return None
        except Exception as e:
            self.logger.error(f"Error reading temperature from sensor manager: {e}")
            return None
    
    def _set_pump(self, state: bool):
        """Set pump state with error handling"""
        try:
            if state != self.state.pump_active:
                self.hardware.set_output(self.pump_port, state)
                self.state.pump_active = state
                action = "ON" if state else "OFF"
                self.state.last_action = f"pump_{action.lower()}"
                # Reduced logging: only log pump changes at debug level
                self.logger.debug(f"💧 Heat exchanger pump: {action}")
        except Exception as e:
            self.logger.error(f"❌ Failed to set pump {state}: {e}")
            self.state.error_message = f"Pump control error: {e}"
    
    def _calculate_adaptive_pwm_duty_cycle(self, current_temp: float) -> tuple[float, float, float]:
        """Calculate adaptive PWM duty cycle for heat exchanger COOLING operation
        
        Heat Exchanger Cooling Logic (more runtime = more cooling):
        - Above target: Run more to cool down (higher duty cycles)
        - Below target: Run less to let temperature rise (lower duty cycles) 
        - Far above target: Continuous cooling to bring temperature down quickly
        
        Control Strategy:
        - Above target (> +10°C): Continuous cooling operation
        - Above target (0 to +10°C): High duty cycles for cooling
        - Below target (0 to -10°C): Low duty cycles to reduce cooling
        - Far below target (< -10°C): Minimal or no cooling
        
        Returns:
            tuple: (duty_cycle_percent, cycle_time_seconds, pump_on_time_seconds)
        """
        target_temp = self.target_temp
        temp_delta = current_temp - target_temp  # Positive = above target, Negative = below target
        
        # Implement cooling logic similar to old wtcontroller
        # When temperature is HIGH → pump runs MORE (more cooling)
        # When temperature is LOW → pump runs LESS (less cooling, let temp rise)
        
        # If temperature is way above target: Continuous cooling
        if current_temp > target_temp + 15.0:  # e.g., >75°C when target is 60°C
            self._log_throttled("warning", f"🔥 Too hot: {current_temp:.1f}°C - Continuous cooling", "too_hot")
            return 100.0, 0.0, 0.0  # Continuous cooling
        
        # If temperature is at or below target: Run minimum cooling when BHKW is active
        elif current_temp <= target_temp:  # e.g., ≤60°C
            self._log_throttled("info", f"❄️ At target: {current_temp:.1f}°C ≤ {target_temp:.1f}°C - Minimum cooling (BHKW running)", "at_target")
            return self.minimum_duty_when_bhkw_running, 0.0, 0.0  # Minimum cooling to keep BHKW heat under control
        
        # Temperature is above target but not extreme: Calculate proportional cooling
        else:
            temp_excess = current_temp - target_temp  # How much above target
            max_temp_range = 15.0  # Maximum temperature range for scaling (15°C above target)
            
            # Calculate duty cycle: more excess = higher duty cycle (more cooling)
            duty_factor = min(temp_excess / max_temp_range, 1.0)  # 0.0 to 1.0
            
            # Scale duty cycle from 20% to 95% based on temperature excess
            min_duty = 20.0  # Minimum cooling duty cycle
            max_duty = 95.0  # Maximum cooling duty cycle  
            duty_cycle = min_duty + (duty_factor * (max_duty - min_duty))
            
            # Round to reasonable increments
            if duty_cycle < 30:
                duty_cycle = 25.0   # Light cooling
            elif duty_cycle < 50:
                duty_cycle = 40.0   # Moderate cooling
            elif duty_cycle < 70:
                duty_cycle = 60.0   # Strong cooling
            elif duty_cycle < 85:
                duty_cycle = 80.0   # Very strong cooling
            else:
                duty_cycle = 90.0   # Maximum PWM cooling
        
        # Dynamic cycle timing based on temperature difference and duty cycle
        temp_delta = abs(current_temp - self.target_temp)
        
        # Base cycle time starts at 1 second, increases with temperature difference for stability
        if temp_delta <= 1.0:
            base_cycle_time = 1.0  # Fast response near target
        elif temp_delta <= 3.0:
            base_cycle_time = 2.0  # Moderate response for small differences
        elif temp_delta <= 5.0:
            base_cycle_time = 3.0  # Slower response for larger differences
        else:
            base_cycle_time = 4.0  # Slowest for very large differences (stability)
        
        pump_on_time = base_cycle_time * (duty_cycle / 100.0)
        pump_off_time = base_cycle_time - pump_on_time
        
        # Enforce absolute minimum timing for pump reliability (0.5s each)
        if pump_on_time > 0 and pump_on_time < self.minimum_on_time:
            pump_on_time = self.minimum_on_time
        if pump_off_time > 0 and pump_off_time < self.minimum_off_time:
            pump_off_time = self.minimum_off_time
            
        cycle_time = pump_on_time + pump_off_time
        
        return duty_cycle, cycle_time, pump_on_time
    
    def _determine_operation_mode(self, current_temp: float) -> str:
        """Determine operation mode for heat exchanger cooling operation"""
        target_temp = self.target_temp
        temp_delta = current_temp - target_temp
        
        # Above target by >10°C: Continuous cooling
        if temp_delta > 10.0:
            return "continuous"  # Too hot -> continuous cooling
        # Below target by >10°C: No cooling needed
        elif temp_delta < -10.0:
            return "off"  # Too cold -> turn off cooling completely
        # Within range: Use adaptive PWM
        else:
            return "adaptive_pwm"  # Use PWM for temperature control
    
    def _handle_adaptive_pwm_mode(self, current_temp: float):
        """Handle adaptive PWM with intelligent temperature targeting"""
        now = datetime.now()
        elapsed = (now - self.last_pump_action).total_seconds()
        
        # Get adaptive PWM parameters based on absolute temperature
        duty_cycle, cycle_time, pump_on_time = self._calculate_adaptive_pwm_duty_cycle(current_temp)
        
        # Handle special case of 0% duty cycle (no cooling needed)
        if duty_cycle == 0.0:
            # Turn off pump completely
            self._set_pump(False)
            self.state.current_pump_on_time = 0.0
            self.state.current_pump_off_time = 0.0
            self.state.duty_cycle_percent = 0.0
            self.state.pwm_frequency = 0.0
            return
            
        pump_off_time = cycle_time - pump_on_time
        
        # Store current PWM parameters in state for monitoring
        self.state.current_pump_on_time = pump_on_time
        self.state.current_pump_off_time = pump_off_time
        self.state.duty_cycle_percent = duty_cycle
        self.state.pwm_frequency = 1.0 / cycle_time if cycle_time > 0 else 0
        
        if self.interval_pump_should_be_on:
            # Pump should be ON, check if time to turn OFF
            if elapsed >= pump_on_time:
                self._set_pump(False)
                self.interval_pump_should_be_on = False
                self.last_pump_action = now
                # Reduce PWM logging frequency - only log every 10 cycles
                if hasattr(self, '_pwm_log_counter'):
                    self._pwm_log_counter += 1
                else:
                    self._pwm_log_counter = 0
                
                if self._pwm_log_counter % 10 == 0:  # Log every 10th cycle
                    temp_delta = current_temp - self.target_temp
                    cooling_action = "cooling" if duty_cycle > 40 else "minimal_cooling"
                    self.logger.debug(f"❄️ PWM Cooler: Pump OFF ({pump_on_time:.1f}s on, {duty_cycle:.0f}% duty, {cooling_action})")
        else:
            # Pump should be OFF, check if time to turn ON
            if elapsed >= pump_off_time:
                self._set_pump(True)
                self.interval_pump_should_be_on = True
                self.last_pump_action = now
                
                # Reduce PWM logging frequency - only log every 10 cycles  
                if hasattr(self, '_pwm_log_counter'):
                    self._pwm_log_counter += 1
                else:
                    self._pwm_log_counter = 0
                    
                if self._pwm_log_counter % 10 == 0:  # Log every 10th cycle
                    temp_delta = current_temp - self.target_temp
                    cooling_action = "cooling" if duty_cycle > 40 else "minimal_cooling"
                    self.logger.debug(f"❄️ PWM Cooler: Pump ON ({pump_off_time:.1f}s off, Δ{temp_delta:+.1f}°C, {duty_cycle:.0f}% {cooling_action})")
    
    def _control_loop(self):
        """Main control loop - runs in separate thread"""
        self.logger.debug("🔄 Heat exchanger control loop started")
        
        while self.running:
            try:
                # Update state timestamp
                self.state.last_check_time = datetime.now()
                self.state.error_message = None
                
                # Check BHKW status
                bhkw_active = self._is_bhkw_active() if self.require_bhkw_active else True
                self.state.bhkw_active = bhkw_active
                
                # If BHKW is not active and required, turn off pump and wait
                if self.require_bhkw_active and not bhkw_active:
                    if self.state.operation_mode != "bhkw_inactive":
                        self._log_throttled("info", "🔌 BHKW inactive - Heat exchanger paused", "bhkw_inactive")
                        self.state.operation_mode = "bhkw_inactive"
                        self._set_pump(False)
                    
                    # Continue loop but don't do temperature control
                    time.sleep(self.update_interval)
                    continue
                
                # BHKW is active, proceed with normal operation
                if self.state.operation_mode == "bhkw_inactive":
                    self._log_throttled("info", "🔌 BHKW active - Heat exchanger resumed", "bhkw_active")
                
                # Read current temperature
                current_temp = self._read_temperature()
                
                if current_temp is None:
                    # Sensor error - check if BHKW is actually running before safety mode
                    if bhkw_active and self.require_bhkw_active:
                        # BHKW is running but sensor failed - safety mode
                        self._log_throttled("warning", f"⚠️ Temperature sensor '{self.temp_sensor}' error while BHKW active - pump ON for safety", "sensor_error_bhkw_active")
                        self.state.operation_mode = "safety"
                        self.state.current_temp = 0.0
                        self.state.temp_difference = 0.0
                        self._set_pump(True)
                    else:
                        # BHKW not running or sensor issue - turn off pump
                        self._log_throttled("info", f"⚠️ Temperature sensor '{self.temp_sensor}' not available - pump OFF (BHKW not active)", "sensor_error_bhkw_inactive")
                        self.state.operation_mode = "sensor_error"
                        self.state.current_temp = 0.0
                        self.state.temp_difference = 0.0
                        self._set_pump(False)
                else:
                    # Valid temperature reading
                    self.state.current_temp = current_temp
                    self.state.temp_difference = abs(current_temp - self.target_temp)
                    
                    # Determine operation mode based on absolute temperature
                    operation_mode = self._determine_operation_mode(current_temp)
                    self.state.operation_mode = operation_mode
                    
                    # Calculate duty cycle for reporting
                    if self.state.current_pump_on_time > 0 and self.state.current_pump_off_time > 0:
                        total_cycle = self.state.current_pump_on_time + self.state.current_pump_off_time
                        self.state.duty_cycle_percent = (self.state.current_pump_on_time / total_cycle) * 100
                    else:
                        self.state.duty_cycle_percent = 100.0 if operation_mode == "continuous" else 0.0
                    
                    temp_delta = current_temp - self.target_temp
                    
                    if operation_mode == "continuous":
                        # Continuous operation for extreme hot conditions
                        self._set_pump(True)
                        self.state.current_pump_on_time = 0.0  # Continuous
                        self.state.current_pump_off_time = 0.0
                        self.state.pwm_frequency = 0.0
                        
                        # Throttled logging for continuous cooling status
                        self._log_throttled("debug", f"🔥 Continuous cooling: {current_temp:.1f}°C (too hot: +{temp_delta:.1f}°C)", "continuous_cooling")
                        
                    elif operation_mode == "off":
                        # Too cold - turn off cooling completely
                        self._set_pump(False)
                        self.state.current_pump_on_time = 0.0
                        self.state.current_pump_off_time = 0.0
                        self.state.pwm_frequency = 0.0
                        
                        # Throttled logging for cooling off status
                        self._log_throttled("debug", f"❄️ Cooling OFF: {current_temp:.1f}°C (too cold: {temp_delta:.1f}°C)", "cooling_off")
                        
                    elif operation_mode == "adaptive_pwm":
                        # Adaptive PWM mode for cooling control
                        self._handle_adaptive_pwm_mode(current_temp)
                        
                    else:
                        # Default fallback: turn off pump
                        self._set_pump(False)
                        self.state.current_pump_on_time = 0.0
                        self.state.current_pump_off_time = 0.0
                        self.state.pwm_frequency = 0.0
                
                # Wait before next check - responsive timing for dynamic PWM cycles
                if self.state.operation_mode == "adaptive_pwm":
                    # Use shorter interval for PWM timing precision (100ms for responsiveness)
                    time.sleep(0.1)  
                else:
                    # Normal interval for continuous/safety modes
                    time.sleep(self.update_interval)
                
            except Exception as e:
                self.logger.error(f"❌ Error in heat exchanger control loop: {e}")
                self.state.error_message = str(e)
                # Safety: turn pump ON during errors
                self._set_pump(True)
                time.sleep(self.update_interval)
        
        # Clean shutdown
        self._set_pump(False)
        self.logger.debug("🛑 Heat exchanger control loop stopped")
    
    def is_thread_healthy(self) -> bool:
        """Check if the heat exchanger thread is healthy and running properly"""
        if not self.running:
            return True  # Not supposed to be running, so it's "healthy"
        
        if self.thread is None:
            return False  # Should be running but no thread exists
            
        if not self.thread.is_alive():
            return False  # Thread exists but died
            
        return True  # Thread exists and is alive
    
    def get_thread_status(self) -> Dict:
        """Get detailed thread status information"""
        return {
            "running_flag": self.running,
            "thread_exists": self.thread is not None,
            "thread_alive": self.thread.is_alive() if self.thread else False,
            "thread_daemon": self.thread.daemon if self.thread else None,
            "thread_name": self.thread.name if self.thread else None,
            "thread_healthy": self.is_thread_healthy(),
            "needs_restart": self.running and (
                self.thread is None or not self.thread.is_alive()
            ),
            "last_check_time": self.state.last_check_time.isoformat() if self.state.last_check_time else None
        }
    
    def get_state(self) -> Dict:
        """Get current state information with PWM control and thread status details"""
        return {
            "running": self.running,
            "current_temp": self.state.current_temp,
            "target_temp": self.state.target_temp,
            "temp_difference": self.state.temp_difference,
            "pump_active": self.state.pump_active,
            "operation_mode": self.state.operation_mode,
            "last_action": self.state.last_action,
            "last_check": self.state.last_check_time.isoformat() if self.state.last_check_time else None,
            "error": self.state.error_message,
            "bhkw_active": self.state.bhkw_active,
            "require_bhkw": self.require_bhkw_active,
            "bhkw_detection": {
                "input_port": self.bhkw_status_input,
                "temp_threshold": self.bhkw_temp_threshold
            },
            "thread_status": {
                "thread_exists": self.thread is not None,
                "thread_alive": self.thread.is_alive() if self.thread else False,
                "thread_daemon": self.thread.daemon if self.thread else None,
                "thread_name": self.thread.name if self.thread else None,
                "should_be_running": self.running,
                "thread_healthy": (
                    self.thread is not None and 
                    self.thread.is_alive() and 
                    self.running
                ) if self.thread else False
            },
            "adaptive_pwm_control": {
                "base_frequency_hz": self.base_frequency,
                "current_frequency_hz": self.state.pwm_frequency,
                "duty_cycle_percent": self.state.duty_cycle_percent,
                "pump_on_time_seconds": self.state.current_pump_on_time,
                "pump_off_time_seconds": self.state.current_pump_off_time,
                "cycle_time_seconds": (self.state.current_pump_on_time + self.state.current_pump_off_time),
                "minimum_on_time": self.minimum_on_time,
                "minimum_off_time": self.minimum_off_time,
                "minimum_duty_when_bhkw_running": self.minimum_duty_when_bhkw_running,
                "temperature_delta": self.state.current_temp - self.state.target_temp,
                "overshoot_protection": self.state.current_temp > self.state.target_temp + 10.0
            },
            "thresholds": {
                "continuous": self.continuous_threshold
            },
            "sensor_diagnostics": self.get_sensor_diagnostics()
        }


def create_heat_exchanger_controller(config, hardware, sensor_manager, logger=None) -> HeatExchangerController:
    """Factory function to create a PWM heat exchanger controller"""
    
    # Extract configuration parameters with pump timing parameters
    heat_exchanger_config = {
        'target_temperature': getattr(config.heat_exchanger, 'target_temperature', 65.0),
        'continuous_threshold': getattr(config.heat_exchanger, 'continuous_threshold', 10.0),
        'update_interval': getattr(config.heat_exchanger, 'update_interval', 5.0),
        'pump_port': config.heat_exchanger.pump_port,
        'temperature_sensor': config.heat_exchanger.temperature_sensor,
        'minimum_on_time': getattr(config.heat_exchanger, 'minimum_on_time', 0.5),
        'minimum_off_time': getattr(config.heat_exchanger, 'minimum_off_time', 0.5),
        'minimum_duty_when_bhkw_running': getattr(config.heat_exchanger, 'minimum_duty_when_bhkw_running', 15.0)
    }
    
    return HeatExchangerController(
        config=heat_exchanger_config,
        hardware=hardware,
        sensor_manager=sensor_manager,
        logger=logger
    )