#!/usr/bin/env python3
"""
System Data Reporter
Reports temperature sensor data, power consumption, and equipment running hours to external API
"""

import time
import json
import uuid
import requests
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from config import HeatingConfig
from sensors import SensorManager

class SystemDataReporter:
    """Reports temperature sensor data, power consumption, and equipment running hours to external API"""
    
    def __init__(self, config: HeatingConfig, sensor_manager: SensorManager, hardware_controller,
                 api_url: str = "http://192.168.191.45:8080", 
                 report_interval: int = 30):
        """
        Initialize system data reporter
        
        Args:
            config: Heating system configuration
            sensor_manager: Sensor manager instance
            hardware_controller: Hardware controller for reading pump states
            api_url: Base URL of the API to report to
            report_interval: Check interval in seconds (not actual reporting interval)
        """
        self.config = config
        self.sensor_manager = sensor_manager
        self.hardware_controller = hardware_controller
        self.api_url = api_url.rstrip('/')
        self.report_interval = report_interval  # How often to check for changes
        self.logger = logging.getLogger("heating.system_data_reporter")
        
        # Change-based reporting configuration
        self.temperature_threshold = 2  # °C - minimum change to trigger report
        self.power_threshold = 500  # W - minimum power change to trigger report  
        self.force_report_interval = 15 * 60  # 15 minutes - force report even if no changes
        
        # Threading control
        self._stop_event = threading.Event()
        self._reporting_thread: Optional[threading.Thread] = None
        self._is_running = False
        
        # Statistics
        self.total_reports_sent = 0
        self.total_errors = 0
        self.last_report_time: Optional[datetime] = None
        self.last_error: Optional[str] = None
        
        # Last reported values for change detection
        self._last_reported_temperatures = {}  # sensor_id -> last_value
        self._last_reported_power = {}  # element_name -> last_power
        self._last_reported_pumps = {}  # pump_name -> last_state
        self._last_force_report_time = datetime.now()
        
        # Power and running state tracking
        self._heating_element_states = {}  # Track heating element on/off states
        self._pump_states = {}  # Track pump running states
        self._last_state_check = datetime.now()
        
        # Initialize power tracking for heating elements
        self._initialize_power_tracking()
        self._initialize_pump_tracking()
        
        self.logger.info(f"System data reporter initialized - API: {self.api_url}")
        self.logger.info(f"Change-based reporting: temp ±{self.temperature_threshold}°C, power ±{self.power_threshold}W, force every {self.force_report_interval/60:.0f}min")
        self.logger.info(f"Equipment tracking: {len(self._heating_element_states)} heating elements, {len(self._pump_states)} pumps")
    
    def _initialize_power_tracking(self) -> None:
        """Initialize tracking for heating elements power consumption"""
        try:
            self.logger.debug("Starting heating element power tracking initialization")
            self.logger.debug(f"Config type: {type(self.config)}")
            self.logger.debug(f"Config has hardware: {hasattr(self.config, 'hardware')}")
            
            # Get hardware outputs from hardware.outputs which contains the complete configuration
            if hasattr(self.config, 'hardware') and hasattr(self.config.hardware, 'outputs'):
                self.logger.debug(f"Found hardware.outputs with {len(self.config.hardware.outputs)} outputs")
                for output_name, output_config in self.config.hardware.outputs.items():
                    self.logger.debug(f"Checking output: {output_name}")
                    # Look for heating elements (heizstab)
                    if 'heizstab' in output_name.lower():
                        power_kw = output_config.get('power_kw', 2.0)
                        self._heating_element_states[output_name] = {
                            'is_on': False,
                            'power_kw': power_kw,
                            'board': output_config['board'],
                            'port': output_config['port'],
                            'uuid': output_config.get('uuid', str(uuid.uuid4())),
                            'description': output_config.get('description', output_name),
                            'last_state_change': datetime.now()
                        }
                        self.logger.debug(f"Added heating element tracking: {output_name}")
            else:
                self.logger.warning("No hardware.outputs configuration found")
                if hasattr(self.config, 'hardware'):
                    self.logger.debug(f"Hardware config exists but no outputs: {dir(self.config.hardware)}")
                else:
                    self.logger.debug("No hardware configuration found")
            
            self.logger.info(f"Initialized power tracking for {len(self._heating_element_states)} heating elements")
        except Exception as e:
            self.logger.error(f"Error initializing power tracking: {e}")
            self.logger.exception("Power tracking initialization error details:")
            raise
    
    def _initialize_pump_tracking(self) -> None:
        """Initialize tracking for pump running hours"""
        try:
            self.logger.debug("Starting pump tracking initialization")
            pump_names = ['puffer_lade_pumpe', 'wt_pumpe']
            
            if hasattr(self.config, 'hardware') and hasattr(self.config.hardware, 'outputs'):
                self.logger.debug(f"Looking for pumps in {len(self.config.hardware.outputs)} outputs: {list(self.config.hardware.outputs.keys())}")
                for pump_name in pump_names:
                    self.logger.debug(f"Looking for pump: {pump_name}")
                    if pump_name in self.config.hardware.outputs:
                        output_config = self.config.hardware.outputs[pump_name]
                        self._pump_states[pump_name] = {
                            'is_running': False,
                            'board': output_config['board'],
                            'port': output_config['port'],
                            'uuid': output_config.get('uuid', str(uuid.uuid4())),
                            'description': output_config.get('description', pump_name),
                            'last_state_change': datetime.now()
                        }
                        self.logger.debug(f"Added pump tracking: {pump_name}")
                    else:
                        self.logger.warning(f"Pump {pump_name} not found in hardware.outputs configuration")
            else:
                self.logger.warning("No hardware.outputs configuration found for pump tracking")
            
            self.logger.info(f"Initialized pump tracking for {len(self._pump_states)} pumps")
        except Exception as e:
            self.logger.error(f"Error initializing pump tracking: {e}")
            self.logger.exception("Pump tracking initialization error details:")
            raise
    
    def _update_equipment_states(self) -> None:
        """Update current states of heating elements and pumps"""
        try:
            current_time = datetime.now()
            
            # Update heating element states
            for element_name, element_data in self._heating_element_states.items():
                try:
                    board = element_data['board']
                    port = element_data['port']
                    current_state = self.hardware_controller.get_output(board, port)
                    
                    # Check for state change
                    if current_state != element_data['is_on']:
                        element_data['last_state_change'] = current_time
                        element_data['is_on'] = current_state
                        self.logger.debug(f"Heating element {element_name} state changed to {'ON' if current_state else 'OFF'}")
                        
                except Exception as e:
                    self.logger.error(f"Error reading heating element {element_name} state: {e}")
            
            # Update pump states
            for pump_name, pump_data in self._pump_states.items():
                try:
                    board = pump_data['board']
                    port = pump_data['port']
                    current_state = self.hardware_controller.get_output(board, port)
                    
                    # Check for state change
                    if current_state != pump_data['is_running']:
                        pump_data['last_state_change'] = current_time
                        pump_data['is_running'] = current_state
                        self.logger.debug(f"Pump {pump_name} state changed to {'RUNNING' if current_state else 'STOPPED'}")
                        
                except Exception as e:
                    self.logger.error(f"Error reading pump {pump_name} state: {e}")
            
            self._last_state_check = current_time
            
        except Exception as e:
            self.logger.error(f"Error updating equipment states: {e}")
    
    def start(self) -> None:
        """Start the system data reporting service"""
        if self._is_running:
            self.logger.warning("System data reporter is already running")
            return
        
        self._stop_event.clear()
        self._reporting_thread = threading.Thread(target=self._reporting_loop, daemon=True)
        self._reporting_thread.start()
        self._is_running = True
        self.logger.info("🚀 System data reporter thread started - beginning data collection and reporting")
    
    def stop(self) -> None:
        """Stop the system data reporting service"""
        if not self._is_running:
            self.logger.warning("System data reporter is not running")
            return
        
        self._stop_event.set()
        if self._reporting_thread and self._reporting_thread.is_alive():
            self._reporting_thread.join(timeout=5)
        self._is_running = False
        self.logger.info("🛑 System data reporter stopped")

    def _reporting_loop(self) -> None:
        """Main reporting loop that runs in a separate thread with change-based reporting"""
        self.logger.info(f"📊 System data reporting loop started - change-based reporting with {self.force_report_interval/60:.0f}min max interval")
        
        while not self._stop_event.is_set():
            try:
                # Update equipment states before checking for changes
                self._update_equipment_states()
                
                # Check if we need to send a report (changes detected or time elapsed)
                should_report, reasons = self._should_send_report()
                
                if should_report:
                    self.logger.info(f"Sending bulk update with changed devices: {', '.join(reasons)}")
                    # Collect and send only changed devices in bulk
                    changed_devices = self._collect_changed_devices()
                    if changed_devices:
                        self._send_bulk_update(changed_devices)
                        self._update_last_reported_values()
                    else:
                        self.logger.debug("No changed devices to send")
                else:
                    self.logger.debug("No significant changes detected - skipping report")
                
                # Wait for the next check interval
                self._stop_event.wait(self.report_interval)
                
            except Exception as e:
                self.logger.error(f"Error in reporting loop: {e}")
                self.total_errors += 1
                self.last_error = str(e)
                # Wait a bit before retrying to avoid rapid error loops
                self._stop_event.wait(min(self.report_interval, 10))
        
        self.logger.info("System data reporting loop ended")
    
    def _should_send_report(self) -> tuple[bool, list]:
        """
        Determine if a report should be sent based on changes and time elapsed
        
        Returns:
            Tuple of (should_send, list_of_reasons)
        """
        reasons = []
        current_time = datetime.now()
        
        # Check if force report time has elapsed (15 minutes)
        time_since_last_force = (current_time - self._last_force_report_time).total_seconds()
        if time_since_last_force >= self.force_report_interval:
            reasons.append(f"15min interval reached")
            self._last_force_report_time = current_time
            return True, reasons
        
        # Check temperature changes
        try:
            temperature_readings = self.sensor_manager.read_all_temperatures()
            for sensor_id, reading in temperature_readings.items():
                if reading.is_valid:
                    last_value = self._last_reported_temperatures.get(sensor_id)
                    if last_value is None:
                        reasons.append(f"new sensor {sensor_id}")
                    elif abs(reading.value - last_value) >= self.temperature_threshold:
                        reasons.append(f"temp {sensor_id} Δ{reading.value - last_value:+.1f}°C")
        except Exception as e:
            self.logger.error(f"Error checking temperature changes: {e}")
        
        # Check power changes (heating elements)
        for element_name, element_data in self._heating_element_states.items():
            current_power = element_data['power_kw'] * 1000 if element_data['is_on'] else 0.0
            last_power = self._last_reported_power.get(element_name)
            if last_power is None:
                reasons.append(f"new heating element {element_name}")
            elif abs(current_power - last_power) >= self.power_threshold:
                reasons.append(f"power {element_name} Δ{current_power - last_power:+.0f}W")
        
        # Check pump state changes
        for pump_name, pump_data in self._pump_states.items():
            current_state = 1 if pump_data['is_running'] else 0
            last_state = self._last_reported_pumps.get(pump_name)
            if last_state is None:
                reasons.append(f"new pump {pump_name}")
            elif current_state != last_state:
                state_text = "started" if current_state else "stopped"
                reasons.append(f"pump {pump_name} {state_text}")
        
        return len(reasons) > 0, reasons
    
    def _collect_changed_devices(self) -> List[Dict]:
        """
        Collect only devices that have changed beyond thresholds or are new
        
        Returns:
            List of device data dictionaries for devices that have changed
        """
        changed_devices = []
        current_time = datetime.now()
        
        # Check for changed temperatures
        try:
            temperature_readings = self.sensor_manager.read_all_temperatures()
            for sensor_id, reading in temperature_readings.items():
                if reading.is_valid:
                    last_value = self._last_reported_temperatures.get(sensor_id)
                    time_since_last_force = (current_time - self._last_force_report_time).total_seconds()
                    
                    # Include if: new sensor, significant change, or force report time
                    should_include = (
                        last_value is None or  # New sensor
                        abs(reading.value - last_value) >= self.temperature_threshold or  # Significant change
                        time_since_last_force >= self.force_report_interval  # Force report time
                    )
                    
                    if should_include:
                        sensor_config = self.config.sensor_paths.get(sensor_id, {})
                        device_name = sensor_config.get('description', sensor_id)
                        sensor_uuid = sensor_config.get('uuid', str(uuid.uuid4()))
                        
                        changed_devices.append({
                            "sensor_type": "temperature",
                            "value": reading.value,
                            "uuid": sensor_uuid,
                            "device_name": device_name
                        })
        except Exception as e:
            self.logger.error(f"Error collecting changed temperatures: {e}")
        
        # Check for changed heating elements
        for element_name, element_data in self._heating_element_states.items():
            current_power = element_data['power_kw'] * 1000 if element_data['is_on'] else 0.0
            last_power = self._last_reported_power.get(element_name)
            time_since_last_force = (current_time - self._last_force_report_time).total_seconds()
            
            # Include if: new element, significant change, or force report time
            should_include = (
                last_power is None or  # New element
                abs(current_power - last_power) >= self.power_threshold or  # Significant change
                time_since_last_force >= self.force_report_interval  # Force report time
            )
            
            if should_include:
                changed_devices.append({
                    "sensor_type": "power",
                    "value": current_power,
                    "uuid": element_data['uuid'],
                    "device_name": element_data['description']
                })
        
        # Check for changed pumps
        for pump_name, pump_data in self._pump_states.items():
            current_state = 1 if pump_data['is_running'] else 0
            last_state = self._last_reported_pumps.get(pump_name)
            time_since_last_force = (current_time - self._last_force_report_time).total_seconds()
            
            # Include if: new pump, state change, or force report time
            should_include = (
                last_state is None or  # New pump
                current_state != last_state or  # State change
                time_since_last_force >= self.force_report_interval  # Force report time
            )
            
            if should_include:
                changed_devices.append({
                    "sensor_type": "running_hours",
                    "value": current_state,
                    "uuid": pump_data['uuid'],
                    "device_name": pump_data['description']
                })
        
        return changed_devices
    
    def _send_bulk_update(self, changed_devices: List[Dict]) -> None:
        """
        Send bulk update with only changed devices
        
        Args:
            changed_devices: List of device data for devices that have changed
        """
        if not changed_devices:
            return
        
        try:
            # Create bulk submission payload with only changed devices
            bulk_data = {
                "batch_uuid": str(uuid.uuid4()),
                "data": changed_devices
            }
            
            # Send data to API with retry logic
            success = self._send_to_api_with_retry(bulk_data, max_retries=3)
            
            if success:
                self.total_reports_sent += 1
                self.last_report_time = datetime.now()
                device_count = len(changed_devices)
                device_types = {}
                for device in changed_devices:
                    device_type = device['sensor_type']
                    device_types[device_type] = device_types.get(device_type, 0) + 1
                
                type_summary = ", ".join([f"{count} {type}" for type, count in device_types.items()])
                self.logger.info(f"Successfully sent bulk update: {device_count} devices ({type_summary})")
            else:
                self.total_errors += 1
                
        except Exception as e:
            self.logger.error(f"Error sending bulk update: {e}")
            self.total_errors += 1
            self.last_error = str(e)
    
    def _collect_all_devices(self) -> List[Dict]:
        """
        Collect all devices for immediate/force reporting
        
        Returns:
            List of all device data dictionaries
        """
        all_devices = []
        
        # Get all temperatures
        try:
            temperature_readings = self.sensor_manager.read_all_temperatures()
            for sensor_id, reading in temperature_readings.items():
                if reading.is_valid:
                    sensor_config = self.config.sensor_paths.get(sensor_id, {})
                    device_name = sensor_config.get('description', sensor_id)
                    sensor_uuid = sensor_config.get('uuid', str(uuid.uuid4()))
                    
                    all_devices.append({
                        "sensor_type": "temperature",
                        "value": reading.value,
                        "uuid": sensor_uuid,
                        "device_name": device_name
                    })
        except Exception as e:
            self.logger.error(f"Error collecting all temperatures: {e}")
        
        # Get all heating elements
        for element_name, element_data in self._heating_element_states.items():
            current_power = element_data['power_kw'] * 1000 if element_data['is_on'] else 0.0
            all_devices.append({
                "sensor_type": "power",
                "value": current_power,
                "uuid": element_data['uuid'],
                "device_name": element_data['description']
            })
        
        # Get all pumps
        for pump_name, pump_data in self._pump_states.items():
            current_state = 1 if pump_data['is_running'] else 0
            all_devices.append({
                "sensor_type": "running_hours",
                "value": current_state,
                "uuid": pump_data['uuid'],
                "device_name": pump_data['description']
            })
        
        return all_devices
    
    def _update_last_reported_values(self) -> None:
        """Update the last reported values for devices that were actually sent"""
        try:
            current_time = datetime.now()
            
            # Only update if force report time was reached (all devices sent)
            time_since_last_force = (current_time - self._last_force_report_time).total_seconds()
            if time_since_last_force >= self.force_report_interval:
                self._last_force_report_time = current_time
                
                # Update all device values when force report occurs
                temperature_readings = self.sensor_manager.read_all_temperatures()
                for sensor_id, reading in temperature_readings.items():
                    if reading.is_valid:
                        self._last_reported_temperatures[sensor_id] = reading.value
                
                for element_name, element_data in self._heating_element_states.items():
                    current_power = element_data['power_kw'] * 1000 if element_data['is_on'] else 0.0
                    self._last_reported_power[element_name] = current_power
                
                for pump_name, pump_data in self._pump_states.items():
                    current_state = 1 if pump_data['is_running'] else 0
                    self._last_reported_pumps[pump_name] = current_state
                    
                self.logger.debug("Updated all device values after force report")
            else:
                # Update only changed device values
                temperature_readings = self.sensor_manager.read_all_temperatures()
                for sensor_id, reading in temperature_readings.items():
                    if reading.is_valid:
                        last_value = self._last_reported_temperatures.get(sensor_id)
                        if last_value is None or abs(reading.value - last_value) >= self.temperature_threshold:
                            self._last_reported_temperatures[sensor_id] = reading.value
                
                for element_name, element_data in self._heating_element_states.items():
                    current_power = element_data['power_kw'] * 1000 if element_data['is_on'] else 0.0
                    last_power = self._last_reported_power.get(element_name)
                    if last_power is None or abs(current_power - last_power) >= self.power_threshold:
                        self._last_reported_power[element_name] = current_power
                
                for pump_name, pump_data in self._pump_states.items():
                    current_state = 1 if pump_data['is_running'] else 0
                    last_state = self._last_reported_pumps.get(pump_name)
                    if last_state is None or current_state != last_state:
                        self._last_reported_pumps[pump_name] = current_state
                        
                self.logger.debug("Updated changed device values only")
                
        except Exception as e:
            self.logger.error(f"Error updating last reported values: {e}")
    
    def _collect_and_send_data(self) -> None:
        """Collect all system data (temperature, power, running hours) and send to API"""
        try:
            # Get all temperature readings
            temperature_readings = self.sensor_manager.read_all_temperatures()
            
            if not temperature_readings:
                self.logger.warning("No temperature readings available")
                return
            
            # Prepare bulk data payload with temperature, power, and running hours data
            bulk_data = self._prepare_bulk_payload(temperature_readings)
            
            # Send data to API with retry logic
            success = self._send_to_api_with_retry(bulk_data, max_retries=3)
            
            if success:
                self.total_reports_sent += 1
                self.last_report_time = datetime.now()
                total_sensors = len(temperature_readings) + len(self._heating_element_states) + len(self._pump_states)
                self.logger.debug(f"Successfully sent system data for {total_sensors} data points")
            else:
                self.total_errors += 1
                
        except Exception as e:
            self.logger.error(f"Error collecting and sending system data: {e}")
            self.total_errors += 1
            self.last_error = str(e)
    
    def _prepare_bulk_payload(self, temperature_readings: Dict) -> Dict:
        """
        Prepare bulk payload for API submission including temperature, power, and running hours
        
        Args:
            temperature_readings: Dictionary of sensor readings
            
        Returns:
            Formatted bulk data payload
        """
        sensor_data_list = []
        
        # Add temperature sensor data
        for sensor_id, reading in temperature_readings.items():
            # Get sensor configuration for additional metadata
            sensor_config = self.config.sensor_paths.get(sensor_id, {})
            device_name = sensor_config.get('description', sensor_id)
            sensor_uuid = sensor_config.get('uuid', str(uuid.uuid4()))
            
            # Only include required fields that API expects
            sensor_data = {
                "sensor_type": "temperature",
                "value": reading.value if reading.is_valid else None,
                "uuid": sensor_uuid,
                "device_name": device_name
            }
            
            sensor_data_list.append(sensor_data)
        
        # Add heating element power data
        for element_name, element_data in self._heating_element_states.items():
            current_power = element_data['power_kw'] * 1000 if element_data['is_on'] else 0.0  # Convert to watts
            
            # Only include required fields that API expects
            power_data = {
                "sensor_type": "power",
                "value": current_power,
                "uuid": element_data['uuid'],
                "device_name": element_data['description']
            }
            sensor_data_list.append(power_data)
        
        # Add pump running state data (not accumulated hours - just current state)
        for pump_name, pump_data in self._pump_states.items():
            # Only include required fields that API expects
            running_data = {
                "sensor_type": "running_hours",
                "value": 1 if pump_data['is_running'] else 0,  # 1 = running, 0 = stopped
                "uuid": pump_data['uuid'],
                "device_name": pump_data['description']
            }
            sensor_data_list.append(running_data)
        
        # Create bulk submission payload - correct format for API
        bulk_data = {
            "batch_uuid": str(uuid.uuid4()),
            "data": sensor_data_list
        }
        
        return bulk_data
    
    def _send_to_api_with_retry(self, data: Dict, max_retries: int = 3) -> bool:
        """
        Send data to API with retry logic and exponential backoff
        
        Args:
            data: Bulk data payload to send
            max_retries: Maximum number of retry attempts
            
        Returns:
            True if successful, False otherwise
        """
        last_error = None
        
        for attempt in range(max_retries + 1):  # +1 for initial attempt
            try:
                success = self._send_to_api(data)
                if success:
                    if attempt > 0:
                        self.logger.info(f"API call succeeded on attempt {attempt + 1}")
                    return True
                else:
                    # API returned error status, but didn't raise exception
                    last_error = self.last_error or f"API returned error status"
                    
            except Exception as e:
                last_error = str(e)
                self.logger.warning(f"API call attempt {attempt + 1} failed: {e}")
            
            # If this wasn't the last attempt, wait before retrying
            if attempt < max_retries:
                # Exponential backoff: 1s, 2s, 4s
                wait_time = 2 ** attempt
                self.logger.info(f"Retrying API call in {wait_time} seconds (attempt {attempt + 2}/{max_retries + 1})")
                time.sleep(wait_time)
        
        # All attempts failed
        self.logger.error(f"API call failed after {max_retries + 1} attempts. Last error: {last_error}")
        self.last_error = f"Failed after {max_retries + 1} attempts: {last_error}"
        return False

    def _send_to_api(self, data: Dict) -> bool:
        """
        Send data to the API endpoint using bulk format (single attempt)
        
        Args:
            data: Bulk data payload to send (format: {"batch_uuid": "...", "data": [...]})
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Use the correct bulk endpoint
            url = f"{self.api_url}/api/sensor-data/bulk"
            
            # Set up request headers
            headers = {
                "Content-Type": "application/json",
                "User-Agent": f"HeatingSystem/{self.config.system_version}"
            }
            
            # Send POST request with proper timeout
            response = requests.post(
                url,
                json=data,
                headers=headers,
                timeout=(5, 30)  # (connection timeout, read timeout)
            )
            
            # Check response - accept all 2xx status codes as success
            # This includes 200 (OK), 201 (Created), 202 (Accepted), 207 (Multi-Status), etc.
            if 200 <= response.status_code < 300:
                sensor_count = len(data.get('data', []))
                
                # For 207 Multi-Status, log additional details if available
                if response.status_code == 207:
                    try:
                        response_data = response.json()
                        success_count = response_data.get('success_count', 'unknown')
                        total_count = response_data.get('total_count', sensor_count)
                        self.logger.info(f"Batch operation completed: {success_count}/{total_count} items processed successfully (HTTP {response.status_code})")
                    except (ValueError, KeyError):
                        self.logger.debug(f"Successfully sent {sensor_count} sensor records to {url} (HTTP {response.status_code})")
                else:
                    self.logger.debug(f"Successfully sent {sensor_count} sensor records to {url} (HTTP {response.status_code})")
                return True
            else:
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}"  # Limit error text
                self.logger.warning(f"API returned error status: {error_msg}")
                self.last_error = error_msg
                return False
                
        except requests.exceptions.Timeout:
            error_msg = f"Request timeout sending to {url}"
            self.logger.warning(error_msg)
            self.last_error = error_msg
            return False
            
        except requests.exceptions.ConnectionError as e:
            error_msg = f"Connection error to {self.api_url}: {str(e)[:100]}"
            self.logger.warning(error_msg)
            self.last_error = error_msg
            return False
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Request error: {str(e)[:100]}"
            self.logger.warning(error_msg)
            self.last_error = error_msg
            return False
            
        except Exception as e:
            error_msg = f"Unexpected error sending to API: {str(e)[:100]}"
            self.logger.error(error_msg)
            self.last_error = error_msg
            return False
    
    def send_immediate_report(self) -> bool:
        """
        Send an immediate system data report (for testing or manual triggers)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Update equipment states before reporting
            self._update_equipment_states()
            # Force report all devices immediately
            all_devices = self._collect_all_devices()
            if all_devices:
                self._send_bulk_update(all_devices)
                self._update_last_reported_values()
            return True
        except Exception as e:
            self.logger.error(f"Error in immediate report: {e}")
            return False
    
    def get_status(self) -> Dict:
        """
        Get current status of the system data reporter
        
        Returns:
            Status dictionary with statistics and state
        """
        current_time = datetime.now()
        time_since_last_force = (current_time - self._last_force_report_time).total_seconds()
        next_force_report_in = max(0, self.force_report_interval - time_since_last_force)
        
        return {
            "is_running": self._is_running,
            "api_url": self.api_url,
            "report_interval": self.report_interval,
            "total_reports_sent": self.total_reports_sent,
            "total_errors": self.total_errors,
            "last_report_time": self.last_report_time.isoformat() if self.last_report_time else None,
            "last_error": self.last_error,
            "temperature_sensor_count": len(self.config.sensor_paths),
            "heating_element_count": len(self._heating_element_states),
            "pump_count": len(self._pump_states),
            "heating_elements": {name: data['is_on'] for name, data in self._heating_element_states.items()},
            "pumps": {name: data['is_running'] for name, data in self._pump_states.items()},
            # Change-based reporting status
            "change_based_reporting": True,
            "temperature_threshold": self.temperature_threshold,
            "power_threshold": self.power_threshold,
            "force_report_interval_minutes": self.force_report_interval / 60,
            "next_force_report_in_seconds": next_force_report_in,
            "tracked_temperatures": len(self._last_reported_temperatures),
            "tracked_power_devices": len(self._last_reported_power),
            "tracked_pumps": len(self._last_reported_pumps)
        }
    
    def test_api_connection(self) -> bool:
        """
        Test connection to the API endpoint
        
        Returns:
            True if API is reachable, False otherwise
        """
        try:
            # Use the specific health endpoint
            test_url = f"{self.api_url}/api/health"
            self.logger.debug(f"Testing API health endpoint: {test_url}")
            response = requests.get(test_url, timeout=3)  # Reduced timeout to prevent blocking
            
            if response.status_code == 200:
                self.logger.info(f"API health check successful: {self.api_url}")
                return True
            else:
                self.logger.warning(f"API health check returned status {response.status_code}")
                return False
                
        except requests.exceptions.Timeout:
            self.logger.warning(f"API health check timeout for {self.api_url}")
            return False
        except requests.exceptions.ConnectionError:
            self.logger.warning(f"API health check connection failed for {self.api_url}")
            return False
        except requests.exceptions.RequestException as e:
            self.logger.warning(f"API health check failed: {e}")
            return False
        except Exception as e:
            self.logger.warning(f"Unexpected error during API health check: {e}")
            return False


