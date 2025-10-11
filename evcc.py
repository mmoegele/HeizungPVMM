#!/usr/bin/env python3
"""
EVCC Integration for Heating System Control
=========================================

This module provides integration with EVCC (Electric Vehicle Charge Controller)
to enable solar-optimized heating control. It fetches PV production, grid power,
and battery state from EVCC to inform heating decisions.
"""

import logging
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
        self.cache_duration = timedelta(seconds=5)  # Cache for 5 seconds

    def get_state(self, use_cache: bool = True) -> Optional[EVCCState]:
        """Get current EVCC state"""
        now = datetime.now()
        
        # Return cached state if still valid
        if (use_cache and self.cached_state and self.last_successful_read and 
            now - self.last_successful_read < self.cache_duration):
            return self.cached_state
        
        try:
            url = f"{self.config.evcc_base_url}/api/state"
            response = self.session.get(url, timeout=self.config.evcc_timeout)
            response.raise_for_status()
            
            data = response.json()
            
            # With EVCC v0.207+ the response no longer has a result wrapper
            state = EVCCState(
                grid_power=data.get('gridPower', 0.0),
                home_power=data.get('homePower', 0.0),
                pv_power=data.get('pvPower', 0.0),
                battery_power=data.get('batteryPower', 0.0),
                battery_soc=data.get('batterySoc', 0.0),
                battery_configured=data.get('batteryConfigured', False),
                timestamp=now
            )
            
            self.cached_state = state
            self.last_successful_read = now
            
            self.logger.debug(f"EVCC state: Grid={state.grid_power:.0f}W, "
                            f"PV={state.pv_power:.0f}W, Home={state.home_power:.0f}W, "
                            f"Battery={state.battery_soc:.1f}%, Surplus={state.surplus_power:.0f}W")
            
            return state
            
        except requests.RequestException as e:
            self.logger.error(f"Failed to get EVCC state: {e}")
            return None
        except (KeyError, ValueError) as e:
            self.logger.error(f"Failed to parse EVCC state: {e}")
            return None

    def is_healthy(self) -> bool:
        """Check if EVCC is healthy and responding"""
        try:
            url = f"{self.config.evcc_base_url}/api/health"
            response = self.session.get(url, timeout=5)
            return response.status_code == 200 and response.text.strip() == "OK"
        except:
            return False


_load_balancer = LoadBalancer()

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
    surplus = state.surplus_power
    power_kw = 2.0
    if hasattr(config, 'heating_elements') and config.heating_elements:
        try:
            power_kw = config.heating_elements[0].power_kw
        except Exception:
            pass

    heizstab_ports = [
        config.hardware['outputs']['heizstab_1'],
        config.hardware['outputs']['heizstab_2'],
        config.hardware['outputs']['heizstab_3'],
    ]

    if battery_soc < 50:
        logger.info(f"Battery SoC {battery_soc:.1f}% < 50%, turning off all heating elements.")
        _set_all_heizstaebe(hardware, config, False, logger)
        return

    # Determine how many elements to turn on
    n_on = 0
    if surplus > power_kw * 3:
        n_on = 3
    elif surplus > power_kw * 2:
        n_on = 2
    elif surplus > power_kw:
        n_on = 1
    
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
        port = next(port for port in heizstab_ports if port['description'].lower().replace(' ', '_') == heizstab_id)
        hardware.set_output((port['board'], port['port']), is_on)
        _load_balancer.update_element_state(heizstab_id, is_on)
        
        # Log the action
        logger.info(f"{heizstab_id} {'ON' if is_on else 'OFF'} "
                   f"(Surplus: {surplus:.1f}W, Battery: {battery_soc:.1f}%)")
    
    # Periodically log usage statistics
    if n_on > 0:  # Only log stats when elements are active
        stats = _load_balancer.get_element_stats()
        logger.debug("Heating element statistics:")
        for element_id, stat in stats.items():
            logger.debug(f"{element_id}: {stat['total_runtime']:.1f}h total, "
                       f"{stat['cycle_count']} cycles, "
                       f"current: {stat['current_runtime']:.1f}min")

def _set_all_heizstaebe(hardware, config, state: bool, logger):
    heizstab_ports = [
        config.hardware['outputs']['heizstab_1'],
        config.hardware['outputs']['heizstab_2'],
        config.hardware['outputs']['heizstab_3'],
    ]
    for i, port in enumerate(heizstab_ports):
        hardware.set_output((port['board'], port['port']), state)
        logger.info(f"Heizstab {i+1} {'ON' if state else 'OFF'} (forced)")