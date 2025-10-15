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
            report_interval: Reporting interval in seconds
        """
        self.config = config
        self.sensor_manager = sensor_manager
        self.hardware_controller = hardware_controller
        self.api_url = api_url.rstrip('/')
        self.report_interval = report_interval
        self.logger = logging.getLogger("heating.system_data_reporter")
        
        # Threading control
        self._stop_event = threading.Event()
        self._reporting_thread: Optional[threading.Thread] = None
        self._is_running = False
        
        # Statistics
        self.total_reports_sent = 0
        self.total_errors = 0
        self.last_report_time: Optional[datetime] = None
        self.last_error: Optional[str] = None
        
        # Power and running state tracking
        self._heating_element_states = {}  # Track heating element on/off states
        self._pump_states = {}  # Track pump running states
        self._last_state_check = datetime.now()
        
        # Initialize power tracking for heating elements
        self._initialize_power_tracking()
        self._initialize_pump_tracking()
        
        self.logger.info(f"System data reporter initialized - API: {self.api_url}, Interval: {report_interval}s")
        self.logger.info(f"Equipment tracking: {len(self._heating_element_states)} heating elements, {len(self._pump_states)} pumps")
    
    def _initialize_power_tracking(self) -> None:
        """Initialize tracking for heating elements power consumption"""
        try:
            self.logger.debug("Starting heating element power tracking initialization")
            # Get hardware outputs from hardware.outputs which contains the complete configuration
            if hasattr(self.config, 'hardware') and hasattr(self.config.hardware, 'outputs'):
                for output_name, output_config in self.config.hardware.outputs.items():
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
                for pump_name in pump_names:
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
                self.logger.warning("No hardware.outputs configuration found")
            
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
        """Main reporting loop that runs in a separate thread"""
        self.logger.info(f"📊 System data reporting loop started - will report every {self.report_interval}s")
        
        while not self._stop_event.is_set():
            try:
                # Update equipment states before collecting data
                self._update_equipment_states()
                
                # Collect and send all system data
                self._collect_and_send_data()
                
                # Wait for the next interval or until stop event
                self._stop_event.wait(self.report_interval)
                
            except Exception as e:
                self.logger.error(f"Error in reporting loop: {e}")
                self.total_errors += 1
                self.last_error = str(e)
                # Wait a bit before retrying to avoid rapid error loops
                self._stop_event.wait(min(self.report_interval, 10))
        
        self.logger.info("System data reporting loop ended")
    
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
            
            # Check response
            if response.status_code == 200:
                sensor_count = len(data.get('data', []))
                self.logger.debug(f"Successfully sent {sensor_count} sensor records to {url}")
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
            self._collect_and_send_data()
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
            "pumps": {name: data['is_running'] for name, data in self._pump_states.items()}
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