#!/usr/bin/env python3
"""
Heating System REST API Server Integration Module
==================================================

Provides HTTP API and web dashboard for the heating system.
Designed to be integrated with the main heating system controller.
"""

import logging
import threading
import time
from datetime import datetime
from typing import Optional
from pathlib import Path
from dataclasses import dataclass

try:
    from flask import Flask, request, jsonify, abort, send_file
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    from flask_cors import CORS
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False


@dataclass
class HTTPServiceConfig:
    """HTTP service configuration"""
    enable: bool = True
    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False
    require_auth: bool = False
    api_key: str = ""
    rate_limit: str = ""  # Disabled - no rate limiting
    enable_cors: bool = True
    dashboard_file: str = "dashboard.html"


class HTTPService:
    """HTTP service integrated with heating system controller"""
    
    def __init__(self, config: HTTPServiceConfig, heating_system, logger=None):
        """Initialize HTTP service"""
        if not FLASK_AVAILABLE:
            raise ImportError("Flask packages not available. Run: pip install flask flask-limiter flask-cors")
        
        self.config = config
        self.heating_system = heating_system
        self.logger = logger or logging.getLogger(__name__)
        
        # Debug logging for config
        self.logger.info(f"HTTP Service config - require_auth: {config.require_auth}, host: {config.host}, port: {config.port}")
        
        # Initialize Flask
        self.app = Flask(__name__)
        
        # Enable CORS if configured
        if config.enable_cors:
            CORS(self.app)
        
        # Initialize rate limiting (skip if disabled)
        if config.rate_limit and config.rate_limit.strip():
            try:
                self.limiter = Limiter(
                    app=self.app,
                    key_func=get_remote_address,
                    default_limits=[config.rate_limit]
                )
                self.logger.info(f"Rate limiting enabled: {config.rate_limit}")
            except Exception as e:
                self.logger.warning(f"Rate limiting not available: {e}")
                self.limiter = None
        else:
            self.logger.info("Rate limiting disabled")
            self.limiter = None
        
        # EVCC Charger API state (for HTTP plugin integration)
        self._evcc_charger_enabled = False
        self._evcc_charger_max_current = 0  # Amps, set by EVCC via maxcurrent
        self._evcc_charger_max_power = 0    # Watts, set by EVCC via setmaxpower (preferred for heating)
        self._evcc_last_contact = 0.0       # monotonic timestamp of last EVCC API call
        self._evcc_watchdog_timeout = 300   # 5 minutes in seconds
        
        # Set up routes and error handlers
        self._setup_routes()
        
        # Start EVCC watchdog thread
        self._evcc_watchdog_thread = threading.Thread(
            target=self._evcc_watchdog_loop, daemon=True, name='evcc-watchdog'
        )
        self._evcc_watchdog_thread.start()
        self._setup_error_handlers()
        
        # Initialize server thread
        self.server_thread: Optional[threading.Thread] = None
        self.start_time = datetime.now()
    
    def _require_auth(self, f):
        """Authentication decorator - temporarily disabled for debugging"""
        def wrapped(*args, **kwargs):
            # TEMPORARY: Always allow access for debugging
            return f(*args, **kwargs)
            
            # Original auth logic (commented out for debugging)
            # self.logger.debug(f"Auth check: require_auth={self.config.require_auth}")
            # if not self.config.require_auth:
            #     return f(*args, **kwargs)
            # 
            # api_key = request.headers.get('X-API-Key')
            # if not api_key or api_key != self.config.api_key:
            #     self.logger.warning(f"Authentication failed: require_auth={self.config.require_auth}, api_key_provided={bool(api_key)}")
            #     abort(401)
            # 
            # return f(*args, **kwargs)
        wrapped.__name__ = f.__name__
        return wrapped
    
    def _setup_error_handlers(self):
        """Set up error handlers"""
        @self.app.errorhandler(400)
        def bad_request(error):
            return jsonify({
                'error': 'Bad Request',
                'message': str(error.description)
            }), 400
        
        @self.app.errorhandler(401)
        def unauthorized(error):
            return jsonify({
                'error': 'Unauthorized',
                'message': 'Valid API key required'
            }), 401
        
        @self.app.errorhandler(404)
        def not_found(error):
            return jsonify({
                'error': 'Not Found',
                'message': 'Endpoint not found'
            }), 404
    
    def _setup_routes(self):
        """Set up HTTP routes"""
        
        def get_dashboard_path(self):
            """Get absolute path to dashboard file"""
            # First try absolute path
            path = Path(self.config.dashboard_file)
            if path.exists():
                return path
            
            # Try relative to current directory
            current_dir = Path(__file__).parent
            path = current_dir / self.config.dashboard_file
            if path.exists():
                return path
            
            return None
        
        @self.app.route('/')
        @self.app.route('/dashboard.html')
        def serve_dashboard():
            """Serve web dashboard"""
            dashboard_path = get_dashboard_path(self)
            if not dashboard_path:
                self.logger.error(f"Dashboard file not found: {self.config.dashboard_file}")
                return jsonify({'error': 'Dashboard not available'}), 404
            
            return send_file(str(dashboard_path), mimetype='text/html')
        
        @self.app.route('/dashboard_visual.html')
        @self.app.route('/visual')
        def serve_visual_dashboard():
            """Serve visual web dashboard"""
            current_dir = Path(__file__).parent
            dashboard_path = current_dir / 'dashboard_visual.html'
            
            if not dashboard_path.exists():
                self.logger.error(f"Visual dashboard file not found: {dashboard_path}")
                return jsonify({'error': 'Visual dashboard not available'}), 404
            
            return send_file(str(dashboard_path), mimetype='text/html')
        
        @self.app.route('/api/health')
        def health_check():
            """Health check endpoint"""
            return jsonify({
                'status': 'healthy',
                'uptime_seconds': (datetime.now() - self.start_time).total_seconds(),
                'version': self.heating_system.config.system_version
            })
        
        @self.app.route('/api/status')
        def get_status_alias():
            """Get complete system status - simplified alias"""
            try:
                # Build status data directly
                result = {
                    'temperatures': {},
                    'outputs': {},
                    'inputs': {},
                    'controllers': {},
                    'evcc': {},
                    'timestamp': datetime.now().isoformat(),
                    'system_ok': True
                }
                
                # Get temperatures
                if self.heating_system.sensor_manager:
                    try:
                        result['temperatures'] = self.heating_system.sensor_manager.get_valid_temperatures()
                    except Exception as e:
                        self.logger.warning(f"Temperature error: {e}")
                
                # Get I/O states  
                if self.heating_system.hardware:
                    try:
                        for board in [0, 1]:
                            for pin in range(8):
                                key = f"{board}-{pin}"
                                result['outputs'][key] = self.heating_system.hardware.get_output(board, pin)
                                result['inputs'][key] = self.heating_system.hardware.get_input(board, pin)
                    except Exception as e:
                        self.logger.warning(f"Hardware I/O error: {e}")
                
                # Get EVCC data if available
                if hasattr(self.heating_system, 'evcc_controller') and self.heating_system.evcc_controller:
                    try:
                        evcc_state = self.heating_system.evcc_controller.get_state()
                        result['evcc'] = evcc_state.get('evcc_data', {})
                        result['controllers']['evcc_controller'] = evcc_state
                    except Exception as e:
                        self.logger.warning(f"EVCC error: {e}")
                
                return jsonify(result)
                
            except Exception as e:
                self.logger.error(f"Error in status alias: {e}")
                return jsonify({'error': 'Status temporarily unavailable'}), 500
        
        @self.app.route('/api/logs')  
        def get_logs_alias():
            """Get system logs - simplified alias"""
            try:
                logs = []
                # Try to get recent log entries
                import logging
                
                # Get the heating system logger
                heating_logger = logging.getLogger('heating_system')
                
                # For now, return a simple response
                result = {
                    'logs': logs,
                    'count': len(logs),
                    'source': 'heating_system',
                    'timestamp': datetime.now().isoformat()
                }
                
                return jsonify(result)
                
            except Exception as e:
                self.logger.error(f"Error in logs alias: {e}")
                return jsonify({'logs': [], 'error': str(e)}), 500
        
        @self.app.route('/api/io/status')
        @self._require_auth
        def get_io_status():
            """Get IO status"""
            if not self.heating_system.hardware:
                return jsonify({'error': 'Hardware not available'}), 503
            
            outputs = {}
            inputs = {}
            
            hw = self.heating_system.hardware
            
            # Get states from board 0
            for i in range(8):
                outputs[f"0-{i}"] = hw.get_output(0, i)
                inputs[f"0-{i}"] = hw.get_input(0, i)
            
            # Get states from board 1
            for i in range(8):
                outputs[f"1-{i}"] = hw.get_output(1, i)
                inputs[f"1-{i}"] = hw.get_input(1, i)
            
            return jsonify({
                'system_ok': True,
                'outputs': outputs,
                'inputs': inputs,
                'timestamp': datetime.now().isoformat()
            })
        
        @self.app.route('/api/io/output/<int:board>/<int:pin>', methods=['POST'])
        @self._require_auth
        def set_output(board, pin):
            """Set output state"""
            if not self.heating_system.hardware:
                return jsonify({'error': 'Hardware not available'}), 503
            
            if board not in [0, 1] or not 0 <= pin <= 7:
                return jsonify({'error': 'Invalid board or pin'}), 400
            
            data = request.get_json()
            if not isinstance(data, dict) or 'state' not in data:
                return jsonify({'error': 'Missing state parameter'}), 400
            
            state = bool(data['state'])
            
            try:
                self.heating_system.hardware.set_output((board, pin), state)
                return jsonify({
                    'success': True,
                    'board': board,
                    'pin': pin,
                    'state': int(state)
                })
            except Exception as e:
                self.logger.error(f"Error setting output {board}-{pin}: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/buffer/test_pump', methods=['POST'])
        @self._require_auth
        def test_buffer_pump():
            """Test buffer pump manually for debugging"""
            if not hasattr(self.heating_system, 'buffer_load_controller') or not self.heating_system.buffer_load_controller:
                return jsonify({'error': 'Buffer load controller not available'}), 503
            
            data = request.get_json()
            if not isinstance(data, dict) or 'state' not in data:
                return jsonify({'error': 'Missing state parameter (true/false)'}), 400
            
            state = bool(data['state'])
            
            try:
                test_result = self.heating_system.buffer_load_controller.test_pump_manual(state)
                return jsonify(test_result)
            except Exception as e:
                self.logger.error(f"Error testing buffer pump: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/temperatures')
        @self._require_auth
        def get_temperatures():
            """Get temperature readings"""
            if not self.heating_system.sensor_manager:
                return jsonify({'error': 'Sensors not available'}), 503
            
            temps = self.heating_system.sensor_manager.get_valid_temperatures()
            return jsonify({
                'temperatures': temps,  # temps is already Dict[str, float]
                'timestamp': datetime.now().isoformat()
            })

        @self.app.route('/api/system/full_status')
        @self._require_auth
        def get_full_system_status():
            """Get comprehensive system status in one request"""
            result = {
                'timestamp': datetime.now().isoformat(),
                'system_ok': True,
                'temperatures': {},
                'digital_io': {
                    'outputs': {},
                    'inputs': {}
                },
                'controllers': {},
                'evcc': None,
                'errors': []
            }
            
            # Get temperatures
            if self.heating_system.sensor_manager:
                try:
                    result['temperatures'] = self.heating_system.sensor_manager.get_valid_temperatures()
                except Exception as e:
                    result['errors'].append(f"Temperature sensors: {str(e)}")
                    result['system_ok'] = False
            else:
                result['errors'].append("Sensor manager not available")
                result['system_ok'] = False
            
            # Get digital I/O
            if self.heating_system.hardware:
                try:
                    outputs = {}
                    inputs = {}
                    
                    # Get states from both boards
                    for board in [0, 1]:
                        for pin in range(8):
                            key = f"{board}-{pin}"
                            outputs[key] = self.heating_system.hardware.get_output(board, pin)
                            inputs[key] = self.heating_system.hardware.get_input(board, pin)
                    
                    result['digital_io']['outputs'] = outputs
                    result['digital_io']['inputs'] = inputs
                except Exception as e:
                    result['errors'].append(f"Hardware I/O: {str(e)}")
                    result['system_ok'] = False
            else:
                result['errors'].append("Hardware interface not available")
                result['system_ok'] = False
            
            # Get controller status
            try:
                controllers = {}
                
                # Heat exchanger controller
                if hasattr(self.heating_system, 'heat_exchanger') and self.heating_system.heat_exchanger:
                    try:
                        he_state = self.heating_system.heat_exchanger.get_state()
                        controllers['heat_exchanger'] = {
                            'name': 'Heat Exchanger',
                            'pump_active': he_state.get('pump_active', False),
                            'bhkw_active': he_state.get('bhkw_active', False),
                            'last_temperature': he_state.get('current_temp'),
                            'target_temperature': he_state.get('target_temp'),
                            'operation_mode': he_state.get('operation_mode'),
                            'require_bhkw': he_state.get('require_bhkw', True),
                            'thread_healthy': he_state.get('thread_status', {}).get('thread_healthy', False),
                            'thread_status': he_state.get('thread_status', {}).get('thread_alive', False),
                            'error_state': he_state.get('error')
                        }
                    except Exception as e:
                        controllers['heat_exchanger'] = {
                            'name': 'Heat Exchanger', 
                            'error': str(e),
                            'thread_healthy': False
                        }
                
                # Mixer controllers
                if hasattr(self.heating_system, 'mixer_manager') and self.heating_system.mixer_manager:
                    try:
                        mixer_states = self.heating_system.mixer_manager.get_states()
                        
                        # Process each individual mixer
                        for mixer_id, mixer_state in mixer_states.items():
                            controllers[f'mixer_{mixer_id}'] = {
                                'name': f'Mixer {mixer_id.title()}',
                                'mixer_id': mixer_id,
                                'current_temperature': mixer_state.get('current_temperature'),
                                'target_temperature': mixer_state.get('target_temperature'),
                                'max_temperature': mixer_state.get('max_temperature'),
                                'temperature_difference': mixer_state.get('temperature_difference'),
                                'last_action': mixer_state.get('last_action', 'none'),
                                'last_action_time': mixer_state.get('last_action_time'),
                                'running': mixer_state.get('running', False),
                                'error_state': mixer_state.get('error_message')
                            }
                        
                        # Also add a summary controller
                        active_mixers = [mixer_id for mixer_id, state in mixer_states.items() 
                                       if state.get('running', False)]
                        controllers['mixer_manager'] = {
                            'name': 'Mixer Manager',
                            'total_mixers': len(mixer_states),
                            'active_mixers': len(active_mixers),
                            'mixer_list': list(mixer_states.keys()),
                            'active_mixer_list': active_mixers
                        }
                        
                    except Exception as e:
                        controllers['mixer_manager'] = {
                            'name': 'Mixer Manager',
                            'error': str(e)
                        }
                
                # Buffer load controller
                if hasattr(self.heating_system, 'buffer_load_controller') and self.heating_system.buffer_load_controller:
                    try:
                        bl_state = self.heating_system.buffer_load_controller.get_state()
                        controllers['buffer_load_controller'] = {
                            'name': 'Buffer Load Controller',
                            'pump_active': bl_state.get('pump_active', False),
                            'actual_pump_state': bl_state.get('actual_pump_state'),
                            'pump_state_mismatch': bl_state.get('pump_state_mismatch', False),
                            'konrad_sensor': bl_state.get('konrad_sensor', 'N/A'),
                            'michael_sensor': bl_state.get('michael_sensor', 'N/A'), 
                            'konrad_temp': bl_state.get('konrad_temp'),
                            'michael_temp': bl_state.get('michael_temp'),
                            'temp_difference': bl_state.get('temp_difference'),
                            'min_temp_difference': bl_state.get('min_temp_difference'),
                            'pump_port': bl_state.get('pump_port'),
                            'hardware_status': bl_state.get('hardware_status'),
                            'last_action': bl_state.get('last_action', 'none'),
                            'last_check_time': bl_state.get('last_check_time'),
                            'running': bl_state.get('running', False),
                            'error_message': bl_state.get('error_message')
                        }
                    except Exception as e:
                        controllers['buffer_load_controller'] = {
                            'name': 'Buffer Load Controller',
                            'error': str(e)
                        }

                # EVCC controller
                if hasattr(self.heating_system, 'evcc_controller') and self.heating_system.evcc_controller:
                    try:
                        evcc_state = self.heating_system.evcc_controller.get_state()
                        thread_status = evcc_state.get('thread_status', {})
                        evcc_data = evcc_state.get('evcc_data', {})
                        loadpoints_data = evcc_state.get('loadpoints', [])
                        vehicles_data = evcc_state.get('vehicles', [])
                        power_calculation = evcc_state.get('power_calculation', {})
                        
                        # Get current heating element states
                        heating_elements = {}
                        
                        # Define fallback port mappings (from config)
                        fallback_ports = {
                            'heizstab_1': {'board': 1, 'port': 0},
                            'heizstab_2': {'board': 1, 'port': 1}, 
                            'heizstab_3': {'board': 1, 'port': 2}
                        }
                        
                        for heizstab_id in ['heizstab_1', 'heizstab_2', 'heizstab_3']:
                            try:
                                output_info = None
                                
                                # Try to get output info from hardware
                                if hasattr(self.heating_system.hardware, 'get_output_by_name'):
                                    try:
                                        output_info = self.heating_system.hardware.get_output_by_name(heizstab_id)
                                    except Exception:
                                        pass
                                
                                # Fallback to configured ports if get_output_by_name fails
                                if not output_info and heizstab_id in fallback_ports:
                                    output_info = fallback_ports[heizstab_id]
                                
                                if output_info:
                                    is_active = self.heating_system.hardware.get_output(output_info['board'], output_info['port'])
                                    heating_elements[heizstab_id] = {
                                        'active': bool(is_active),
                                        'board': output_info['board'],
                                        'port': output_info['port']
                                    }
                                else:
                                    heating_elements[heizstab_id] = {'active': False, 'error': 'No port mapping found'}
                                    
                            except Exception as e:
                                heating_elements[heizstab_id] = {'active': False, 'error': f'Cannot read state: {str(e)}'}
                        
                        controllers['evcc_controller'] = {
                            'name': 'EVCC Controller',
                            'thread_healthy': thread_status.get('thread_healthy', False),
                            'evcc_connected': thread_status.get('evcc_connected', False),
                            'last_update': thread_status.get('last_update'),
                            'update_count': thread_status.get('update_count', 0),
                            'pv_power': evcc_data.get('pv_power', 0),
                            'battery_soc': evcc_data.get('battery_soc', 0),
                            'surplus_power': evcc_data.get('surplus_power', 0),
                            'heating_elements': heating_elements,
                            'active_elements_count': sum(1 for elem in heating_elements.values() if elem.get('active', False)),
                            'error_state': thread_status.get('last_error'),
                            'loadpoints': loadpoints_data,
                            'vehicles': vehicles_data,
                            'power_calculation': power_calculation,
                            # Debug information
                            'debug_heating_elements': {elem_id: {'active': elem.get('active'), 'error': elem.get('error')} 
                                                     for elem_id, elem in heating_elements.items()}
                        }
                    except Exception as e:
                        controllers['evcc_controller'] = {
                            'name': 'EVCC Controller',
                            'error': str(e),
                            'thread_healthy': False
                        }
                
                # System data reporter
                if hasattr(self.heating_system, 'system_data_reporter') and self.heating_system.system_data_reporter:
                    try:
                        reporter_status = self.heating_system.system_data_reporter.get_status()
                        controllers['system_data_reporter'] = {
                            'name': 'System Data Reporter',
                            'is_running': reporter_status.get('is_running', False),
                            'api_url': reporter_status.get('api_url', 'N/A'),
                            'total_reports_sent': reporter_status.get('total_reports_sent', 0),
                            'total_errors': reporter_status.get('total_errors', 0),
                            'last_report_time': reporter_status.get('last_report_time'),
                            'last_error': reporter_status.get('last_error'),
                            'temperature_sensor_count': reporter_status.get('temperature_sensor_count', 0),
                            'heating_element_count': reporter_status.get('heating_element_count', 0),
                            'pump_count': reporter_status.get('pump_count', 0),
                            'thread_healthy': reporter_status.get('is_running', False),
                            'report_interval': reporter_status.get('report_interval', 30)
                        }
                    except Exception as e:
                        controllers['system_data_reporter'] = {
                            'name': 'System Data Reporter',
                            'error': str(e),
                            'thread_healthy': False,
                            'is_running': False
                        }
                
                result['controllers'] = controllers
            except Exception as e:
                result['errors'].append(f"Controller status: {str(e)}")
            
            # Get EVCC status
            try:
                if hasattr(self.heating_system, 'evcc_controller') and self.heating_system.evcc_controller:
                    # Get status from EVCC controller
                    evcc_status = self.heating_system.evcc_controller.get_state()
                    
                    if evcc_status and evcc_status.get('evcc_data'):
                        evcc_data = evcc_status['evcc_data']
                        thread_status = evcc_status.get('thread_status', {})
                        
                        result['evcc'] = {
                            'enabled': True,
                            'connected': thread_status.get('evcc_connected', False),
                            'pv_power': evcc_data.get('pv_power', 0),
                            'battery_soc': evcc_data.get('battery_soc', 0),
                            'grid_power': evcc_data.get('grid_power', 0),
                            'surplus_power': evcc_data.get('surplus_power', 0),
                            'house_consumption': evcc_data.get('house_consumption', 0),
                            'last_update': evcc_data.get('timestamp'),
                            'thread_healthy': thread_status.get('thread_healthy', False),
                            'update_count': thread_status.get('update_count', 0),
                            'loadpoints': evcc_status.get('loadpoints', []),
                            'vehicles': evcc_status.get('vehicles', [])
                        }
                    else:
                        thread_status = evcc_status.get('thread_status', {}) if evcc_status else {}
                        result['evcc'] = {
                            'enabled': True,
                            'connected': False,
                            'message': thread_status.get('last_error', 'EVCC controller not providing data'),
                            'thread_healthy': thread_status.get('thread_healthy', False)
                        }
                elif hasattr(self.heating_system.config, 'evcc') and self.heating_system.config.evcc.enable:
                    result['evcc'] = {
                        'enabled': True,
                        'connected': False,
                        'message': 'EVCC controller not initialized'
                    }
                else:
                    result['evcc'] = {
                        'enabled': False,
                        'message': 'EVCC integration disabled in configuration'
                    }
            except Exception as e:
                self.logger.error(f"Error getting EVCC status: {e}")
                result['evcc'] = {
                    'enabled': True,
                    'connected': False,
                    'error': str(e)
                }
            
            return jsonify(result)

        @self.app.route('/api/system/logs')
        @self._require_auth
        def get_system_logs():
            """Get recent system logs (excluding API logs)"""
            try:
                import logging
                
                # Get the heating system logger
                heating_logger = logging.getLogger('heating_system')
                
                # First try to get logs from systemd journal (since service runs via systemd)
                try:
                    import subprocess
                    
                    # Try to get logs from systemd journal for heating-control service
                    self.logger.debug("Attempting to read logs from systemd journal...")
                    
                    # Get last 100 lines from heating-control service
                    cmd = ['journalctl', '-u', 'heating-control', '-n', '100', '--no-pager', '--output=short-iso']
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                    
                    if result.returncode == 0 and result.stdout.strip():
                        journal_lines = result.stdout.strip().split('\n')
                        log_entries = []
                        
                        for line in journal_lines:
                            line = line.strip()
                            if not line:
                                continue
                            
                            # Skip systemd metadata lines
                            if line.startswith('-- ') or 'systemd[1]:' in line:
                                continue
                                
                            # Skip HTTP/API related logs
                            line_lower = line.lower()
                            if any(skip_term in line_lower for skip_term in [
                                'werkzeug', 'flask.app', '- - [', 'get /api/', 'post /api/', 
                                'put /api/', 'delete /api/', 'options /api/', 'head /api/',
                                'http request', 'http response'
                            ]):
                                continue
                            
                            log_entries.append(line)
                        
                        if log_entries:
                            return jsonify({
                                'logs': log_entries[-50:],  # Return last 50 entries
                                'count': len(log_entries[-50:]),
                                'source': 'systemd_journal',
                                'service': 'heating-control',
                                'timestamp': datetime.now().isoformat()
                            })
                    
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError) as e:
                    self.logger.warning(f"Could not read systemd journal: {e}")
                except Exception as e:
                    self.logger.warning(f"Error reading systemd journal: {e}")
                
                # Fallback to in-memory logs if journal access fails
                if hasattr(self.heating_system, 'logging_system') and self.heating_system.logging_system:
                    try:
                        # Get recent logs from the logging system (in-memory capture)
                        recent_logs = self.heating_system.logging_system.get_recent_logs(limit=100)
                        
                        # Filter out HTTP/API related logs
                        system_logs = []
                        for log_entry in recent_logs:
                            log_text = str(log_entry.get('message', '')).lower()
                            # Skip HTTP/Flask/Werkzeug related logs but keep system API errors
                            skip_terms = ['flask', 'werkzeug', 'http request', 'http response', 'GET /', 'POST /', 'PUT /', 'DELETE /']
                            if any(skip_term in log_text for skip_term in skip_terms):
                                continue
                            system_logs.append(log_entry)
                        
                        return jsonify({
                            'logs': system_logs,
                            'count': len(system_logs),
                            'source': 'memory_capture',
                            'timestamp': datetime.now().isoformat()
                        })
                    except Exception as e:
                        self.logger.error(f"Error getting logs from logging system: {e}")
                
                # Final fallback - no logs available
                return jsonify({
                    'logs': [],
                    'count': 0,
                    'source': 'none',
                    'error': 'No log source available - journal access failed and no memory logs',
                    'timestamp': datetime.now().isoformat()
                })
                
            except Exception as e:
                self.logger.error(f"Error getting system logs: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/evcc')
        @self._require_auth  
        def get_evcc_status():
            """Get EVCC status and solar information"""
            try:
                # Import EVCC module
                from evcc import EVCCClient, SolarHeatingConfig
                
                # Check if EVCC is enabled in config
                if not hasattr(self.heating_system.config, 'evcc') or not self.heating_system.config.evcc.enable:
                    return jsonify({
                        'enabled': False,
                        'message': 'EVCC integration disabled in configuration'
                    })
                
                # Create EVCC config object
                evcc_config = SolarHeatingConfig(
                    evcc_base_url=self.heating_system.config.evcc.base_url,
                    evcc_timeout=self.heating_system.config.evcc.timeout
                )
                
                # Create EVCC client
                evcc_client = EVCCClient(evcc_config)
                
                # Get EVCC state
                evcc_state = evcc_client.get_state(use_cache=True)
                
                if evcc_state:
                    return jsonify({
                        'enabled': True,
                        'connected': True,
                        'pv_power': evcc_state.pv_power,
                        'battery_soc': evcc_state.battery_soc,
                        'grid_power': evcc_state.grid_power,
                        'surplus_power': evcc_state.surplus_power,
                        'house_consumption': evcc_state.house_consumption,
                        'car_charging_power': getattr(evcc_state, 'car_charging_power', 0),
                        'timestamp': datetime.now().isoformat(),
                        'last_update': evcc_state.timestamp.isoformat() if evcc_state.timestamp else None
                    })
                else:
                    return jsonify({
                        'enabled': True,
                        'connected': False,
                        'message': 'Unable to connect to EVCC',
                        'base_url': self.heating_system.config.evcc.base_url
                    })
                    
            except ImportError:
                return jsonify({
                    'enabled': False,
                    'message': 'EVCC module not available'
                })
            except Exception as e:
                self.logger.error(f"Error getting EVCC status: {e}")
                return jsonify({
                    'enabled': True,
                    'connected': False,
                    'error': str(e)
                }), 500
        
        # Manual Mode Control Endpoints
        @self.app.route('/api/evcc/manual-mode/activate', methods=['POST'])
        def activate_manual_mode():
            """Activate manual mode for EVCC heating control"""
            try:
                if not hasattr(self.heating_system, 'evcc_controller') or not self.heating_system.evcc_controller:
                    return jsonify({'error': 'EVCC controller not available'}), 503
                
                data = request.get_json() or {}
                duration_minutes = data.get('duration_minutes')
                
                result = self.heating_system.evcc_controller.activate_manual_mode(duration_minutes)
                
                if result['success']:
                    return jsonify(result), 200
                else:
                    return jsonify(result), 400
                    
            except Exception as e:
                self.logger.error(f"Error activating manual mode: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/evcc/manual-mode/deactivate', methods=['POST'])
        def deactivate_manual_mode():
            """Deactivate manual mode and return to automatic control"""
            try:
                if not hasattr(self.heating_system, 'evcc_controller') or not self.heating_system.evcc_controller:
                    return jsonify({'error': 'EVCC controller not available'}), 503
                
                result = self.heating_system.evcc_controller.deactivate_manual_mode()
                
                if result['success']:
                    return jsonify(result), 200
                else:
                    return jsonify(result), 400
                    
            except Exception as e:
                self.logger.error(f"Error deactivating manual mode: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/evcc/manual-mode/extend', methods=['POST'])
        def extend_manual_mode():
            """Extend manual mode duration"""
            try:
                if not hasattr(self.heating_system, 'evcc_controller') or not self.heating_system.evcc_controller:
                    return jsonify({'error': 'EVCC controller not available'}), 503
                
                data = request.get_json() or {}
                additional_minutes = data.get('additional_minutes')
                
                if not additional_minutes or additional_minutes <= 0:
                    return jsonify({'error': 'additional_minutes must be a positive integer'}), 400
                
                result = self.heating_system.evcc_controller.extend_manual_mode(additional_minutes)
                
                if result['success']:
                    return jsonify(result), 200
                else:
                    return jsonify(result), 400
                    
            except Exception as e:
                self.logger.error(f"Error extending manual mode: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/evcc/manual-mode/status', methods=['GET'])
        def get_manual_mode_status():
            """Get current manual mode status"""
            try:
                if not hasattr(self.heating_system, 'evcc_controller') or not self.heating_system.evcc_controller:
                    # Old EVCC controller disabled — return inactive status
                    return jsonify({
                        'active': False,
                        'mode': 'evcc_charger_api',
                        'message': 'Heating controlled by EVCC charger API'
                    })
                
                # Use the dedicated manual mode status method
                status = self.heating_system.evcc_controller.get_manual_mode_status()
                
                return jsonify(status)
                    
            except Exception as e:
                self.logger.error(f"Error getting manual mode status: {e}")
                return jsonify({'error': str(e)}), 500
        
        # ============================================================
        # EVCC Charger HTTP Plugin Interface
        # ============================================================
        # These endpoints allow EVCC to control the heating elements
        # as a custom charger/loadpoint via the HTTP plugin.
        # EVCC becomes the controller and calls these endpoints.
        # ============================================================
        
        HEIZSTAB_PORTS = [
            {'board': 1, 'port': 0, 'name': 'heizstab_1'},
            {'board': 1, 'port': 1, 'name': 'heizstab_2'},
            {'board': 1, 'port': 2, 'name': 'heizstab_3'},
        ]
        
        def _charger_get_element_power():
            """Get configured power per heating element in W"""
            try:
                return self.heating_system.config.evcc.heating_element_power
            except Exception:
                return 2000.0
        
        def _charger_get_active_count():
            """Count currently active heating elements"""
            if not self.heating_system.hardware:
                return 0
            count = 0
            for p in HEIZSTAB_PORTS:
                try:
                    if self.heating_system.hardware.get_output(p['board'], p['port']):
                        count += 1
                except Exception:
                    pass
            return count
        
        def _charger_apply_elements(desired_count):
            """Activate exactly desired_count heating elements (0-3)"""
            if not self.heating_system.hardware:
                self.logger.error("EVCC Charger: Hardware not available")
                return
            desired_count = max(0, min(len(HEIZSTAB_PORTS), desired_count))
            for i, p in enumerate(HEIZSTAB_PORTS):
                try:
                    self.heating_system.hardware.set_output(
                        (p['board'], p['port']), i < desired_count
                    )
                except Exception as e:
                    self.logger.error(f"EVCC Charger: Error setting {p['name']}: {e}")
            self.logger.info(f"EVCC Charger: Set {desired_count} heating elements active")
        
        def _charger_update():
            """Apply heating element changes based on current charger state.
            
            Priority: setmaxpower (Watts) > maxcurrent (Amps converted to Watts).
            EVCC uses setmaxpower for heating devices.
            """
            if not self._evcc_charger_enabled:
                _charger_apply_elements(0)
                return
            element_power = _charger_get_element_power()
            # setmaxpower takes priority (direct Watts from EVCC)
            if self._evcc_charger_max_power > 0:
                desired = min(len(HEIZSTAB_PORTS), int(self._evcc_charger_max_power / element_power))
            else:
                # Fallback to maxcurrent: each element is on a separate phase
                # so total power = maxcurrent * 230V * 3 phases
                max_power = self._evcc_charger_max_current * 230 * len(HEIZSTAB_PORTS)
                desired = min(len(HEIZSTAB_PORTS), int(max_power / element_power))
            _charger_apply_elements(desired)
        
        def _charger_get_buffer_temp():
            """Get buffer temperature for EVCC display"""
            if not self.heating_system.sensor_manager:
                return None
            try:
                temps = self.heating_system.sensor_manager.get_valid_temperatures()
                # Use configured sensor, with fallbacks
                configured_sensor = getattr(
                    self.heating_system.config.evcc, 'charger_api_temp_sensor', 'puffer_k_mitte'
                )
                for sensor in [configured_sensor, 'puffer_k_mitte', 'puffer_m_mitte']:
                    if sensor in temps:
                        return temps[sensor]
            except Exception:
                pass
            return None
        
        # --- Read endpoints (EVCC reads these via HTTP GET) ---
        
        @self.app.route('/api/evcc/charger/status')
        def evcc_charger_get_status():
            """Charger status: B=connected/idle, C=charging/heating"""
            self._evcc_last_contact = time.monotonic()
            active = _charger_get_active_count()
            status = "C" if self._evcc_charger_enabled and active > 0 else "B"
            return jsonify({"status": status})
        
        @self.app.route('/api/evcc/charger/enabled')
        def evcc_charger_get_enabled():
            """Is charging/heating currently enabled?"""
            self._evcc_last_contact = time.monotonic()
            return jsonify({"enabled": self._evcc_charger_enabled})
        
        @self.app.route('/api/evcc/charger/power')
        def evcc_charger_get_power():
            """Current heating power in W"""
            self._evcc_last_contact = time.monotonic()
            power = _charger_get_active_count() * _charger_get_element_power()
            return jsonify({"power": power})
        
        @self.app.route('/api/evcc/charger/temp')
        def evcc_charger_get_temp():
            """Current buffer temperature in °C"""
            temp = _charger_get_buffer_temp()
            return jsonify({"temp": temp if temp is not None else 0})
        
        @self.app.route('/api/evcc/charger/templimit')
        def evcc_charger_get_templimit():
            """Temperature limit in °C"""
            try:
                limit = int(self.heating_system.config.safety.max_temperature)
            except Exception:
                limit = 85
            return jsonify({"templimit": limit})
        
        @self.app.route('/api/evcc/charger/maxpower')
        def evcc_charger_get_maxpower():
            """Maximum possible heating power in W"""
            max_power = len(HEIZSTAB_PORTS) * _charger_get_element_power()
            return jsonify({"maxpower": max_power})
        
        # --- Write endpoints (EVCC controls heating via these) ---
        # EVCC HTTP plugin sends plain text body (e.g. "true", "16", "4000")
        # or uses GET with template variables in URL.
        
        def _parse_body_bool():
            """Parse boolean from EVCC HTTP plugin body (plain text or JSON)"""
            data = request.get_json(silent=True)
            if data is not None:
                val = data.get('enable', data.get('value', False))
                return str(val).lower() in ('true', '1', 'on')
            raw = request.get_data(as_text=True).strip().lower()
            return raw in ('true', '1', 'on')
        
        def _parse_body_int():
            """Parse integer from EVCC HTTP plugin body (plain text or JSON)"""
            data = request.get_json(silent=True)
            if data is not None:
                return int(data.get('maxcurrent', data.get('maxpower', data.get('value', 0))))
            raw = request.get_data(as_text=True).strip()
            try:
                return int(float(raw))
            except (ValueError, TypeError):
                return 0
        
        @self.app.route('/api/evcc/charger/enable/<state>')
        def evcc_charger_set_enable_get(state):
            """Enable/disable heating. EVCC GET: /enable/true or /enable/false"""
            self._evcc_charger_enabled = state.lower() in ('true', '1', 'on')
            _charger_update()
            self.logger.info(f"EVCC Charger: enable={self._evcc_charger_enabled}")
            return jsonify({"ok": True, "enabled": self._evcc_charger_enabled})
        
        @self.app.route('/api/evcc/charger/enable', methods=['POST', 'PUT'])
        def evcc_charger_set_enable_post():
            """Enable/disable heating. EVCC POST body: 'true' or 'false'"""
            self._evcc_charger_enabled = _parse_body_bool()
            _charger_update()
            self.logger.info(f"EVCC Charger: enable={self._evcc_charger_enabled}")
            return jsonify({"ok": True, "enabled": self._evcc_charger_enabled})
        
        @self.app.route('/api/evcc/charger/maxcurrent/<int:value>')
        def evcc_charger_set_maxcurrent_get(value):
            """Set max current in A. EVCC GET: /maxcurrent/16"""
            self._evcc_charger_max_current = max(0, value)
            _charger_update()
            active = _charger_get_active_count()
            self.logger.info(
                f"EVCC Charger: maxcurrent={value}A → "
                f"{active} elements ({active * _charger_get_element_power():.0f}W)"
            )
            return jsonify({"ok": True, "maxcurrent": value, "active_elements": active})
        
        @self.app.route('/api/evcc/charger/maxcurrent', methods=['POST', 'PUT'])
        def evcc_charger_set_maxcurrent_post():
            """Set max current in A. EVCC POST body: '16'"""
            value = _parse_body_int()
            self._evcc_charger_max_current = max(0, value)
            _charger_update()
            active = _charger_get_active_count()
            self.logger.info(
                f"EVCC Charger: maxcurrent={value}A → "
                f"{active} elements ({active * _charger_get_element_power():.0f}W)"
            )
            return jsonify({"ok": True, "maxcurrent": value, "active_elements": active})
        
        @self.app.route('/api/evcc/charger/setmaxpower/<int:value>')
        def evcc_charger_set_maxpower_get(value):
            """Set max heating power in W. EVCC GET: /setmaxpower/4000"""
            self._evcc_charger_max_power = max(0, value)
            _charger_update()
            active = _charger_get_active_count()
            self.logger.info(
                f"EVCC Charger: setmaxpower={value}W → "
                f"{active} elements ({active * _charger_get_element_power():.0f}W)"
            )
            return jsonify({"ok": True, "maxpower": value, "active_elements": active})
        
        @self.app.route('/api/evcc/charger/setmaxpower', methods=['POST', 'PUT'])
        def evcc_charger_set_maxpower_post():
            """Set max heating power in W. EVCC POST body: '4000'"""
            value = _parse_body_int()
            self._evcc_charger_max_power = max(0, value)
            _charger_update()
            active = _charger_get_active_count()
            self.logger.info(
                f"EVCC Charger: setmaxpower={value}W → "
                f"{active} elements ({active * _charger_get_element_power():.0f}W)"
            )
            return jsonify({"ok": True, "maxpower": value, "active_elements": active})
    
    def _evcc_watchdog_loop(self):
        """Background thread: turn off heating if EVCC stops communicating"""
        while True:
            time.sleep(60)
            if self._evcc_last_contact == 0.0:
                continue  # No contact yet, nothing to watch
            elapsed = time.monotonic() - self._evcc_last_contact
            if elapsed > self._evcc_watchdog_timeout and self._evcc_charger_enabled:
                self.logger.warning(
                    f"EVCC watchdog: No contact for {elapsed:.0f}s, "
                    f"turning off all heating elements"
                )
                self._evcc_charger_enabled = False
                self._evcc_charger_max_current = 0
                self._evcc_charger_max_power = 0
                if self.heating_system and self.heating_system.hardware:
                    for p in [{'board': 1, 'port': 0}, {'board': 1, 'port': 1}, {'board': 1, 'port': 2}]:
                        try:
                            self.heating_system.hardware.set_output((p['board'], p['port']), False)
                        except Exception:
                            pass
    
    def start(self):
        """Start HTTP server in a background thread"""
        def run_server():
            self.app.run(
                host=self.config.host,
                port=self.config.port,
                debug=self.config.debug,
                use_reloader=False  # Important: disable reloader in thread
            )
        
        self.server_thread = threading.Thread(
            target=run_server,
            name="HTTPService",
            daemon=True  # Thread will be killed when main program exits
        )
        self.server_thread.start()
        self.logger.info(f"HTTP service started on {self.config.host}:{self.config.port}")
    
    def stop(self):
        """Stop HTTP server"""
        # Flask development server doesn't have a clean shutdown method
        # The daemon thread will be killed when the main program exits
        self.logger.info("HTTP service stopping")