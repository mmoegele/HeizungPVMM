#!/usr/bin/env python3
"""Heating System Main Entry Point"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime
import signal

try:
    from config import HeatingConfig, load_complete_config
    from logging_system import HeatingSystemLogger
    from hardware import create_hardware_controller
    from sensors import create_sensor_manager
    from gpio_fix import apply_gpio_patch, test_gpio_functionality
    from memory_monitor import MemoryMonitor
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
        self.running = False
        self.memory_monitor = None
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        if self.logger:
            self.logger.info(f"Received signal {signum}, initiating graceful shutdown")
        else:
            print(f"Received signal {signum}, initiating graceful shutdown")
        self.running = False
    
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
            self.logger = logging.getLogger("heating.main")
            
            self.logger_system.log_system_startup(
                self.config.system_version, 
                str(self.config_file)
            )
            
            self.hardware = create_hardware_controller(
                self.config.piface_board_count,
                self.logger,
                self.config.mock_hardware
            )
            print(f"✅ Hardware controller initialized ({self.config.piface_board_count} boards)")
            
            self.sensor_manager = create_sensor_manager(self.config, self.logger_system)
            print("✅ Sensor manager initialized")
            
            temperatures = self.sensor_manager.get_valid_temperatures()
            print(f"✅ Initial sensor check: {len(temperatures)} sensors responding")
            
            # Initialize memory monitor
            self.memory_monitor = MemoryMonitor(max_memory_mb=500, check_interval=300)
            self.memory_monitor.start_monitoring()
            print("✅ Memory monitor initialized")
            
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
                
                loop_count += 1
                import time
                time.sleep(self.config.main_loop_interval)
                
        except KeyboardInterrupt:
            print("\n🛑 Shutdown requested by user")
            return self.shutdown()
        except Exception as e:
            print(f"❌ Fatal error: {e}")
            if self.logger:
                self.logger.critical(f"Fatal error: {e}")
            return 1
    
    def shutdown(self) -> int:
        try:
            print("🔄 Shutting down heating system...")
            self.running = False
            
            if self.memory_monitor:
                self.memory_monitor.stop_monitoring()
                print("✅ Memory monitor stopped")
                
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
