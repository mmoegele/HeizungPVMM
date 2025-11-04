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
    control_parameters: Dict[str, Any] = field(default_factory=dict)

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
    rate_limit: str = ""  # Disabled - no rate limiting
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
    pump_port: str = "wt_pumpe"       # Port name for pump (references outputs section)
    # BHKW Detection Configuration
    require_bhkw_active: bool = True  # Only run heat exchanger when BHKW is active
    bhkw_status_input: str = "bhkw_running_status"  # Digital input name to read BHKW status
    bhkw_temp_threshold: float = 30.0  # Fallback: Minimum temperature to consider BHKW active (°C)

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
    pump_port: str = "puffer_lade_pumpe"    # Port name for pump (references outputs section)

@dataclass
class EVCCConfig:
    """EVCC integration configuration"""
    enable: bool = False
    base_url: str = "http://192.168.191.45:7070"
    timeout: int = 10
    update_interval: int = 30
    min_battery_soc_for_heating: float = 50.0
    max_battery_soc_for_aggressive: float = 80.0
    max_temperature_for_heating: float = 70.0
    min_surplus_duration: int = 120
    heating_element_power: float = 2000.0
    turn_on_hysteresis: float = 200.0
    turn_off_hysteresis: float = 300.0
    cache_duration: int = 5
    # Manual Mode Configuration
    enable_manual_override: bool = True
    default_duration_minutes: int = 15
    max_duration_minutes: int = 60
    min_duration_minutes: int = 5

