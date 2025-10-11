#!/usr/bin/env python3
"""
Configuration Module - Data Structures and Configuration Management
"""

import yaml
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Union
from pathlib import Path
from datetime import datetime
from enum import Enum


def safe_get_nested(data, keys, default=None):
    """Safely get nested dictionary values"""
    try:
        for key in keys:
            if isinstance(data, dict) and key in data and data[key] is not None:
                data = data[key]
            else:
                return default
        return data
    except (TypeError, AttributeError):
        return default

class SystemState(Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    EMERGENCY_SHUTDOWN = "emergency_shutdown"

@dataclass
class TemperatureReading:
    value: float
    timestamp: datetime
    sensor_id: str
    is_valid: bool = True
    error_message: Optional[str] = None

@dataclass
class SafetyLimits:
    max_temperature: float = 85.0
    min_temperature: float = -20.0
    max_temperature_difference: float = 50.0
    max_pump_runtime_minutes: int = 120
    watchdog_timeout_seconds: int = 60

@dataclass
class MixerConfig:
    enable_fixed_temperature: bool = True
    pump_activation_temperature: float = 20.0
    temperature_tolerance: float = 1.0
    mixer_controllers: Dict[str, Dict[str, Any]] = field(default_factory=dict)

@dataclass
class HeatingElementConfig:
    element_id: str
    board: int
    port: int
    power_kw: float = 2.0
    priority: int = 1
    temperature_sensor: Optional[str] = None
    max_runtime_minutes: int = 60

@dataclass
class HTTPServiceConfig:
    enable: bool = True
    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False
    require_auth: bool = True
    api_key: str = ""
    rate_limit: str = "100 per hour"
    enable_cors: bool = True
    dashboard_file: str = "dashboard.html"

@dataclass
class HeatExchangerConfig:
    """Heat exchanger configuration settings"""
    target_temperature: float = 65.0  # Target temperature (wtSollTemperatur)
    min_temperature: float = 50.0    # Minimum temperature (wtMinTemperatur)
    min_pump_interval: float = 0.15  # Minimum pump on time
    max_interval: float = 1.0        # Maximum interval between pump cycles (seconds)
    min_interval: float = 0.1        # Minimum interval between pump cycles (seconds)
    interval_multiplier: float = 1.5  # Multiplier for wait time between cycles
    control_interval: int = 10        # Read interval in seconds
    temperature_sensor: str = "bhkw_vorlauf"  # Temperature sensor ID
    # Hardware configuration
    pump_board: int = 1              # PiFace board number for pump
    pump_port: int = 7               # Port number for pump

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
    pump_board: int = 0                     # Board number for pump
    pump_port: int = 6                      # Port number for pump

@dataclass
class HeatingConfig:
    system_name: str = "Heating Controller"
    system_version: str = "2.0.0"
    load_temperature: float = 40.0
    mixers: MixerConfig = field(default_factory=MixerConfig)
    heat_exchanger: HeatExchangerConfig = field(default_factory=HeatExchangerConfig)
    buffer_load: BufferLoadConfig = field(default_factory=BufferLoadConfig)
    temperature_tolerance: float = 1.0
    charge_temperature_difference: float = 3.0
    one_wire_mount_point: str = "/mnt/1wire"
    sensor_paths: Dict[str, Dict[str, str]] = field(default_factory=dict)
    sensor_cache_duration: int = 2
    sensor_read_timeout: int = 5
    sensor_retry_attempts: int = 3
    piface_board_count: int = 2
    pump_port_config: Dict[str, Tuple[int, int]] = field(default_factory=dict)
    heating_elements: List[HeatingElementConfig] = field(default_factory=list)
    heating_auto_control: bool = True
    heating_max_simultaneous: int = 2
    main_loop_interval: int = 5
    temperature_read_interval: int = 300
    safety_check_interval: int = 10
    volkszaehler_base_url: str = ""
    volkszaehler_timeout: int = 10
    demo_mode: bool = False
    mock_hardware: bool = False
    simulation_mode: bool = False
    safety: SafetyLimits = field(default_factory=SafetyLimits)
    http_service: HTTPServiceConfig = field(default_factory=HTTPServiceConfig)

    @classmethod
    def from_yaml(cls, yaml_path: Union[str, Path]) -> 'HeatingConfig':
        yaml_path = Path(yaml_path)
        if not yaml_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {yaml_path}")
        
        with open(yaml_path, 'r') as f:
            config_data = yaml.safe_load(f)
        
        # Initialize HTTP service config
        http_service = HTTPServiceConfig()
        if 'http_service' in config_data:
            http_config = config_data['http_service']
            http_service.enable = http_config.get('enable', True)
            http_service.host = http_config.get('host', '0.0.0.0')
            http_service.port = http_config.get('port', 8080)
            http_service.debug = http_config.get('debug', False)
            http_service.require_auth = http_config.get('require_auth', True)
            http_service.api_key = http_config.get('api_key', '')
            http_service.rate_limit = http_config.get('rate_limit', '100 per hour')
            http_service.enable_cors = http_config.get('enable_cors', True)
            http_service.dashboard_file = http_config.get('dashboard_file', 'dashboard.html')
        
        # Extract one-wire and sensor configuration
        one_wire_mount_point = safe_get_nested(config_data, ['sensors', 'one_wire_mount_point'], '/mnt/1wire')
        
        # Extract sensor paths and configuration
        sensor_paths = {}
        if 'sensors' in config_data and 'temperature_sensors' in config_data['sensors']:
            for sensor_name, sensor_config in config_data['sensors']['temperature_sensors'].items():
                sensor_paths[sensor_name] = {
                    'path': sensor_config['path'],
                    'description': sensor_config.get('description', ''),
                    'uuid': sensor_config.get('uuid', '')
                }
        
        # Extract pump port configurations
        pump_port_config = {}
        if 'hardware' in config_data and 'outputs' in config_data['hardware']:
            for output_name, output_config in config_data['hardware']['outputs'].items():
                pump_port_config[output_name] = (output_config['board'], output_config['port'])
                
        # Extract mixer configuration
        mixer_config = MixerConfig()
        if 'mixers' in config_data:
            mixers_data = config_data['mixers']
            mixer_config.enable_fixed_temperature = mixers_data.get('enable_fixed_temperature', True)
            mixer_config.pump_activation_temperature = mixers_data.get('pump_activation_temperature', 20.0)
            mixer_config.temperature_tolerance = mixers_data.get('temperature_tolerance', 1.0)
            mixer_config.mixer_controllers = mixers_data.get('mixer_controllers', {})
        
        # Extract heating elements
        heating_elements = []
        heating_elements_config = config_data.get('heating_elements', {})
        if 'elements' in heating_elements_config:
            for element_id, element_config in heating_elements_config['elements'].items():
                heating_elements.append(HeatingElementConfig(
                    element_id=element_id,
                    board=element_config['board'],
                    port=element_config['port'],
                    power_kw=element_config.get('power_kw', 2.0),
                    priority=element_config.get('priority', 1),
                    temperature_sensor=element_config.get('temperature_sensor'),
                    max_runtime_minutes=element_config.get('max_runtime_minutes', 60)
                ))
        
        return cls(
            system_name=safe_get_nested(config_data, ['system', 'name'], 'Heating Controller'),
            system_version=safe_get_nested(config_data, ['system', 'version'], '2.0.0'),
            load_temperature=safe_get_nested(config_data, ['temperature', 'load_temperature'], 40.0),
            temperature_tolerance=safe_get_nested(config_data, ['temperature', 'temperature_tolerance'], 1.0),
            charge_temperature_difference=safe_get_nested(config_data, ['temperature', 'charge_temperature_difference'], 3.0),
            one_wire_mount_point=one_wire_mount_point,
            sensor_paths=sensor_paths,
            sensor_cache_duration=safe_get_nested(config_data, ['sensors', 'cache_duration_seconds'], 2),
            sensor_read_timeout=safe_get_nested(config_data, ['sensors', 'read_timeout_seconds'], 5),
            sensor_retry_attempts=safe_get_nested(config_data, ['sensors', 'retry_attempts'], 3),
            piface_board_count=safe_get_nested(config_data, ['hardware', 'piface', 'board_count'], 2),
            pump_port_config=pump_port_config,
            heating_elements=heating_elements,
            heating_auto_control=heating_elements_config.get('auto_control', True),
            heating_max_simultaneous=heating_elements_config.get('max_simultaneous', 2),
            main_loop_interval=safe_get_nested(config_data, ['timing', 'main_loop_interval'], 5),
            temperature_read_interval=safe_get_nested(config_data, ['timing', 'temperature_read_interval'], 300),
            safety_check_interval=safe_get_nested(config_data, ['timing', 'safety_check_interval'], 10),
            volkszaehler_base_url=safe_get_nested(config_data, ['network', 'volkszaehler', 'base_url'], ''),
            volkszaehler_timeout=safe_get_nested(config_data, ['network', 'volkszaehler', 'timeout'], 10),
            demo_mode=safe_get_nested(config_data, ['development', 'demo_mode'], False),
            mock_hardware=safe_get_nested(config_data, ['development', 'mock_hardware'], False),
            simulation_mode=safe_get_nested(config_data, ['development', 'simulation_mode'], False),
        )
    
    def validate(self) -> None:
        if not 0 <= self.load_temperature <= 100:
            raise ValueError(f"Invalid load_temperature: {self.load_temperature}")
        if self.temperature_tolerance <= 0:
            raise ValueError(f"Invalid temperature_tolerance: {self.temperature_tolerance}")

def load_complete_config(config_path: Union[str, Path]):
    config_path = Path(config_path)
    heating_config = HeatingConfig.from_yaml(config_path)
    return heating_config, None  # EVCC config placeholder

if __name__ == "__main__":
    print("🔧 Configuration Module Test")
    config = HeatingConfig()
    config.validate()
    print("✅ Configuration test passed")