def create_system_data_reporter(config: HeatingConfig, sensor_manager: SensorManager, hardware_controller,
                               api_url: str = "http://192.168.191.45:8080", 
                               report_interval: int = 30) -> SystemDataReporter:
    """
    Factory function to create a system data reporter instance
    
    Args:
        config: Heating system configuration
        sensor_manager: Sensor manager instance
        hardware_controller: Hardware controller for reading pump/heating element states
        api_url: API base URL
        report_interval: Reporting interval in seconds
        
    Returns:
        SystemDataReporter instance
    """
    return SystemDataReporter(config, sensor_manager, hardware_controller, api_url, report_interval)


if __name__ == "__main__":
    """Test the system data reporter"""
    print("🌡️ System Data Reporter Test")
    
    # Set up logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        # Load configuration
        from pathlib import Path
        config_path = Path(__file__).parent / "heating_config.yaml"
        
        if not config_path.exists():
            print(f"❌ Configuration file not found: {config_path}")
            exit(1)
        
        config = HeatingConfig.from_yaml(config_path)
        print(f"✅ Loaded configuration with {len(config.sensor_paths)} sensors")
        
        # Create sensor manager
        from sensors import create_sensor_manager
        sensor_manager = create_sensor_manager(config, logging.getLogger("sensors"))
        
        # Create mock hardware controller for testing
        class MockHardwareController:
            def get_output(self, board, port):
                # Mock some random states for testing
                import random
                return random.choice([True, False])
        
        mock_hardware = MockHardwareController()
        
        # Test sensor readings
        readings = sensor_manager.read_all_temperatures()
        print(f"✅ Read {len(readings)} temperature sensors")
        
        for sensor_id, reading in readings.items():
            status = "✅ Valid" if reading.is_valid else "❌ Invalid"
            value = f"{reading.value:.1f}°C" if reading.is_valid else "N/A"
            print(f"  - {sensor_id}: {value} {status}")
        
        # Create and test reporter
        reporter = create_system_data_reporter(config, sensor_manager, mock_hardware)
        
        # Test API connection
        print(f"\n🔗 Testing API connection to {reporter.api_url}...")
        if reporter.test_api_connection():
            print("✅ API connection successful")
        else:
            print("⚠️ API connection failed (this is expected if API server is not running)")
        
        # Test immediate report (will fail if API is not running, but tests the data preparation)
        print("\n📡 Testing immediate report...")
        if reporter.send_immediate_report():
            print("✅ Immediate report sent successfully")
        else:
            print("⚠️ Immediate report failed (expected if API server is not running)")
        
        # Show status
        status = reporter.get_status()
        print(f"\n📊 Reporter Status:")
        print(f"  - Running: {status['is_running']}")
        print(f"  - Reports sent: {status['total_reports_sent']}")
        print(f"  - Errors: {status['total_errors']}")
        print(f"  - Temperature sensors: {status['temperature_sensor_count']}")
        print(f"  - Heating elements: {status['heating_element_count']}")
        print(f"  - Pumps: {status['pump_count']}")
        
        # Test brief automatic reporting (5 seconds)
        print(f"\n⏰ Testing automatic reporting for 5 seconds...")
        reporter.start()
        time.sleep(5)
        reporter.stop()
        
        final_status = reporter.get_status()
        print(f"✅ Test completed - Reports sent: {final_status['total_reports_sent']}, Errors: {final_status['total_errors']}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()