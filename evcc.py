#!/usr/bin/env python3
"""
EVCC Integration for Heating System Control
=========================================

This module provides integration with EVCC (Electric Vehicle Charge Controller)
to enable solar-optimized heating control. It fetches PV production, grid power,
and battery state from EVCC to inform heating decisions.
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional, Dict, List
from datetime import datetime, timedelta
import requests


class HeatingElementState:
    """Tracks state and runtime of a heating element"""
    def __init__(self, element_id: str):
        self.element_id = element_id
        self.is_on = False
        self.last_on = None
        self.last_off = None
        self.total_runtime = timedelta()
        self.cycle_count = 0

    def turn_on(self):
        """Record turning on the element"""
        if not self.is_on:
            self.is_on = True
            self.last_on = datetime.now()
            self.cycle_count += 1

    def turn_off(self):
        """Record turning off the element"""
        if self.is_on:
            self.is_on = False
            self.last_off = datetime.now()
            if self.last_on:
                self.total_runtime += self.last_off - self.last_on

    @property
    def current_runtime(self) -> timedelta:
        """Get current continuous runtime if element is on"""
        if self.is_on and self.last_on:
            return datetime.now() - self.last_on
        return timedelta()


class EVCCController:
    """EVCC Controller with threaded operation and health monitoring"""
    def __init__(self, config, hardware, logger):
        self.config = config
        self.hardware = hardware
        self.logger = logger
        self.running = False
        self.thread = None
        self.last_update = None
        self.last_error = None
        self.update_count = 0
        
        # Confirmation system - require 2 consecutive checks before action
        self.pending_action = None  # Target number of elements to activate
        self.confirmation_count = 0
        self.required_confirmations = 2
        
        # Initialize EVCC client
        evcc_config = SolarHeatingConfig(
            evcc_base_url=config.evcc.base_url,
            evcc_timeout=config.evcc.timeout
        )
        self.evcc_client = EVCCClient(evcc_config)
        
        # Initialize heating elements to OFF state for safety
        print("🔄 Initializing heating elements...")
        self._initialize_heating_elements()
        print("✅ EVCC controller initialized")
        
    def start(self):
        """Start the EVCC controller thread"""
        if self.running:
            self.logger.warning("EVCC controller already running")
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._control_loop, name="EVCCController", daemon=True)
        self.thread.start()
        self.logger.info("EVCC controller thread started")
    
    def _initialize_heating_elements(self):
        """Initialize all heating elements to OFF state for safety"""
        try:
            self.logger.info("Initializing heating elements to OFF state")
            
            # Get heating element ports
            heizstab_ports = self._get_heating_element_ports()
            
            # Turn off all heating elements
            for port_config in heizstab_ports:
                try:
                    self.hardware.set_output((port_config['board'], port_config['port']), False)
                    self.logger.info(f"Set {port_config['description']} (B{port_config['board']}P{port_config['port']}) to OFF")
                except Exception as e:
                    self.logger.error(f"Failed to set {port_config['description']} to OFF: {e}")
            
            self.logger.info("All heating elements initialized to OFF state")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize heating elements: {e}")
    
    def _get_heating_element_ports(self):
        """Get heating element port configurations"""
        heizstab_ports = []
        try:
            # Use the hardware.get_output_by_name method if available
            for heizstab_id in ['heizstab_1', 'heizstab_2', 'heizstab_3']:
                if hasattr(self.hardware, 'get_output_by_name'):
                    try:
                        output_info = self.hardware.get_output_by_name(heizstab_id)
                        if output_info:
                            heizstab_ports.append({
                                'board': output_info['board'], 
                                'port': output_info['port'], 
                                'description': heizstab_id
                            })
                    except Exception:
                        # If get_output_by_name fails, skip this heizstab
                        continue
        except Exception:
            pass
        
        if not heizstab_ports:
            # Fallback to default ports from configuration
            heizstab_ports = [
                {'board': 1, 'port': 0, 'description': 'heizstab_1'},
                {'board': 1, 'port': 1, 'description': 'heizstab_2'},
                {'board': 1, 'port': 2, 'description': 'heizstab_3'},
            ]
        
        return heizstab_ports
        
    def _get_current_heating_power(self):
        """Calculate the current power consumption of active heating elements"""
        try:
            current_power = 0
            heating_element_power = getattr(self.config.evcc, 'heating_element_power', 1700.0)
            
            # Get heating element ports
            heizstab_ports = self._get_heating_element_ports()
            
            # Check each heating element
            for port_config in heizstab_ports:
                try:
                    is_active = self.hardware.get_output(port_config['board'], port_config['port'])
                    if is_active:
                        current_power += heating_element_power
                        self.logger.debug(f"Heating element {port_config['description']} is active, adding {heating_element_power}W")
                except Exception as e:
                    self.logger.warning(f"Failed to check status of {port_config['description']}: {e}")
            
            self.logger.debug(f"Total current heating power: {current_power}W")
            return current_power
            
        except Exception as e:
            self.logger.error(f"Failed to calculate current heating power: {e}")
            return 0
        
    def stop(self):
        """Stop the EVCC controller thread"""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                self.logger.warning("EVCC controller thread did not stop gracefully")
            else:
                self.logger.info("EVCC controller thread stopped")
        self.thread = None
        
    def _control_loop(self):
        """Main EVCC control loop"""
        self.logger.info("EVCC control loop started")
        
        while self.running:
            try:
                # Run EVCC heating control with confirmation system
                control_heating_elements_with_confirmation(self.evcc_client, self.hardware, self.config, self.logger, self)
                
                # Update status
                self.last_update = datetime.now()
                self.update_count += 1
                self.last_error = None
                
            except Exception as e:
                self.last_error = str(e)
                self.logger.error(f"EVCC control loop error: {e}")
            
            # Sleep for update interval
            sleep_time = self.config.evcc.update_interval
            for _ in range(sleep_time):
                if not self.running:
                    break
                time.sleep(1)
        
        self.logger.info("EVCC control loop ended")
        
    def is_thread_healthy(self) -> bool:
        """Check if EVCC thread is healthy"""
        if not self.running:
            return False
        if not self.thread or not self.thread.is_alive():
            return False
        
        # Check if we've had updates recently
        if self.last_update:
            time_since_update = datetime.now() - self.last_update
            max_allowed_time = timedelta(seconds=self.config.evcc.update_interval * 2.5)
            if time_since_update > max_allowed_time:
                return False
                
        return True
        
    def get_thread_status(self) -> Dict:
        """Get detailed thread status"""
        status = {
            'thread_healthy': self.is_thread_healthy(),
            'thread_alive': self.thread.is_alive() if self.thread else False,
            'running': self.running,
            'last_update': self.last_update.isoformat() if self.last_update else None,
            'update_count': self.update_count,
            'last_error': self.last_error,
            'evcc_connected': self.evcc_client.is_healthy() if self.evcc_client else False
        }
        return status
        
    def get_state(self) -> Dict:
        """Get EVCC controller state"""
        status = self.get_thread_status()
        
        # Try to get current EVCC data
        evcc_data = None
        loadpoints_data = None
        vehicles_data = None
        power_calculation = None
        
        if self.evcc_client:
            try:
                evcc_state = self.evcc_client.get_state(use_cache=True)
                if evcc_state:
                    evcc_data = {
                        'pv_power': evcc_state.pv_power,
                        'battery_soc': evcc_state.battery_soc,
                        'grid_power': evcc_state.grid_power,
                        'surplus_power': evcc_state.surplus_power,
                        'house_consumption': evcc_state.house_consumption,
                        'timestamp': evcc_state.timestamp.isoformat() if evcc_state.timestamp else None
                    }
                
            except Exception as e:
                status['evcc_error'] = str(e)
                self.logger.error(f"Error getting EVCC state: {e}")
            
            # Get loadpoints and vehicles data separately to avoid one failure affecting the other
            try:
                loadpoints_data = self.evcc_client.get_loadpoints()
            except Exception as e:
                self.logger.error(f"Error getting loadpoints: {e}")
                loadpoints_data = None
                
            try:
                vehicles_data = self.evcc_client.get_vehicles()
            except Exception as e:
                self.logger.error(f"Error getting vehicles: {e}")
                vehicles_data = None
                
            # Calculate power usage and priorities
            try:
                power_calculation = self._get_power_calculation_details()
            except Exception as e:
                self.logger.error(f"Error calculating power details: {e}")
                power_calculation = None
        
        return {
            'thread_status': status,
            'evcc_data': evcc_data,
            'loadpoints': loadpoints_data,
            'vehicles': vehicles_data,
            'power_calculation': power_calculation,
            'enabled': True
        }
    
    def _get_power_calculation_details(self) -> Dict:
        """Get detailed power calculation information for status display"""
        try:
            state = self.evcc_client.get_state(use_cache=True)
            if not state:
                return {'error': 'No EVCC data available'}
            
            # Battery configuration from config or defaults
            max_battery_charge_power = 10000  # 10kW max charging power (could be made configurable)
            battery_power = state.battery_power
            
            # Get loadpoints for vehicle charging calculation
            loadpoints = self.evcc_client.get_loadpoints() or []
            
            # Calculate vehicle charging power and potential
            vehicle_charging_power = 0
            vehicle_max_potential = 0
            charging_vehicles = []
            connected_vehicles = []
            max_vehicle_charge_power = 10000  # 10kW max per vehicle
            
            for i, lp in enumerate(loadpoints):
                vehicle_name = lp.get('vehicle', f'LP{i}')
                charge_power = lp.get('chargePower', 0)
                is_charging = lp.get('charging', False)
                is_connected = lp.get('connected', False)
                is_enabled = lp.get('enabled', False)
                
                if is_charging:
                    # Vehicle is actively charging
                    vehicle_charging_power += charge_power
                    vehicle_max_potential += max_vehicle_charge_power  # Reserve full 10kW capacity
                    charging_vehicles.append({
                        'name': vehicle_name, 
                        'power': charge_power,
                        'status': 'charging',
                        'max_power': max_vehicle_charge_power
                    })
                elif is_connected and is_enabled:
                    # Vehicle is connected but not charging - reserve full capacity
                    vehicle_max_potential += max_vehicle_charge_power
                    connected_vehicles.append({
                        'name': vehicle_name,
                        'status': 'connected',
                        'max_power': max_vehicle_charge_power
                    })
            
            # Get heating element power from config
            heating_element_power = getattr(self.config.evcc, 'heating_element_power', 2000.0)
            power_kw = heating_element_power / 1000.0
            
            # Calculate current heating element power consumption
            current_heating_power = self._get_current_heating_power()
            
            # Correct house consumption by subtracting current heating power
            # to avoid double-counting heating elements in the calculation
            corrected_house_consumption = state.house_consumption - current_heating_power
            
            # Updated surplus calculation logic
            min_battery_soc = getattr(self.config.evcc, 'min_battery_soc_for_heating', 50.0)
            pv_threshold = 10000  # Keep 10kW as threshold for now
            safety_buffer = 500
            
            if state.battery_soc < min_battery_soc and state.pv_power < pv_threshold:
                # Battery < min_soc AND PV < 10kW: no heating
                effective_surplus = 0
                priority_status = "battery_low_pv_low"
                priority_reason = f"Battery {state.battery_soc:.1f}% < {min_battery_soc}% and PV {state.pv_power/1000:.1f}kW < {pv_threshold/1000:.1f}kW: no heating"
            elif state.battery_soc > min_battery_soc:
                # Battery > min_soc: calculate PV - corrected house load
                effective_surplus = max(0, state.pv_power - corrected_house_consumption - safety_buffer)
                priority_status = "heating_allowed"
                priority_reason = f"Battery > {min_battery_soc}%: PV {state.pv_power/1000:.1f}kW - House {corrected_house_consumption/1000:.1f}kW (corrected) = {effective_surplus/1000:.1f}kW available"
            else:
                # Battery < min_soc but PV >= 10kW: calculate PV - corrected house load - 10kW (reserve 10kW for battery)
                effective_surplus = max(0, state.pv_power - corrected_house_consumption - pv_threshold - safety_buffer)
                priority_status = "battery_low_pv_high"
                priority_reason = f"Battery {state.battery_soc:.1f}% < {min_battery_soc}% but PV {state.pv_power/1000:.1f}kW >= {pv_threshold/1000:.1f}kW: PV - House {corrected_house_consumption/1000:.1f}kW - {pv_threshold/1000:.1f}kW = {effective_surplus/1000:.1f}kW available"
            
            # Battery status (for display)
            if battery_power < 0:  # Battery is charging (negative value in EVCC)
                battery_status = "charging"
            elif battery_power > 0:  # Battery is discharging
                battery_status = "discharging"  
            else:
                battery_status = "not_charging"
            
            return {
                'pv_power': state.pv_power,
                'battery_soc': state.battery_soc,
                'battery_power': battery_power,
                'battery_status': battery_status,
                'raw_surplus': state.surplus_power,
                'house_consumption': state.house_consumption,
                'current_heating_power': current_heating_power,
                'corrected_house_consumption': corrected_house_consumption,
                'vehicle_charging_power': vehicle_charging_power,
                'vehicle_max_potential': vehicle_max_potential,
                'charging_vehicles': charging_vehicles,
                'connected_vehicles': connected_vehicles,
                'effective_surplus': effective_surplus,
                'heating_element_power': heating_element_power,
                'priority_status': priority_status,
                'priority_reason': priority_reason,
                'safety_buffer': safety_buffer,
                'min_battery_soc': min_battery_soc,
                'pv_threshold': pv_threshold,
                'max_possible_elements': min(3, max(0, int(effective_surplus / heating_element_power)))
            }
            
        except Exception as e:
            return {'error': str(e)}


class LoadBalancer:
    """Manages load balancing between heating elements"""
    def __init__(self):
        self.elements: Dict[str, HeatingElementState] = {}
        self.rotation_interval = timedelta(hours=1)
        self.last_rotation = datetime.now()

    def register_element(self, element_id: str):
        """Register a heating element for tracking"""
        if element_id not in self.elements:
            self.elements[element_id] = HeatingElementState(element_id)

    def get_priority_list(self) -> List[str]:
        """Get list of elements sorted by usage (least used first)"""
        sorted_elements = sorted(
            self.elements.items(),
            key=lambda x: (x[1].total_runtime, x[1].cycle_count)
        )
        return [e[0] for e in sorted_elements]

    def should_rotate(self) -> bool:
        """Check if elements should be rotated based on time"""
        return datetime.now() - self.last_rotation > self.rotation_interval

    def update_element_state(self, element_id: str, is_on: bool):
        """Update the state of an element"""
        if element_id in self.elements:
            if is_on:
                self.elements[element_id].turn_on()
            else:
                self.elements[element_id].turn_off()

    def get_element_stats(self) -> Dict:
        """Get statistics for all elements"""
        return {
            element_id: {
                'is_on': state.is_on,
                'total_runtime': state.total_runtime.total_seconds() / 3600,  # hours
                'cycle_count': state.cycle_count,
                'current_runtime': state.current_runtime.total_seconds() / 60  # minutes
            }
            for element_id, state in self.elements.items()
        }


@dataclass
@dataclass
class SolarHeatingConfig:
    """Configuration for EVCC integration"""
    evcc_base_url: str
    evcc_timeout: int = 10


@dataclass
class EVCCState:
    """Current state information from EVCC"""
    grid_power: float
    home_power: float
    pv_power: float
    battery_power: float
    battery_soc: float
    battery_configured: bool
    timestamp: datetime
    
    @property
    def house_consumption(self) -> float:
        """Calculate house consumption (alias for home_power)"""
        return self.home_power
    
    @property
    def surplus_power(self) -> float:
        """Calculate current power surplus/deficit"""
        # Positive means surplus (exporting), negative means importing
        return self.pv_power - self.home_power - self.battery_power


class EVCCClient:
    """Client for EVCC REST API"""
    
    def __init__(self, config: SolarHeatingConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.session = requests.Session()
        self.last_successful_read = None
        self.cached_state = None
        self.cached_status_data = None
        self.cache_duration = timedelta(seconds=5)  # Cache for 5 seconds

    def _make_request_with_retry(self, url: str, max_retries: int = 2) -> Optional[requests.Response]:
        """
        Make HTTP request with retry logic and exponential backoff
        
        Args:
            url: URL to request
            max_retries: Maximum number of retry attempts
            
        Returns:
            Response object if successful, None otherwise
        """
        import time
        last_error = None
        
        for attempt in range(max_retries + 1):  # +1 for initial attempt
            try:
                response = self.session.get(url, timeout=self.config.evcc_timeout)
                response.raise_for_status()
                
                if attempt > 0:
                    self.logger.info(f"EVCC API call succeeded on attempt {attempt + 1}")
                return response
                
            except requests.exceptions.Timeout as e:
                last_error = f"Request timeout: {e}"
                self.logger.warning(f"EVCC API timeout on attempt {attempt + 1}: {url}")
                
            except requests.exceptions.ConnectionError as e:
                last_error = f"Connection error: {e}"
                self.logger.warning(f"EVCC API connection error on attempt {attempt + 1}: {url}")
                
            except requests.exceptions.RequestException as e:
                last_error = f"Request error: {e}"
                self.logger.warning(f"EVCC API request error on attempt {attempt + 1}: {e}")
                
            except Exception as e:
                last_error = f"Unexpected error: {e}"
                self.logger.error(f"EVCC API unexpected error on attempt {attempt + 1}: {e}")
            
            # If this wasn't the last attempt, wait before retrying
            if attempt < max_retries:
                # Exponential backoff: 0.5s, 1s
                wait_time = 0.5 * (2 ** attempt)
                self.logger.debug(f"Retrying EVCC API call in {wait_time}s (attempt {attempt + 2}/{max_retries + 1})")
                time.sleep(wait_time)
        
        # All attempts failed
        self.logger.error(f"EVCC API call failed after {max_retries + 1} attempts to {url}. Last error: {last_error}")
        return None

    def get_status_data(self, use_cache: bool = True) -> Optional[Dict]:
        """Get complete EVCC status data from /api/state - cached to avoid multiple API calls"""
        now = datetime.now()
        
        # Return cached status if still valid
        if (use_cache and self.cached_status_data and self.last_successful_read and 
            now - self.last_successful_read < self.cache_duration):
            return self.cached_status_data
        
        try:
            url = f"{self.config.evcc_base_url}/api/state"
            response = self._make_request_with_retry(url, max_retries=2)
            
            if response is None:
                return None
            
            status_data = response.json()
            
            # Cache the complete status response
            self.cached_status_data = status_data
            self.last_successful_read = now
            
            self.logger.debug(f"EVCC status data fetched and cached from {url}")
            return status_data
            
        except (KeyError, ValueError) as e:
            self.logger.error(f"Failed to parse EVCC status data: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error getting EVCC status data: {e}")
            return None

    def get_state(self, use_cache: bool = True) -> Optional[EVCCState]:
        """Get current EVCC state from cached status data"""
        status_data = self.get_status_data(use_cache)
        if not status_data:
            return self.cached_state  # Return last known state if available
        
        try:
            # EVCC API v0.209+ has state data directly at root level (no result wrapper)
            state = EVCCState(
                grid_power=status_data.get('gridPower', 0.0),
                home_power=status_data.get('homePower', 0.0),
                pv_power=status_data.get('pvPower', 0.0),
                battery_power=status_data.get('batteryPower', 0.0),
                battery_soc=status_data.get('batterySoc', 0.0),
                battery_configured=status_data.get('batteryConfigured', False),
                timestamp=datetime.now()
            )
            
            self.cached_state = state
            
            self.logger.debug(f"EVCC state: Grid={state.grid_power:.0f}W, "
                            f"PV={state.pv_power:.0f}W, Home={state.home_power:.0f}W, "
                            f"Battery={state.battery_soc:.1f}%, Surplus={state.surplus_power:.0f}W")
            
            return state
            
        except (KeyError, ValueError) as e:
            self.logger.error(f"Failed to parse EVCC state from cached data: {e}")
            return self.cached_state  # Return last known state if available

    def get_available_power_for_heating(self) -> float:
        """
        Calculate available power for heating using correct formula:
        Available Power = PV Power - Home Power - Current Loadpoint Charging Power
        
        Note: EVCC's residualPower includes current EV charging, but we want 
        the actual surplus available for heating without current EV load.
        """
        try:
            # Get state data using centralized method with retry logic
            status_data = self.get_status_data()
            if status_data is None:
                self.logger.warning("Could not get EVCC status data for power calculation")
                return 0.0
            
            # EVCC API v0.209+ has data directly at root level
            pv_power = status_data.get('pvPower', 0)  # Current PV generation
            home_power = status_data.get('homePower', 0)  # Home consumption
            
            # Calculate total current charging power from all loadpoints
            total_charging_power = 0
            loadpoints = status_data.get('loadpoints', [])
            for lp in loadpoints:
                if isinstance(lp, dict) and lp.get('charging', False):
                    charge_power = lp.get('chargePower', 0)
                    total_charging_power += charge_power
            
            # Available power = PV generation - home consumption - current EV charging
            available_power = pv_power - home_power - total_charging_power
            
            self.logger.debug(f"Power calculation: PV={pv_power}W, Home={home_power}W, " +
                            f"EV_Charging={total_charging_power}W, Available={available_power}W")
            
            return available_power
            
        except Exception as e:
            self.logger.error(f"Error calculating available power for heating: {e}")
            return 0.0

    def get_smart_heating_power_allocation(self) -> Dict:
        """
        Smart power allocation that balances heating and EV charging needs.
        
        Strategy:
        1. Check if EVs are connected and need charging (not at target SoC)
        2. Reserve appropriate power for EV charging based on their needs
        3. Allow heating to use remaining surplus power
        4. Dynamically adjust based on PV production changes
        
        Returns:
        - available_for_heating: Power (W) available for heating elements
        - reserved_for_ev: Power (W) reserved for potential EV charging
        - reasoning: Explanation of the allocation decision
        """
        try:
            # Get current state using centralized method with retry logic
            status_data = self.get_status_data()
            if status_data is None:
                self.logger.warning("Could not get EVCC status data for smart power allocation")
                return {
                    'available_for_heating': 0,
                    'reserved_for_ev': 0,
                    'reasoning': "EVCC data unavailable",
                    'pv_power': 0,
                    'home_power': 0,
                    'current_ev_charging': 0,
                    'base_available': 0,
                    'safety_buffer': 0,
                    'ev_analysis': []
                }
            
            # EVCC API v0.209+ has data directly at root level
            pv_power = status_data.get('pvPower', 0)
            home_power = status_data.get('homePower', 0)
            loadpoints = status_data.get('loadpoints', [])
            vehicles = status_data.get('vehicles', {})
            
            # Calculate base available power
            total_current_charging = sum(lp.get('chargePower', 0) for lp in loadpoints if lp.get('charging', False))
            base_available = pv_power - home_power - total_current_charging
            
            if base_available <= 0:
                return {
                    'available_for_heating': 0,
                    'reserved_for_ev': 0,
                    'reasoning': f"No surplus power available (PV: {pv_power}W, Home: {home_power}W, EV: {total_current_charging}W)",
                    'pv_power': pv_power,
                    'home_power': home_power,
                    'current_ev_charging': total_current_charging,
                    'base_available': base_available,
                    'safety_buffer': 0,
                    'ev_analysis': []
                }
            
            # Analyze EV charging needs
            ev_power_reservation = 0
            ev_analysis = []
            
            for i, lp in enumerate(loadpoints):
                if not isinstance(lp, dict):
                    continue
                    
                is_connected = lp.get('connected', False)
                is_charging = lp.get('charging', False)
                is_enabled = lp.get('enabled', False)
                vehicle_id = lp.get('vehicle', f'loadpoint_{i}')
                current_charge_power = lp.get('chargePower', 0)
                
                if not is_connected:
                    continue
                
                # Get vehicle info if available
                vehicle_info = vehicles.get(vehicle_id, {}) if isinstance(vehicles, dict) else {}
                vehicle_soc = vehicle_info.get('soc', 0)
                target_soc = vehicle_info.get('limitSoc', 100)  # Target SoC limit
                vehicle_capacity = vehicle_info.get('capacity', 50000)  # Wh
                vehicle_name = vehicle_info.get('title', vehicle_id)
                
                # Calculate charging need
                soc_needed = max(0, target_soc - vehicle_soc)
                energy_needed_wh = (soc_needed / 100) * vehicle_capacity
                
                # Determine power reservation strategy
                if is_charging:
                    # Vehicle is actively charging - it already has power allocated
                    reserved_power = max(1000, current_charge_power)  # Reserve at least 1kW for ramp-up
                    reason = f"Currently charging at {current_charge_power}W"
                elif soc_needed > 5:  # Vehicle needs significant charging (>5% SoC)
                    if energy_needed_wh > 10000:  # More than 10kWh needed
                        reserved_power = 6000  # Reserve 6kW for fast charging
                        reason = f"Needs {soc_needed:.1f}% SoC ({energy_needed_wh/1000:.1f}kWh) - reserve 6kW"
                    elif energy_needed_wh > 5000:  # 5-10kWh needed
                        reserved_power = 3000  # Reserve 3kW for moderate charging
                        reason = f"Needs {soc_needed:.1f}% SoC ({energy_needed_wh/1000:.1f}kWh) - reserve 3kW"
                    else:
                        reserved_power = 1500  # Reserve 1.5kW for topping up
                        reason = f"Needs {soc_needed:.1f}% SoC ({energy_needed_wh/1000:.1f}kWh) - reserve 1.5kW"
                else:
                    # Vehicle is nearly full or at target
                    reserved_power = 500  # Small reservation for maintenance charging
                    reason = f"At {vehicle_soc:.1f}% (target {target_soc}%) - minimal reservation"
                
                if is_enabled:
                    ev_power_reservation += reserved_power
                    ev_analysis.append({
                        'name': vehicle_name,
                        'soc': vehicle_soc,
                        'target_soc': target_soc,
                        'energy_needed_wh': energy_needed_wh,
                        'reserved_power': reserved_power,
                        'charging': is_charging,
                        'current_power': current_charge_power,
                        'reason': reason
                    })
            
            # Calculate power allocation
            safety_buffer = 200  # 200W safety margin
            available_after_ev_reservation = base_available - ev_power_reservation - safety_buffer
            heating_power_allocation = max(0, available_after_ev_reservation)
            
            # Generate reasoning
            if ev_power_reservation > 0:
                ev_summary = f"Reserved {ev_power_reservation}W for {len(ev_analysis)} connected EV(s)"
                reasoning = f"{ev_summary}. Available for heating: {heating_power_allocation}W after {safety_buffer}W safety buffer"
            else:
                reasoning = f"No EVs need charging. Available for heating: {heating_power_allocation}W after {safety_buffer}W safety buffer"
            
            result = {
                'available_for_heating': heating_power_allocation,
                'reserved_for_ev': ev_power_reservation,
                'reasoning': reasoning,
                'pv_power': pv_power,
                'home_power': home_power,
                'current_ev_charging': total_current_charging,
                'base_available': base_available,
                'safety_buffer': safety_buffer,
                'ev_analysis': ev_analysis
            }
            
            self.logger.debug(f"Smart power allocation: {result}")
            return result
            
        except (KeyError, ValueError, TypeError) as e:
            self.logger.error(f"Data format error in smart power allocation: {e}")
            return {
                'available_for_heating': 0,
                'reserved_for_ev': 0,
                'reasoning': f"Data format error: {e}",
                'pv_power': 0,
                'home_power': 0,
                'current_ev_charging': 0,
                'base_available': 0,
                'safety_buffer': 0,
                'ev_analysis': []
            }
        except Exception as e:
            self.logger.error(f"Unexpected error in smart power allocation: {e}")
            return {
                'available_for_heating': 0,
                'reserved_for_ev': 0,
                'reasoning': f"Calculation error: {e}",
                'pv_power': 0,
                'home_power': 0,
                'current_ev_charging': 0,
                'base_available': 0,
                'safety_buffer': 0,
                'ev_analysis': []
            }

    def get_loadpoints(self) -> Optional[List[Dict]]:
        """Get EVCC loadpoints (charging stations) information from cached status data"""
        status_data = self.get_status_data()
        if not status_data:
            return None
        
        try:
            # EVCC API v0.209+ has loadpoints directly at root level
            loadpoints = status_data.get('loadpoints', [])
            
            if loadpoints:
                self.logger.info(f"EVCC loadpoints: {len(loadpoints)} found")
                # Log basic info for debugging
                for i, lp in enumerate(loadpoints):
                    if isinstance(lp, dict):
                        title = lp.get('title', f'Loadpoint {i+1}')
                        charging = lp.get('charging', False)
                        connected = lp.get('connected', False)
                        power = lp.get('chargePower', 0)
                        self.logger.debug(f"Loadpoint {i+1}: {title}, Connected: {connected}, Charging: {charging}, Power: {power}W")
            else:
                self.logger.info("No loadpoints found in status response")
            
            return loadpoints
            
        except Exception as e:
            self.logger.error(f"Unexpected error getting EVCC loadpoints from cached data: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None

    def get_vehicles(self) -> Optional[List[Dict]]:
        """Get EVCC vehicles information from cached status data"""
        status_data = self.get_status_data()
        if not status_data:
            return None
        
        try:
            # Get static vehicle configuration
            vehicles_config = status_data.get('vehicles', {})
            # Get dynamic data from loadpoints
            loadpoints = status_data.get('loadpoints', [])
            
            if not vehicles_config:
                return []
            
            # Merge static config with dynamic loadpoint data
            vehicles_list = []
            for vehicle_id, vehicle_config in vehicles_config.items():
                if isinstance(vehicle_config, dict):
                    # Start with static configuration
                    vehicle_info = vehicle_config.copy()
                    vehicle_info['id'] = vehicle_id
                    if 'title' not in vehicle_info:
                        vehicle_info['title'] = vehicle_id
                    
                    # Find corresponding loadpoint data by matching vehicle name/title
                    vehicle_title = vehicle_info.get('title', vehicle_id)
                    for loadpoint in loadpoints:
                        if isinstance(loadpoint, dict):
                            lp_vehicle_title = loadpoint.get('vehicleTitle', '')
                            lp_vehicle_name = loadpoint.get('vehicleName', '')
                            
                            # Match by title or name
                            if (lp_vehicle_title == vehicle_title or 
                                lp_vehicle_name == vehicle_id or 
                                lp_vehicle_title == vehicle_id):
                                
                                # Merge dynamic data from loadpoint
                                vehicle_info['soc'] = loadpoint.get('vehicleSoc', 0)
                                vehicle_info['range'] = loadpoint.get('vehicleRange', 0)
                                vehicle_info['odometer'] = loadpoint.get('vehicleOdometer', 0)
                                vehicle_info['connected'] = loadpoint.get('connected', False)
                                vehicle_info['charging'] = loadpoint.get('charging', False)
                                vehicle_info['chargePower'] = loadpoint.get('chargePower', 0)
                                
                                self.logger.debug(f"Merged loadpoint data for vehicle {vehicle_title}: SoC={vehicle_info['soc']}%, Range={vehicle_info['range']}km")
                                break
                    
                    vehicles_list.append(vehicle_info)
            
            self.logger.info(f"EVCC vehicles: {len(vehicles_list)} found")
            # Log basic info for debugging
            for vehicle in vehicles_list:
                title = vehicle.get('title', 'Unknown')
                soc = vehicle.get('soc', 0)
                range_km = vehicle.get('range', 0)
                capacity = vehicle.get('capacity', 0)
                self.logger.debug(f"Vehicle: {title}, SoC: {soc}%, Range: {range_km}km, Capacity: {capacity}kWh")
            
            return vehicles_list
                
        except Exception as e:
            self.logger.error(f"Unexpected error getting EVCC vehicles from cached data: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None

    def get_session_data(self, loadpoint_id: int = 0) -> Optional[Dict]:
        """Get charging session data for a specific loadpoint"""
        try:
            url = f"{self.config.evcc_base_url}/api/sessions"
            response = self._make_request_with_retry(url, max_retries=2)
            
            if response is None:
                return None
            
            sessions = response.json()
            
            # Filter for specific loadpoint if provided
            if loadpoint_id is not None:
                sessions = [s for s in sessions if s.get('loadpoint') == loadpoint_id]
            
            self.logger.debug(f"EVCC sessions: {len(sessions)} found for loadpoint {loadpoint_id}")
            return sessions
            
        except (KeyError, ValueError) as e:
            self.logger.error(f"Failed to parse EVCC sessions: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error getting EVCC sessions: {e}")
            return None

    def is_healthy(self) -> bool:
        """Check if EVCC is healthy and responding"""
        try:
            url = f"{self.config.evcc_base_url}/api/health"
            # Use retry for health check but with shorter timeout for faster failure detection
            response = self._make_request_with_retry(url, max_retries=1)
            
            if response is None:
                return False
                
            return response.status_code == 200 and response.text.strip() == "OK"
        except Exception:
            return False


_load_balancer = LoadBalancer()

def _get_heating_element_ports(hardware):
    """Get heating element port configurations"""
    heizstab_ports = []
    try:
        # Use the hardware.get_output_by_name method if available
        for heizstab_id in ['heizstab_1', 'heizstab_2', 'heizstab_3']:
            if hasattr(hardware, 'get_output_by_name'):
                try:
                    output_info = hardware.get_output_by_name(heizstab_id)
                    if output_info:
                        heizstab_ports.append({
                            'board': output_info['board'], 
                            'port': output_info['port'], 
                            'description': heizstab_id
                        })
                except Exception:
                    # If get_output_by_name fails, skip this heizstab
                    continue
    except Exception:
        pass
    
    if not heizstab_ports:
        # Fallback to default ports from configuration
        heizstab_ports = [
            {'board': 1, 'port': 0, 'description': 'heizstab_1'},
            {'board': 1, 'port': 1, 'description': 'heizstab_2'},
            {'board': 1, 'port': 2, 'description': 'heizstab_3'},
        ]
    
    return heizstab_ports

def get_evcc_info(evcc_client, logger):
    """Get comprehensive EVCC information including loadpoints and vehicles"""
    result = {
        'state': None,
        'loadpoints': None,
        'vehicles': None,
        'sessions': None,
        'error': None
    }
    
    try:
        # Get basic state
        result['state'] = evcc_client.get_state(use_cache=False)
        
        # Get loadpoints
        result['loadpoints'] = evcc_client.get_loadpoints()
        
        # Get vehicles  
        result['vehicles'] = evcc_client.get_vehicles()
        
        # Get charging sessions (for first loadpoint if available)
        if result['loadpoints'] and len(result['loadpoints']) > 0:
            result['sessions'] = evcc_client.get_session_data(loadpoint_id=0)
        
        logger.info("Successfully retrieved EVCC information")
        
        # Log summary
        if result['state']:
            logger.info(f"EVCC State: PV={result['state'].pv_power:.0f}W, "
                       f"Grid={result['state'].grid_power:.0f}W, "
                       f"Battery={result['state'].battery_soc:.1f}%, "
                       f"Surplus={result['state'].surplus_power:.0f}W")
        
        if result['loadpoints']:
            logger.info(f"Found {len(result['loadpoints'])} loadpoints")
            for i, lp in enumerate(result['loadpoints']):
                status = lp.get('charging', 'unknown')
                power = lp.get('chargePower', 0)
                logger.info(f"  Loadpoint {i}: {status}, Power: {power:.0f}W")
        
        if result['vehicles']:
            logger.info(f"Found {len(result['vehicles'])} vehicles")
            for i, vehicle in enumerate(result['vehicles']):
                name = vehicle.get('title', f'Vehicle {i}')
                soc = vehicle.get('soc', 0)
                logger.info(f"  {name}: SoC {soc:.1f}%")
                
    except Exception as e:
        result['error'] = str(e)
        logger.error(f"Failed to get EVCC info: {e}")
    
    return result

def create_evcc_controller(config, hardware, logger):
    """Factory function to create EVCC controller"""
    if not hasattr(config, 'evcc') or not config.evcc.enable:
        logger.info("EVCC integration disabled in configuration")
        return None
        
    try:
        print("🔄 Creating EVCC controller...")
        controller = EVCCController(config, hardware, logger)
        logger.info(f"EVCC controller created for {config.evcc.base_url}")
        return controller
    except Exception as e:
        logger.error(f"Failed to create EVCC controller: {e}")
        print(f"❌ Failed to create EVCC controller: {e}")
        return None

def control_heating_elements_with_confirmation(evcc_client, hardware, config, logger, controller):
    """
    Control heating elements with confirmation system - requires 2 consecutive checks 
    before making changes to prevent rapid cycling every 30 seconds.
    """
    # Calculate desired number of elements based on current conditions
    desired_elements = _calculate_desired_elements(evcc_client, config, logger)
    
    # Check if this matches our pending action
    if controller.pending_action == desired_elements:
        # Same action as before, increment confirmation counter
        controller.confirmation_count += 1
        logger.info(f"EVCC Confirmation: Desired {desired_elements} elements "
                   f"({controller.confirmation_count}/{controller.required_confirmations} confirmations)")
        
        # If we have enough confirmations, execute the action
        if controller.confirmation_count >= controller.required_confirmations:
            logger.info(f"EVCC Action: Confirmed {desired_elements} elements - executing change")
            _apply_heating_element_changes(desired_elements, hardware, config, logger)
            
            # Reset confirmation system
            controller.pending_action = None
            controller.confirmation_count = 0
    else:
        # Different action, restart confirmation process
        if controller.pending_action is not None:
            logger.info(f"EVCC: Changing target from {controller.pending_action} to {desired_elements} elements - restarting confirmation")
        
        controller.pending_action = desired_elements
        controller.confirmation_count = 1
        logger.info(f"EVCC Pending: {desired_elements} elements "
                   f"(1/{controller.required_confirmations} confirmations)")

def _calculate_desired_elements(evcc_client, config, logger):
    """Calculate how many heating elements should be active based on updated EVCC logic"""
    state = evcc_client.get_state()
    if not state:
        logger.warning("No EVCC data available")
        return 0

    battery_soc = state.battery_soc
    pv_power = state.pv_power
    house_consumption = state.house_consumption
    
    # Get configuration values
    min_battery_soc = getattr(config.evcc, 'min_battery_soc_for_heating', 50.0)
    heating_element_power = getattr(config.evcc, 'heating_element_power', 2000.0)  # Default 2kW per element
    pv_threshold = 10000  # Keep 10kW threshold for now, could be made configurable
    
    safety_buffer = 500  # 500W safety buffer

    # Updated logic implementation using config values
    if battery_soc < min_battery_soc and pv_power < pv_threshold:
        # Battery < min_soc AND PV < 10kW: no heating
        logger.info(f"EVCC: Battery {battery_soc:.1f}% < {min_battery_soc}% and PV {pv_power/1000:.1f}kW < {pv_threshold/1000:.1f}kW - no heating allowed")
        return 0
    elif battery_soc > min_battery_soc:
        # Battery > min_soc: calculate PV - house load
        effective_surplus = max(0, pv_power - house_consumption - safety_buffer)
        logger.info(f"EVCC: Battery {battery_soc:.1f}% > {min_battery_soc}% - PV {pv_power/1000:.1f}kW - House {house_consumption/1000:.1f}kW = {effective_surplus/1000:.1f}kW available")
    else:
        # Battery < min_soc but PV >= 10kW: calculate PV - house load - 10kW (reserve 10kW for battery)
        effective_surplus = max(0, pv_power - house_consumption - pv_threshold - safety_buffer)
        logger.info(f"EVCC: Battery {battery_soc:.1f}% < {min_battery_soc}% but PV {pv_power/1000:.1f}kW >= {pv_threshold/1000:.1f}kW - PV {pv_power/1000:.1f}kW - House {house_consumption/1000:.1f}kW - {pv_threshold/1000:.1f}kW = {effective_surplus/1000:.1f}kW available")

    # Calculate number of elements based on effective surplus and heating element power
    if effective_surplus <= 0:
        logger.info("No surplus power available for heating")
        return 0
    
    # Calculate how many elements we can power based on available surplus
    max_elements = int(effective_surplus / heating_element_power)
    # Limit to maximum of 3 elements
    desired_elements = min(max_elements, 3)
    
    logger.info(f"EVCC: {effective_surplus/1000:.1f}kW surplus / {heating_element_power/1000:.1f}kW per element = {desired_elements} elements")
    
    return desired_elements

def _apply_heating_element_changes(desired_count, hardware, config, logger):
    """Apply the confirmed heating element changes"""
    global _load_balancer

    # Initialize load balancer if needed
    for heizstab_id in ['heizstab_1', 'heizstab_2', 'heizstab_3']:
        _load_balancer.register_element(heizstab_id)

    # Get heating element ports
    heizstab_ports = _get_heating_element_ports(hardware)
    
    # Get prioritized list of elements based on usage
    priority_list = _load_balancer.get_priority_list()
    
    # Check if we should rotate elements
    if _load_balancer.should_rotate():
        logger.info("Rotating heating elements for load balancing")
        _load_balancer.last_rotation = datetime.now()
    
    # Update element states and control outputs
    heizstab_states = {id: False for id in ['heizstab_1', 'heizstab_2', 'heizstab_3']}
    
    # Activate elements according to priority
    for i in range(desired_count):
        if i < len(priority_list):
            heizstab_states[priority_list[i]] = True
    
    # Apply the states to hardware
    for heizstab_id, is_on in heizstab_states.items():
        # Find the matching port configuration
        matching_port = None
        for port in heizstab_ports:
            if port['description'] == heizstab_id:
                matching_port = port
                break
        
        if matching_port:
            hardware.set_output((matching_port['board'], matching_port['port']), is_on)
            _load_balancer.update_element_state(heizstab_id, is_on)
            
            logger.info(f"{heizstab_id} {'ON' if is_on else 'OFF'} "
                       f"(Board {matching_port['board']}, Port {matching_port['port']})")
        else:
            logger.warning(f"No port configuration found for {heizstab_id}")

def control_heating_elements(evcc_client, hardware, config, logger):
    """
    Control heating elements based on EVCC surplus and battery SoC with load balancing.
    Uses priority rotation to evenly distribute wear across heating elements.
    - If battery SoC > 50% and surplus > power_kw: activate heating elements
    - Number of active elements depends on available surplus
    - Load balancing rotates elements to ensure even usage
    """
    global _load_balancer

    # Initialize load balancer if needed
    for heizstab_id in ['heizstab_1', 'heizstab_2', 'heizstab_3']:
        _load_balancer.register_element(heizstab_id)
    state = evcc_client.get_state()
    if not state:
        logger.warning("No EVCC data available, turning off all heating elements.")
        _set_all_heizstaebe(hardware, config, False, logger)
        return

    battery_soc = state.battery_soc
    power_allocation = evcc_client.get_smart_heating_power_allocation()  # Smart EV-aware power allocation
    power_kw = 2.0
    if hasattr(config, 'evcc') and hasattr(config.evcc, 'heating_element_power'):
        try:
            power_kw = config.evcc.heating_element_power / 1000.0  # Convert W to kW
        except Exception:
            pass
    
    power_w = power_kw * 1000  # Convert back to watts for calculations

    # Get heating element ports
    heizstab_ports = _get_heating_element_ports(hardware)

    # Count currently active heating elements
    currently_active_count = 0
    for port_config in heizstab_ports:
        try:
            if hardware.get_output((port_config['board'], port_config['port'])):
                currently_active_count += 1
        except Exception:
            # If we can't read the output state, assume it's off
            pass
    
    # Get available power from smart allocation
    available_for_heating = power_allocation['available_for_heating']
    
    # Calculate adjusted surplus: available heating power + power of currently active elements
    # This represents the total "available" power if we were to turn off all heating elements
    adjusted_surplus = available_for_heating + (currently_active_count * power_w)
    
    # Log current EVCC state for debugging
    logger.info(f"EVCC Control: {power_allocation['reasoning']}")
    logger.info(f"PV={power_allocation['pv_power']:.0f}W, Home={power_allocation['home_power']:.0f}W, "
               f"Battery={battery_soc:.1f}%, Available_for_Heating={available_for_heating:.0f}W, "
               f"Active Elements={currently_active_count}, Adjusted Surplus={adjusted_surplus:.0f}W")

    if battery_soc < 50:
        logger.info(f"Battery SoC {battery_soc:.1f}% < 50%, turning off all heating elements.")
        _set_all_heizstaebe(hardware, config, False, logger)
        return

    # Determine how many elements to turn on based on adjusted surplus
    n_on = 0
    if adjusted_surplus > power_w * 3:
        n_on = 3
    elif adjusted_surplus > power_w * 2:
        n_on = 2
    elif adjusted_surplus > power_w:
        n_on = 1
    
    logger.info(f"EVCC Decision: Activating {n_on} heating elements based on {adjusted_surplus:.0f}W adjusted surplus "
               f"(was {currently_active_count} active, available for heating {available_for_heating:.0f}W)")
    
    # Get prioritized list of elements based on usage
    priority_list = _load_balancer.get_priority_list()
    
    # Check if we should rotate elements
    if _load_balancer.should_rotate():
        logger.info("Rotating heating elements for load balancing")
        _load_balancer.last_rotation = datetime.now()
    
    # Update element states and control outputs
    heizstab_states = {id: False for id in ['heizstab_1', 'heizstab_2', 'heizstab_3']}
    
    # Activate elements according to priority
    for i in range(n_on):
        if i < len(priority_list):
            heizstab_states[priority_list[i]] = True
    
    # Apply the states to hardware
    for heizstab_id, is_on in heizstab_states.items():
        # Find the matching port configuration
        matching_port = None
        for port in heizstab_ports:
            if port['description'] == heizstab_id:
                matching_port = port
                break
        
        if matching_port:
            hardware.set_output((matching_port['board'], matching_port['port']), is_on)
            _load_balancer.update_element_state(heizstab_id, is_on)
            
            # Log the action
            logger.info(f"{heizstab_id} {'ON' if is_on else 'OFF'} "
                       f"(Board {matching_port['board']}, Port {matching_port['port']}, "
                       f"Adjusted Surplus: {adjusted_surplus:.1f}W, Battery: {battery_soc:.1f}%)")
        else:
            logger.warning(f"No port configuration found for {heizstab_id}")
    
    # Periodically log usage statistics
    if n_on > 0:  # Only log stats when elements are active
        stats = _load_balancer.get_element_stats()
        logger.debug("Heating element statistics:")
        for element_id, stat in stats.items():
            logger.debug(f"{element_id}: {stat['total_runtime']:.1f}h total, "
                       f"{stat['cycle_count']} cycles, "
                       f"current: {stat['current_runtime']:.1f}min")

def _set_all_heizstaebe(hardware, config, state: bool, logger):
    # Get heating element ports
    heizstab_ports = _get_heating_element_ports(hardware)
    
    for i, port in enumerate(heizstab_ports):
        hardware.set_output((port['board'], port['port']), state)
        logger.info(f"Heizstab {i+1} {'ON' if state else 'OFF'} (forced)")