#!/usr/bin/env python3
"""Heating System Main Entry Point"""

import sys
import argparse
import logging
import time
from pathlib import Path
from datetime import datetime
import signal
import threading

try:
    import logging_system
    from config import HeatingConfig, load_complete_config
    from logging_system import HeatingSystemLogger
    from hardware import create_hardware_controller
    from sensors import create_sensor_manager
    from gpio import apply_gpio_patch, test_gpio_functionality
    from memory_monitor import MemoryMonitor
    from http_service import HTTPService, HTTPServiceConfig
    from mixer_controller import MixerManager
    from heat_exchanger import create_heat_exchanger_controller
    from buffer_load_controller import create_buffer_load_controller
    from evcc import create_evcc_controller
    from system_data_reporter import create_system_data_reporter
    print("Logging system loaded from:", logging_system.__file__)
    print("✅ All core modules imported successfully")
except ImportError as e:
    print(f"❌ Failed to import heating system modules: {e}")
    sys.exit(1)

class HeatingSystemMain:
    def __init__(self, config_file: str = "heating_config.yaml"):
        self.config_file = Path(config_file)
        self.config = None
        self.logger_system = None
        self.logger = None
        self.hardware = None
        self.sensor_manager = None
        self.mixer_manager = None
        self.heat_exchanger = None
        self.buffer_load_controller = None
        self.evcc_controller = None
        self.system_data_reporter = None
        self.running = False
        self.memory_monitor = None
        
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        if self.logger:
            self.logger.info(f"Received signal {signum}, initiating graceful shutdown")
        else:
            print(f"Received signal {signum}, initiating graceful shutdown")
        self.running = False
        
        # Stop HTTP service if it's running
        if hasattr(self, 'http_service') and self.http_service:
            self.http_service.stop()
    
    def _check_and_restart_threads(self):
        """Monitor and restart critical threads if they die"""
        try:
            # Check system data reporter thread
            if self.system_data_reporter:
                try:
                    reporter_status = self.system_data_reporter.get_status()
                    if not reporter_status['is_running']:
                        self.logger.warning("🔄 System data reporter stopped, restarting...")
                        try:
                            self.system_data_reporter.start()
                            self.logger.info("✅ System data reporter restarted successfully")
                        except Exception as e:
                            self.logger.error(f"❌ Failed to restart system data reporter: {e}")
                except Exception as e:
                    self.logger.error(f"❌ Error checking system data reporter: {e}")

            # Check buffer load controller thread
            if self.buffer_load_controller:
                if hasattr(self.buffer_load_controller, 'thread') and hasattr(self.buffer_load_controller, 'running'):
                    if self.buffer_load_controller.running and (
                        not self.buffer_load_controller.thread or 
                        not self.buffer_load_controller.thread.is_alive()
                    ):
                        self.logger.warning("🔄 Buffer load controller thread died, restarting...")
                        try:
                            self.buffer_load_controller.stop()  # Clean stop
                            time.sleep(1)
                            self.buffer_load_controller.start()  # Restart
                            self.logger.info("✅ Buffer load controller thread restarted successfully")
                        except Exception as e:
                            self.logger.error(f"❌ Failed to restart buffer load controller: {e}")
            
            # Check EVCC controller thread
            if self.evcc_controller:
                try:
                    if hasattr(self.evcc_controller, 'is_thread_healthy'):
                        if not self.evcc_controller.is_thread_healthy():
                            thread_status = self.evcc_controller.get_thread_status() if hasattr(self.evcc_controller, 'get_thread_status') else {}
                            self.logger.warning(f"🔄 EVCC controller thread unhealthy: {thread_status}")
                            
                            try:
                                self.evcc_controller.stop()  # Clean stop
                                time.sleep(1)
                                self.evcc_controller.start()  # Restart
                                self.logger.info("✅ EVCC controller thread restarted successfully")
                            except Exception as e:
                                self.logger.error(f"❌ Failed to restart EVCC controller: {e}")
                except Exception as e:
                    self.logger.error(f"❌ Error checking EVCC controller thread: {e}")

            # Check heat exchanger thread (enhanced monitoring)
            if self.heat_exchanger:
                try:
                    # Use enhanced thread health checking
                    if hasattr(self.heat_exchanger, 'is_thread_healthy'):
                        if not self.heat_exchanger.is_thread_healthy():
                            thread_status = self.heat_exchanger.get_thread_status() if hasattr(self.heat_exchanger, 'get_thread_status') else {}
                            self.logger.warning(f"🔄 Heat exchanger thread unhealthy: {thread_status}")
                            
                            try:
                                self.heat_exchanger.stop()  # Clean stop
                                time.sleep(1)
                                self.heat_exchanger.start()  # Restart
                                self.logger.info("✅ Heat exchanger thread restarted successfully")
                            except Exception as e:
                                self.logger.error(f"❌ Failed to restart heat exchanger: {e}")
                    
                    # Fallback to old method if new methods not available
                    elif hasattr(self.heat_exchanger, 'thread') and hasattr(self.heat_exchanger, 'running'):
                        if self.heat_exchanger.running and (
                            not self.heat_exchanger.thread or 
                            not self.heat_exchanger.thread.is_alive()
                        ):
                            self.logger.warning("🔄 Heat exchanger thread died, restarting...")
                            try:
                                self.heat_exchanger.stop()  # Clean stop
                                time.sleep(1)
                                self.heat_exchanger.start()  # Restart
                                self.logger.info("✅ Heat exchanger thread restarted successfully")
                            except Exception as e:
                                self.logger.error(f"❌ Failed to restart heat exchanger: {e}")
                                
                except Exception as e:
                    self.logger.error(f"❌ Error checking heat exchanger thread: {e}")
            
            # Check mixer controller threads
            if self.mixer_manager and hasattr(self.mixer_manager, 'check_and_restart_threads'):
                try:
                    restart_status = self.mixer_manager.check_and_restart_threads()
                    # Log summary if any mixers were restarted
                    restarted_count = sum(restart_status.values())
                    if restarted_count > 0:
                        self.logger.info(f"📊 Mixer thread monitoring: {restarted_count} threads restarted")
                except Exception as e:
                    self.logger.error(f"❌ Error checking mixer threads: {e}")
            
            # Check HTTP service thread
            if hasattr(self, 'http_service') and self.http_service:
                try:
                    if hasattr(self.http_service, 'server_thread') and self.http_service.server_thread:
                        if not self.http_service.server_thread.is_alive():
                            self.logger.warning("🔄 HTTP service thread died, restarting...")
                            try:
                                self.http_service.stop()  # Clean stop
                                time.sleep(1) 
                                self.http_service.start()  # Restart
                                self.logger.info("✅ HTTP service thread restarted successfully")
                            except Exception as e:
                                self.logger.error(f"❌ Failed to restart HTTP service: {e}")
                except Exception as e:
                    self.logger.error(f"❌ Error checking HTTP service thread: {e}")
                    
        except Exception as e:
            self.logger.error(f"❌ Error in thread monitoring: {e}")
            # Don't let thread monitoring crash the main loop
    
    def initialize(self) -> bool:
        try:
            print(f"🔧 Initializing heating system from {self.config_file}")
            
            if not self.config_file.exists():
                print(f"❌ Configuration file not found: {self.config_file}")
                return False
            
            self.config, _ = load_complete_config(self.config_file)
            print(f"✅ Configuration loaded: {self.config.system_name} v{self.config.system_version}")
            
            self.config.validate()
            print("✅ Configuration validation passed")
            
            log_dir = Path("/var/log/heating")
            self.logger_system = HeatingSystemLogger("INFO", log_dir)
            # Defensive check: some environments may produce an object
            # without the expected attribute (stale bytecode or partial init).
            if not hasattr(self.logger_system, "main_logger"):
                print("⚠️ HeatingSystemLogger has no 'main_logger' attribute - dumping diagnostics:")
                try:
                    import inspect, logging_system
                    print("logging_system module file:", getattr(logging_system, "__file__", "<unknown>"))
                    print("HeatingSystemLogger in module:", getattr(logging_system, "HeatingSystemLogger", None))
                    print("logger_system object dir:", dir(self.logger_system))
                except Exception as diag_e:
                    print("Failed to gather diagnostics:", diag_e)
                # Fallback to a basic logger so system can continue for debugging
                self.logger = logging.getLogger("heating.main")
            else:
                self.logger = self.logger_system.main_logger
            
            self.logger_system.log_system_startup(
                self.config.system_version, 
                str(self.config_file)
            )
            
            # Determine mock mode - use config setting
            mock_mode = self.config.mock_hardware
                        
            self.hardware = create_hardware_controller(
                board_count=self.config.piface_board_count,
                logger=self.logger,
                mock_mode=mock_mode
            )
            
            # Turn off all outputs at startup for safety
            self.hardware.turn_off_all_outputs()
            
            self.sensor_manager = create_sensor_manager(self.config, self.logger_system)
            
            # Initialize mixer controller
            self.mixer_manager = MixerManager(
                config=self.config,
                hardware=self.hardware,
                sensor_manager=self.sensor_manager
            )
            print("✅ Mixer manager initialized")
            
            # Initialize heat exchanger controller (now self-threaded)
            self.heat_exchanger = create_heat_exchanger_controller(
                config=self.config,
                hardware=self.hardware,
                sensor_manager=self.sensor_manager,
                logger=self.logger
            )
            print("✅ Heat exchanger controller initialized and thread started")
            
            # Start mixer controllers
            self.mixer_manager.start_all()
            print("✅ Mixer controllers started")
            
            # Initialize and start buffer load controller
            self.buffer_load_controller = create_buffer_load_controller(
                config=self.config,
                hardware=self.hardware,
                sensor_manager=self.sensor_manager,
                logger=self.logger
            )
            
            # Start buffer load controller (it manages its own thread)
            self.buffer_load_controller.start()
            print("✅ Buffer load controller initialized and started")
            
            # Start heat exchanger controller (it manages its own thread)  
            self.heat_exchanger.start()
            print("✅ Heat exchanger controller initialized and started")
            
            # Initialize and start system data reporter
            try:
                self.logger.info(f"System data reporter configuration check: enabled={self.config.system_data_reporter.enable}")
                if self.config.system_data_reporter.enable:
                    self.logger.info(f"Creating system data reporter for API: {self.config.system_data_reporter.api_url}")
                    self.system_data_reporter = create_system_data_reporter(
                        config=self.config,
                        sensor_manager=self.sensor_manager,
                        hardware_controller=self.hardware,
                        api_url=self.config.system_data_reporter.api_url,
                        report_interval=self.config.system_data_reporter.report_interval
                    )
                    self.logger.info("System data reporter object created successfully")
                    
                    # Test API connection before starting (non-blocking)
                    self.logger.info(f"Testing API connection to {self.config.system_data_reporter.api_url}")
                    try:
                        api_connection_ok = self.system_data_reporter.test_api_connection()
                        self.logger.info(f"API connection test completed: {api_connection_ok}")
                        
                        if api_connection_ok:
                            self.system_data_reporter.start()
                            print(f"✅ System data reporter initialized and started (reporting to {self.config.system_data_reporter.api_url})")
                            self.logger.info(f"System data reporter successfully started")
                        else:
                            # Start anyway - it will retry connections during operation
                            self.system_data_reporter.start()
                            print(f"⚠️ System data reporter started despite API connection issues - will retry during operation")
                            self.logger.info(f"System data reporter started despite API connection issues - will retry during operation")
                    except Exception as api_test_error:
                        # Start anyway - don't let API issues block system startup
                        self.logger.warning(f"Exception during API connection test: {api_test_error}")
                        self.system_data_reporter.start()
                        print(f"⚠️ System data reporter started despite API test error - will retry during operation")
                        self.logger.info(f"System data reporter started despite API test error: {api_test_error}")
                        
                else:
                    print("ℹ️ System data reporter disabled in configuration")
                    self.logger.info("System data reporter disabled in configuration")
            except Exception as e:
                self.logger.error(f"Failed to initialize system data reporter: {e}")
                self.logger.exception("Full system data reporter initialization error:")
                print(f"❌ System data reporter initialization failed: {e}")
                # Continue with startup even if reporter fails
                self.system_data_reporter = None
            
            temperatures = self.sensor_manager.get_valid_temperatures()
            print(f"✅ Initial sensor check: {len(temperatures)} sensors responding")
            
            # Initialize memory monitor
            self.memory_monitor = MemoryMonitor(max_memory_mb=500, check_interval=300)
            self.memory_monitor.start_monitoring()
            print("✅ Memory monitor initialized")
            
            # Initialize EVCC controller if enabled
            print("🔄 Initializing EVCC controller...")
            self.evcc_controller = create_evcc_controller(self.config, self.hardware, self.logger)
            if self.evcc_controller:
                print("🔄 Starting EVCC controller thread...")
                self.evcc_controller.start()
                print(f"✅ EVCC controller initialized and started for {self.config.evcc.base_url}")
            else:
                print("ℹ️ EVCC integration disabled or failed to initialize")
            
            # Initialize HTTP service if enabled
            print("🔄 Initializing HTTP service...")
            if self.config.http_service.enable:
                try:
                    http_config = HTTPServiceConfig(
                        host=self.config.http_service.host,
                        port=self.config.http_service.port,
                        debug=self.config.http_service.debug,
                        require_auth=self.config.http_service.require_auth,
                        api_key=self.config.http_service.api_key,
                        rate_limit=self.config.http_service.rate_limit,
                        enable_cors=self.config.http_service.enable_cors,
                        dashboard_file=self.config.http_service.dashboard_file
                    )
                    self.http_service = HTTPService(
                        config=http_config,
                        heating_system=self,
                        logger=self.logger
                    )
                    self.http_service.start()
                    print(f"✅ HTTP service started on port {http_config.port}")
                except Exception as e:
                    self.logger.error(f"Failed to initialize HTTP service: {e}")
                    print(f"⚠️ HTTP service initialization failed: {e}")
                    # Continue anyway as this is not critical
            else:
                print("ℹ️ HTTP service disabled in configuration")
            
            return True
            
        except Exception as e:
            print(f"❌ Initialization failed: {e}")
            if self.logger:
                self.logger.error(f"Initialization failed: {e}")
            return False
    
    def run(self) -> int:
        if not self.initialize():
            return 1
        
        try:
            print("🔥 Starting heating system...")
            self.running = True
            
            print("🔄 Main control loop started")
            print("Press Ctrl+C to stop")
            
            loop_count = 0
            while self.running:
                temperatures = self.sensor_manager.get_valid_temperatures()
                
                if loop_count % 10 == 0:
                    temp_summary = ", ".join([f"{k}: {v:.1f}°C" for k, v in list(temperatures.items())[:3]])
                    if len(temperatures) > 3:
                        temp_summary += f" (and {len(temperatures)-3} more)"
                    print(f"🌡️ Temperatures: {temp_summary}")
                    
                    # Log mixer states periodically
                    mixer_states = self.mixer_manager.get_states()
                    for mixer_id, state in mixer_states.items():
                        # Skip non-mixer entries like 'update_interval'
                        if isinstance(state, dict) and 'current_temperature' in state:
                            self.logger.info(
                                f"Mixer {mixer_id}: {state['current_temperature']:.1f}°C "
                                f"-> {state['target_temperature']:.1f}°C"
                            )
                
                # Get main loop interval (default to 5 seconds if not configured)
                main_loop_interval = getattr(self.config, 'main_loop_interval', None)
                if main_loop_interval is None:
                    main_loop_interval = getattr(self.config, 'system_control', {}).get('main_loop_interval', 5)
                
                # Check and restart threads every 10 loops (every ~50 seconds)
                if loop_count % 10 == 0:
                    self._check_and_restart_threads()
                
                loop_count += 1
                time.sleep(main_loop_interval)
                
        except KeyboardInterrupt:
            print("\n🛑 Shutdown requested by user")
            return self.shutdown()
        except Exception as e:
            import traceback
            print(f"❌ Fatal error: {e}")
            if self.logger:
                self.logger.critical(f"Fatal error: {e}")
                # Only show full traceback in debug mode
                if self.logger.isEnabledFor(logging.DEBUG):
                    traceback.print_exc()
                    self.logger.critical(f"Full traceback: {traceback.format_exc()}")
            else:
                # If no logger available, check if debug mode by looking at config
                if hasattr(self, 'config') and hasattr(self.config, 'logging') and self.config.logging.level == "DEBUG":
                    traceback.print_exc()
            return 1
    
    def shutdown(self) -> int:
        try:
            print("🔄 Shutting down heating system...")
            self.running = False
            
            if self.memory_monitor:
                self.memory_monitor.stop_monitoring()
                print("✅ Memory monitor stopped")
            
            # Clean up system data reporter
            if self.system_data_reporter:
                self.system_data_reporter.stop()
                print("✅ System data reporter stopped")
                
            # Clean up EVCC controller
            if self.evcc_controller:
                self.evcc_controller.stop()
                print("✅ EVCC controller stopped")
                
            # Clean up heat exchanger (now self-managed)
            if self.heat_exchanger:
                self.heat_exchanger.stop()
                print("✅ Heat exchanger controller stopped")
            
            # Clean up mixer manager
            if self.mixer_manager:
                self.mixer_manager.stop_all()
                print("✅ Mixer controllers stopped")
                
            # Clean up buffer load controller
            if self.buffer_load_controller:
                self.buffer_load_controller.stop()
                print("✅ Buffer load controller stopped")
                
            if self.hardware:
                # Turn off all outputs before disposing
                self.hardware.turn_off_all_outputs()
                self.hardware.dispose()
                print("✅ Hardware disposed")
            
            if self.logger_system:
                self.logger_system.log_system_shutdown("User requested shutdown")
                print("✅ Shutdown logged")
            
            print("✅ Heating system shutdown complete")
            return 0
            
        except Exception as e:
            print(f"❌ Error during shutdown: {e}")
            return 1

def run_gpio_test():
    print("🔧 GPIO Functionality Test")
    print("=" * 40)
    
    patch_result = apply_gpio_patch()
    print(f"GPIO patch applied: {'✅ Yes' if patch_result else '❌ No'}")
    
    test_result = test_gpio_functionality()
    print(f"GPIO test result: {'✅ Pass' if test_result else '❌ Fail'}")
    
    return 0 if test_result else 1

def main():
    parser = argparse.ArgumentParser(description="Modular Heating System Controller")
    parser.add_argument('--config', default='heating_config.yaml', help='Configuration file')
    parser.add_argument('--demo', action='store_true', help='Run in demo mode')
    parser.add_argument('--test-gpio', action='store_true', help='Test GPIO functionality')
    parser.add_argument('--version', action='version', version='Heating System 2.0.0')
    
    args = parser.parse_args()
    
    print("🔥 Modular Heating System Controller 2.0.0")
    print("=" * 50)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if args.test_gpio:
        return run_gpio_test()
    
    try:
        system = HeatingSystemMain(args.config)
        
        if args.demo:
            print("🧪 Demo mode enabled - using mock hardware")
        
        return system.run()
        
    except Exception as e:
        print(f"❌ Failed to start heating system: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
