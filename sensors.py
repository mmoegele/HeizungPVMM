#!/usr/bin/env python3
"""Sensor Management Module"""

import os
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple
from config import TemperatureReading, HeatingConfig

class TemperatureSensor:
    """1-Wire temperature sensor implementation"""
    
    def __init__(self, sensor_path: str, sensor_id: str, description: str, 
                 retry_attempts: int = 3, retry_delay: float = 0.1):
        self.path = Path(sensor_path)
        self.sensor_id = sensor_id
        self.description = description
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self._last_reading: Optional[TemperatureReading] = None
        self._last_error: Optional[str] = None
    
    def read_raw_value(self) -> Tuple[bool, str]:
        """Read raw value from sensor file"""
        try:
            if not self.path.exists():
                return False, f"Sensor file not found: {self.path}"
            
            with open(self.path, 'r') as f:
                content = f.read().strip()
            
            if not content:
                return False, "Empty sensor reading"
            
            if "YES" not in content:
                return False, "Invalid CRC"
            
            if "t=" not in content:
                return False, "No temperature value found"
            
            return True, content
            
        except Exception as e:
            return False, f"Error reading sensor: {e}"
    
    def parse_temperature(self, raw_content: str) -> Optional[float]:
        """Parse temperature value from raw sensor data"""
        try:
            temp_pos = raw_content.find("t=")
            if temp_pos != -1:
                temp_string = raw_content[temp_pos + 2:]
                temp_value = float(temp_string) / 1000.0
                return temp_value
            return None
        except (ValueError, IndexError) as e:
            return None
    
    def read_temperature(self) -> TemperatureReading:
        """Read temperature with retry logic"""
        now = datetime.now()
        
        for attempt in range(self.retry_attempts):
            success, raw_value = self.read_raw_value()
            
            if success:
                temp = self.parse_temperature(raw_value)
                if temp is not None:
                    reading = TemperatureReading(
                        value=temp,
                        timestamp=now,
                        sensor_id=self.sensor_id,
                        is_valid=True
                    )
                    self._last_reading = reading
                    self._last_error = None
                    return reading
            
            if attempt < self.retry_attempts - 1:
                time.sleep(self.retry_delay)
        
        # Return invalid reading after all retries failed
        error_msg = f"Failed to read sensor after {self.retry_attempts} attempts"
        self._last_error = error_msg
        return TemperatureReading(
            value=0.0,
            timestamp=now,
            sensor_id=self.sensor_id,
            is_valid=False,
            error_message=error_msg
        )
    
    @property
    def last_reading(self) -> Optional[TemperatureReading]:
        return self._last_reading
    
    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

class MockSensorManager:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.mock_temperatures = {
            'puffer_k_mitte': 45.0,
            'puffer_k_vorlauf': 50.0,
            'puffer_k_rueck': 40.0,
            'puffer_m_mitte': 48.0,
            'puffer_m_vorlauf': 52.0,
            'puffer_m_rueck': 42.0
        }
    
    def read_all_temperatures(self) -> Dict[str, TemperatureReading]:
        readings = {}
        now = datetime.now()
        
        for sensor_id, temp in self.mock_temperatures.items():
            readings[sensor_id] = TemperatureReading(
                value=temp,
                timestamp=now,
                sensor_id=sensor_id,
                is_valid=True
            )
        return readings
    
    def get_valid_temperatures(self) -> Dict[str, float]:
        readings = self.read_all_temperatures()
        return {sensor_id: reading.value for sensor_id, reading in readings.items()}
    
    def set_mock_temperature(self, sensor_id: str, temperature: float) -> None:
        self.mock_temperatures[sensor_id] = temperature
    
    def run_sensor_diagnostics(self) -> Dict:
        return {
            "type": "mock",
            "sensor_count": len(self.mock_temperatures)
        }

