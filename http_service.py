#!/usr/bin/env python3
"""
Heating System REST API Server Integration Module
==================================================

Provides HTTP API and web dashboard for the heating system.
Designed to be integrated with the main heating system controller.
"""

import logging
import threading
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
    rate_limit: str = "100 per hour"
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
        
        # Initialize rate limiting
        try:
            self.limiter = Limiter(
                app=self.app,
                key_func=get_remote_address,
                default_limits=[config.rate_limit]
            )
        except Exception as e:
            self.logger.warning(f"Rate limiting not available: {e}")
            self.limiter = None
        
        # Set up routes and error handlers
        self._setup_routes()
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
        
        @self.app.route('/api/health')
        def health_check():
            """Health check endpoint"""
            return jsonify({
                'status': 'healthy',
                'uptime_seconds': (datetime.now() - self.start_time).total_seconds(),
                'version': self.heating_system.config.system_version
            })
        
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