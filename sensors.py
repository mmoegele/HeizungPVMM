#!/usr/bin/env python3
"""Sensor Management Module"""

import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
from config import TemperatureReading, HeatingConfig

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
    def __init__(self, config: HeatingConfig, logger):
        self.config = config
        self.logger = logger
        
        if config.demo_mode or config.mock_hardware:
            self.mock_manager = MockSensorManager(logging.getLogger("sensors"))
            self.use_mock = True
        else:
            self.use_mock = False
            # TODO: Initialize real sensors
    
    def read_all_temperatures(self) -> Dict[str, TemperatureReading]:
        if self.use_mock:
            return self.mock_manager.read_all_temperatures()
        # TODO: Read real sensors
        return {}
    
    def get_valid_temperatures(self) -> Dict[str, float]:
        if self.use_mock:
            return self.mock_manager.get_valid_temperatures()
        # TODO: Read real sensors
        return {}
    
    def run_sensor_diagnostics(self) -> Dict:
        if self.use_mock:
            return self.mock_manager.run_sensor_diagnostics()
        return {"type": "real", "sensor_count": 0}
    
    def set_mock_temperature(self, sensor_id: str, temperature: float) -> None:
        if self.use_mock:
            self.mock_manager.set_mock_temperature(sensor_id, temperature)

def create_sensor_manager(config: HeatingConfig, logger) -> SensorManager:
    return SensorManager(config, logger)

if __name__ == "__main__":
    print("🔧 Sensor Module Test")
    from config import HeatingConfig
    config = HeatingConfig(demo_mode=True)
    sensor_manager = SensorManager(config, None)
    temps = sensor_manager.get_valid_temperatures()
    print(f"✅ Sensor test completed: {len(temps)} sensors")
