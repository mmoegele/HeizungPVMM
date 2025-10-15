#!/usr/bin/env python3
"""Logging System Module"""

import logging
import logging.handlers
from pathlib import Path
from typing import Dict, Any, Optional, List
from collections import deque
from datetime import datetime
import threading

class LogCaptureHandler(logging.Handler):
    """Custom logging handler to capture recent log entries in memory"""
    
    def __init__(self, max_records: int = 1000):
        super().__init__()
        self.max_records = max_records
        self.records = deque(maxlen=max_records)
        # Remove threading lock to prevent deadlocks
    
    def emit(self, record):
        """Capture log record"""
        try:
            # Format the record - no lock needed for deque with maxlen
            formatted_record = {
                'timestamp': datetime.fromtimestamp(record.created).isoformat(),
                'level': record.levelname,
                'logger': record.name,
                'message': self.format(record),
                'module': record.module,
                'function': record.funcName,
                'line': record.lineno
            }
            self.records.append(formatted_record)
        except Exception:
            # Don't let logging errors break the application
            pass
    
    def get_recent_logs(self, limit: Optional[int] = None) -> List[Dict]:
        """Get recent log entries"""
        try:
            if limit:
                return list(self.records)[-limit:]
            return list(self.records)
        except Exception:
            return []

class HeatingSystemLogger:
    def __init__(self, log_level: str = "INFO", log_dir: Optional[Path] = None):
        self.log_level = log_level
        self.log_dir = log_dir or Path("/var/log/heating")
        # Create logger objects first to ensure attributes exist
        self.main_logger = logging.getLogger("heating.main")
        self.audit_logger = logging.getLogger("heating.audit")
        self.safety_logger = logging.getLogger("heating.safety")
        # Create log capture handler for dashboard
        self.log_capture_handler = LogCaptureHandler(max_records=1000)
        # Then configure logging handlers and levels
        self.setup_logging()
        
    def setup_logging(self) -> None:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        
        # Set up log capture handler for dashboard
        self.log_capture_handler.setFormatter(formatter)
        
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, self.log_level.upper()))
        root_logger.addHandler(console_handler)
        root_logger.addHandler(self.log_capture_handler)  # Capture all logs
        
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
    
    def get_recent_logs(self, limit: Optional[int] = None) -> List[Dict]:
        """Get recent log entries captured by the log handler"""
        return self.log_capture_handler.get_recent_logs(limit)
    
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