@dataclass
class SystemDataReporterConfig:
    """System data reporter configuration (temperature, power, running hours)"""
    enable: bool = True
    api_url: str = "http://192.168.191.45:8080"
    report_interval: int = 30
    timeout: int = 10

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
    hardware_outputs: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # Complete hardware output config
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
    evcc: EVCCConfig = field(default_factory=EVCCConfig)
    system_data_reporter: SystemDataReporterConfig = field(default_factory=SystemDataReporterConfig)

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
            http_service.require_auth = http_config.get('require_auth', False)
            http_service.api_key = http_config.get('api_key', '')
            http_service.rate_limit = http_config.get('rate_limit', '')  # Default: no rate limiting
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
        
        # Extract pump port configurations and complete hardware output configs
        pump_port_config = {}
        hardware_outputs = {}
        if 'hardware' in config_data and 'outputs' in config_data['hardware']:
            for output_name, output_config in config_data['hardware']['outputs'].items():
                if isinstance(output_config, dict) and 'board' in output_config and 'port' in output_config:
                    pump_port_config[output_name] = (output_config['board'], output_config['port'])
                    hardware_outputs[output_name] = output_config  # Store complete config including UUID
                else:
                    print(f"Warning: Invalid output config for {output_name}: {output_config}")
                
        # Extract mixer configuration
        mixer_config = MixerConfig()
        if 'mixers' in config_data:
            mixers_data = config_data['mixers']
            mixer_config.enable_fixed_temperature = mixers_data.get('enable_fixed_temperature', True)
            mixer_config.pump_activation_temperature = mixers_data.get('pump_activation_temperature', 20.0)
            mixer_config.temperature_tolerance = mixers_data.get('temperature_tolerance', 1.0)
            mixer_config.mixer_controllers = mixers_data.get('mixer_controllers', {})
            # Add support for control_parameters
            mixer_config.control_parameters = mixers_data.get('control_parameters', {})
        
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
        
        # Extract Buffer Load configuration
        buffer_load_config = BufferLoadConfig()
        if 'buffer_load' in config_data:
            buffer_data = config_data['buffer_load']
            buffer_load_config.min_temperature_difference = buffer_data.get('min_temperature_difference', 2.0)
            buffer_load_config.hysteresis = buffer_data.get('hysteresis', 1.0)
            buffer_load_config.min_run_time = buffer_data.get('min_run_time', 60)
            buffer_load_config.min_off_time = buffer_data.get('min_off_time', 120)
            buffer_load_config.check_interval = buffer_data.get('check_interval', 30)
            buffer_load_config.source_sensor = buffer_data.get('source_sensor', 'puffer_k_mitte')
            buffer_load_config.target_sensor = buffer_data.get('target_sensor', 'puffer_m_mitte')
            buffer_load_config.pump_port = buffer_data.get('pump_port', 'puffer_lade_pumpe')
        
        # Extract Heat Exchanger configuration
        heat_exchanger_config = HeatExchangerConfig()
        if 'heat_exchanger' in config_data:
            heat_data = config_data['heat_exchanger']
            heat_exchanger_config.target_temperature = heat_data.get('target_temperature', 65.0)
            heat_exchanger_config.min_temperature = heat_data.get('min_temperature', 50.0)
            heat_exchanger_config.min_pump_interval = heat_data.get('min_pump_interval', 0.15)
            heat_exchanger_config.max_interval = heat_data.get('max_interval', 1.0)
            heat_exchanger_config.min_interval = heat_data.get('min_interval', 0.1)
            heat_exchanger_config.interval_multiplier = heat_data.get('interval_multiplier', 1.5)
            heat_exchanger_config.control_interval = heat_data.get('control_interval', 10)
            heat_exchanger_config.temperature_sensor = heat_data.get('temperature_sensor', 'bhkw_vorlauf')
            heat_exchanger_config.pump_port = heat_data.get('pump_port', 'wt_pumpe')
            # BHKW Detection Configuration  
            heat_exchanger_config.require_bhkw_active = heat_data.get('require_bhkw_active', True)
            heat_exchanger_config.bhkw_status_input = heat_data.get('bhkw_status_input', 'bhkw_running_status')
            heat_exchanger_config.bhkw_temp_threshold = heat_data.get('bhkw_temp_threshold', 30.0)

        # Extract EVCC configuration
        evcc_config = EVCCConfig()
        if 'evcc' in config_data:
            evcc_data = config_data['evcc']
            evcc_config.enable = evcc_data.get('enable', False)
            evcc_config.base_url = evcc_data.get('base_url', 'http://192.168.191.45:7070')
            evcc_config.timeout = evcc_data.get('timeout', 10)
            evcc_config.update_interval = evcc_data.get('update_interval', 30)
            evcc_config.min_battery_soc_for_heating = evcc_data.get('min_battery_soc_for_heating', 50.0)
            evcc_config.max_battery_soc_for_aggressive = evcc_data.get('max_battery_soc_for_aggressive', 80.0)
            evcc_config.max_temperature_for_heating = evcc_data.get('max_temperature_for_heating', 70.0)
            evcc_config.min_surplus_duration = evcc_data.get('min_surplus_duration', 120)
            evcc_config.heating_element_power = evcc_data.get('heating_element_power', 2000.0)
            evcc_config.turn_on_hysteresis = evcc_data.get('turn_on_hysteresis', 200.0)
            evcc_config.turn_off_hysteresis = evcc_data.get('turn_off_hysteresis', 300.0)
            evcc_config.cache_duration = evcc_data.get('cache_duration', 5)
            
            # Manual Mode Configuration
            manual_mode_data = evcc_data.get('manual_mode', {})
            evcc_config.enable_manual_override = manual_mode_data.get('enable_manual_override', True)
            evcc_config.default_duration_minutes = manual_mode_data.get('default_duration_minutes', 15)
            evcc_config.max_duration_minutes = manual_mode_data.get('max_duration_minutes', 60)
            evcc_config.min_duration_minutes = manual_mode_data.get('min_duration_minutes', 5)
        
        # Extract System Data Reporter configuration
        system_reporter_config = SystemDataReporterConfig()
        if 'system_data_reporter' in config_data:
            temp_data = config_data['system_data_reporter']
            system_reporter_config.enable = temp_data.get('enable', True)
            system_reporter_config.api_url = temp_data.get('api_url', 'http://192.168.191.45:8080')
            system_reporter_config.report_interval = temp_data.get('report_interval', 30)
            system_reporter_config.timeout = temp_data.get('timeout', 10)
        # Legacy support for old temperature_reporter config name
        elif 'temperature_reporter' in config_data:
            temp_data = config_data['temperature_reporter']
            system_reporter_config.enable = temp_data.get('enable', True)
            system_reporter_config.api_url = temp_data.get('api_url', 'http://192.168.191.45:8080')
            system_reporter_config.report_interval = temp_data.get('report_interval', 30)
            system_reporter_config.timeout = temp_data.get('timeout', 10)
        
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
            hardware_outputs=hardware_outputs,
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
            mixers=mixer_config,
            heat_exchanger=heat_exchanger_config,
            buffer_load=buffer_load_config,
            http_service=http_service,
            evcc=evcc_config,
            system_data_reporter=system_reporter_config,
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