class SensorManager:
    """Main sensor management class"""
    
    def __init__(self, config: HeatingConfig, logger):
        self.config = config
        self.logger = logger
        self.sensors: Dict[str, TemperatureSensor] = {}
        self.cache_duration = timedelta(seconds=config.sensor_cache_duration)
        self.last_cache_update = None
        self.cached_readings: Dict[str, TemperatureReading] = {}
        
        if config.demo_mode or config.mock_hardware:
            self.mock_manager = MockSensorManager(logging.getLogger("sensors"))
            self.use_mock = True
        else:
            self.use_mock = False
            self._initialize_sensors()
    
    def _initialize_sensors(self):
        """Initialize all configured temperature sensors"""
        one_wire_path = Path(self.config.one_wire_mount_point)
        if not one_wire_path.exists():
            self.logger.error(f"One-Wire mount point not found: {one_wire_path}")
            return
            
        for sensor_id, sensor_config in self.config.sensor_paths.items():
            try:
                # Use the full sensor path as configured
                sensor_path = Path(sensor_config['path'])
                if not sensor_path.is_absolute():
                    # If it's a relative path, prepend the one_wire_mount_point
                    sensor_path = one_wire_path / sensor_path
                
                description = sensor_config.get('description', f"Temperature Sensor {sensor_id}")
                sensor = TemperatureSensor(
                    sensor_path=str(sensor_path),
                    sensor_id=sensor_id,
                    description=description,
                    retry_attempts=self.config.sensor_retry_attempts
                )
                self.sensors[sensor_id] = sensor
                self.logger.debug(f"Initialized sensor {sensor_id} at {sensor_path}")
            except Exception as e:
                self.logger.error(f"Failed to initialize sensor {sensor_id}: {e}")
    
    def read_all_temperatures(self) -> Dict[str, TemperatureReading]:
        """Read all temperature sensors with caching"""
        if self.use_mock:
            return self.mock_manager.read_all_temperatures()
        
        now = datetime.now()
        
        # Return cached values if still valid
        if (self.last_cache_update and 
            now - self.last_cache_update < self.cache_duration):
            return self.cached_readings
        
        readings = {}
        self.last_cache_update = now
        for sensor_id, sensor in self.sensors.items():
            try:
                reading = sensor.read_temperature()
                readings[sensor_id] = reading
                
                if not reading.is_valid:
                    self.logger.warning(
                        f"Invalid reading from sensor {sensor_id}: {reading.error_message}"
                    )
            except Exception as e:
                self.logger.error(f"Error reading sensor {sensor_id}: {e}")
                readings[sensor_id] = TemperatureReading(
                    value=0.0,
                    timestamp=now,
                    sensor_id=sensor_id,
                    is_valid=False,
                    error_message=str(e)
                )
        
        # Update cache
        self.cached_readings = readings
        self.last_cache_update = now
        
        return readings
    
    def get_valid_temperatures(self) -> Dict[str, float]:
        """Get only valid temperature readings"""
        if self.use_mock:
            return self.mock_manager.get_valid_temperatures()
        
        readings = self.read_all_temperatures()
        return {
            sensor_id: reading.value 
            for sensor_id, reading in readings.items() 
            if reading.is_valid
        }
    
    def run_sensor_diagnostics(self) -> Dict:
        """Run diagnostics on all sensors"""
        if self.use_mock:
            return self.mock_manager.run_sensor_diagnostics()
        
        readings = self.read_all_temperatures()
        valid_count = sum(1 for r in readings.values() if r.is_valid)
        
        diagnostics = {
            "type": "real",
            "sensor_count": len(self.sensors),
            "valid_sensors": valid_count,
            "all_valid": valid_count == len(self.sensors),
            "errors": {}
        }
        
        # Collect error messages
        for sensor_id, reading in readings.items():
            if not reading.is_valid and reading.error_message:
                diagnostics["errors"][sensor_id] = reading.error_message
        
        return diagnostics
    
    def set_mock_temperature(self, sensor_id: str, temperature: float) -> None:
        """Set mock temperature (only in mock mode)"""
        if self.use_mock:
            self.mock_manager.set_mock_temperature(sensor_id, temperature)

def create_sensor_manager(config: HeatingConfig, logger) -> SensorManager:
    return SensorManager(config, logger)

if __name__ == "__main__":
    print("🔧 Sensor Module Test")
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("test")
    
    try:
        # Test with mock mode
        print("\nTesting mock mode:")
        mock_config = HeatingConfig(demo_mode=True)
        mock_manager = create_sensor_manager(mock_config, logger)
        mock_temps = mock_manager.get_valid_temperatures()
        print(f"✅ Mock sensors: {len(mock_temps)} readings")
        for sensor_id, temp in mock_temps.items():
            print(f"  - {sensor_id}: {temp:.1f}°C")
        
        # Test with real sensors if available
        print("\nTesting real sensors:")
        real_config = HeatingConfig(
            demo_mode=False,
            mock_hardware=False,
            sensor_paths={
                "test_sensor": "/sys/bus/w1/devices/28-xxxxxxxxxxxx/w1_slave"
            }
        )
        real_manager = create_sensor_manager(real_config, logger)
        real_temps = real_manager.get_valid_temperatures()
        print(f"✅ Real sensors: {len(real_temps)} readings")
        
        # Run diagnostics
        diagnostics = real_manager.run_sensor_diagnostics()
        print("\nDiagnostics:", diagnostics)
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
    else:
        print("\n✅ All tests completed")
