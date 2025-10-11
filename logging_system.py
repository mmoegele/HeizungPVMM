#!/usr/bin/env python3
"""Logging System Module"""

import logging
import logging.handlers
from pathlib import Path
from typing import Dict, Any, Optional

class HeatingSystemLogger:
    def __init__(self, log_level: str = "INFO", log_dir: Optional[Path] = None):
        self.log_level = log_level
        self.log_dir = log_dir or Path("/var/log/heating")
        # Create logger objects first to ensure attributes exist
        self.main_logger = logging.getLogger("heating.main")
        self.audit_logger = logging.getLogger("heating.audit")
        self.safety_logger = logging.getLogger("heating.safety")
        # Then configure logging handlers and levels
        self.setup_logging()
        
    def setup_logging(self) -> None:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, self.log_level.upper()))
        root_logger.addHandler(console_handler)
        
        if self._is_log_dir_writable():
            self._setup_file_handlers(formatter)
    
    def _is_log_dir_writable(self) -> bool:
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            test_file = self.log_dir / "test_write.tmp"
            test_file.touch()
            test_file.unlink()
            return True
        except:
            return False
    
    def _setup_file_handlers(self, formatter):
        main_handler = logging.handlers.RotatingFileHandler(
            self.log_dir / "heating_system.log",
            maxBytes=10*1024*1024,
            backupCount=5
        )
        main_handler.setFormatter(formatter)
        self.main_logger.addHandler(main_handler)
        
        audit_handler = logging.handlers.RotatingFileHandler(
            self.log_dir / "audit.log",
            maxBytes=5*1024*1024,
            backupCount=10
        )
        audit_handler.setFormatter(formatter)
        self.audit_logger.addHandler(audit_handler)
        self.audit_logger.propagate = False
    
    # Delegate standard logging methods to main_logger
    def debug(self, msg: str, *args, **kwargs) -> None:
        self.main_logger.debug(msg, *args, **kwargs)
        
    def info(self, msg: str, *args, **kwargs) -> None:
        self.main_logger.info(msg, *args, **kwargs)
        
    def warning(self, msg: str, *args, **kwargs) -> None:
        self.main_logger.warning(msg, *args, **kwargs)
        
    def error(self, msg: str, *args, **kwargs) -> None:
        self.main_logger.error(msg, *args, **kwargs)
        
    def critical(self, msg: str, *args, **kwargs) -> None:
        self.main_logger.critical(msg, *args, **kwargs)
        
    def exception(self, msg: str, *args, **kwargs) -> None:
        self.main_logger.exception(msg, *args, **kwargs)
    
    def log_system_startup(self, version: str, config_file: str) -> None:
        self.main_logger.info(f"SYSTEM_STARTUP: Version {version}, Config: {config_file}")
    
    def log_system_shutdown(self, reason: str = "Normal shutdown") -> None:
        self.main_logger.info(f"SYSTEM_SHUTDOWN: {reason}")

def setup_basic_logging(level: str = "INFO") -> logging.Logger:
    logging.basicConfig(level=getattr(logging, level.upper()))
    return logging.getLogger("heating")

if __name__ == "__main__":
    print("🔧 Logging System Test")
    logger_system = HeatingSystemLogger("INFO")
    logger_system.log_system_startup("2.0.0", "test_config.yaml")
    print("✅ Logging test completed")
