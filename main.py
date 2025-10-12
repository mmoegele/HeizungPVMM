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
        self.heat_exchanger_thread = None
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
            
            self.hardware = create_hardware_controller(
                self.config.piface_board_count,
                self.logger,
                self.config.mock_hardware
            )
            
            # Enhanced hardware status display
            print(f"✅ Hardware controller initialized ({self.config.piface_board_count} boards)")
            if hasattr(self.hardware, 'run_board_diagnostics'):
                diag = self.hardware.run_board_diagnostics()
                print(f"   🔧 GPIO patch: {'✅' if diag['gpio_patch_applied'] else '❌'}")
                print(f"   🎭 Mock mode: {'✅' if diag['mock_mode'] else '❌'}")
                
                # Show board status
                board_status = []
                for board_id, status in diag['boards'].items():
                    if status['available']:
                        board_status.append(f"B{board_id}:✅")
                    else:
                        board_status.append(f"B{board_id}:❌")
                print(f"   📡 Boards: {' '.join(board_status)}")
            else:
                print(f"   ⚠️  No diagnostics available for {type(self.hardware).__name__}")
            
            self.sensor_manager = create_sensor_manager(self.config, self.logger_system)
            print("✅ Sensor manager initialized")
            
            # Initialize mixer controller
            self.mixer_manager = MixerManager(
                config=self.config,
                hardware=self.hardware,
                sensor_manager=self.sensor_manager
            )
            print("✅ Mixer manager initialized")
            
            # Initialize heat exchanger controller
            self.heat_exchanger = create_heat_exchanger_controller(
                config=self.config,
                hardware=self.hardware,
                sensor_manager=self.sensor_manager,
                logger=self.logger
            )
            
            # Start heat exchanger in its own thread with proper interval
            def heat_exchanger_loop():
                while self.running:
                    if self.heat_exchanger:
                        updated = self.heat_exchanger.update()
                        if not updated:
                            # Sleep a short time if no update was needed
                            time.sleep(0.1)
                    else:
                        time.sleep(1)
                        
            self.heat_exchanger_thread = threading.Thread(
                target=heat_exchanger_loop,
                name="HeatExchangerThread",
                daemon=True
            )
            self.heat_exchanger_thread.start()
            print("✅ Heat exchanger controller initialized and thread started")
            
            # Start mixer manager in its own thread with proper interval
            def mixer_loop():
                while self.running:
                    if self.mixer_manager:
                        updated = self.mixer_manager.update()
                        if not updated:
                            # Sleep a short time if no update was needed
                            time.sleep(0.1)
                    else:
                        time.sleep(1)
                        
            self.mixer_thread = threading.Thread(
                target=mixer_loop,
                name="MixerThread",
                daemon=True
            )
            self.mixer_thread.start()
            print("✅ Mixer manager thread started")
            
            # Initialize buffer load controller
            self.buffer_load_controller = create_buffer_load_controller(
                config=self.config,
                hardware=self.hardware,
                sensor_manager=self.sensor_manager,
                logger=self.logger
            )
            
            # Start buffer load controller in its own thread with proper interval
            def buffer_load_loop():
                while self.running:
                    if self.buffer_load_controller:
                        updated = self.buffer_load_controller.update()
                        if not updated:
                            # Sleep a short time if no update was needed
                            time.sleep(0.1)
                    else:
                        time.sleep(1)
                        
            self.buffer_load_thread = threading.Thread(
                target=buffer_load_loop,
                name="BufferLoadThread",
                daemon=True
            )
            self.buffer_load_thread.start()
            print("✅ Buffer load controller initialized and thread started")
            
            temperatures = self.sensor_manager.get_valid_temperatures()
            print(f"✅ Initial sensor check: {len(temperatures)} sensors responding")
            
            # Initialize memory monitor
            self.memory_monitor = MemoryMonitor(max_memory_mb=500, check_interval=300)
            self.memory_monitor.start_monitoring()
            print("✅ Memory monitor initialized")
            
            # Initialize HTTP service if enabled
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
                
                loop_count += 1
                time.sleep(self.config.main_loop_interval)
                
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
                
            # Clean up heat exchanger
            if self.heat_exchanger:
                self.heat_exchanger.dispose()
                if hasattr(self, 'heat_exchanger_thread') and self.heat_exchanger_thread and self.heat_exchanger_thread.is_alive():
                    self.heat_exchanger_thread.join(timeout=2)
                print("✅ Heat exchanger controller disposed")
            
            # Clean up mixer manager
            if self.mixer_manager:
                self.mixer_manager.dispose()
                if hasattr(self, 'mixer_thread') and self.mixer_thread and self.mixer_thread.is_alive():  
                    self.mixer_thread.join(timeout=2)
                print("✅ Mixer manager disposed")
                
            # Clean up buffer load controller
            if self.buffer_load_controller:
                self.buffer_load_controller.dispose()
                if hasattr(self, 'buffer_load_thread') and self.buffer_load_thread and self.buffer_load_thread.is_alive():
                    self.buffer_load_thread.join(timeout=2)
                print("✅ Buffer load controller disposed")
                
            if self.hardware:
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
