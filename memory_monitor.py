"""
Memory Monitor for Heating System
Prevents memory leaks and monitors resource usage
"""

import gc
import psutil
import threading
import logging
import time
from datetime import datetime

class MemoryMonitor:
    """Monitor and prevent memory leaks"""
    
    def __init__(self, max_memory_mb=500, check_interval=300):
        self.max_memory_mb = max_memory_mb
        self.check_interval = check_interval
        self.monitoring = False
        self.monitor_thread = None
        self.logger = logging.getLogger(__name__)
        
    def start_monitoring(self):
        """Start memory monitoring in background thread"""
        if not self.monitoring:
            self.monitoring = True
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            self.logger.info("Memory monitoring started")
    
    def stop_monitoring(self):
        """Stop memory monitoring"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.monitoring:
            try:
                process = psutil.Process()
                memory_mb = process.memory_info().rss / 1024 / 1024
                
                if memory_mb > self.max_memory_mb:
                    self.logger.warning(f"High memory usage: {memory_mb:.1f}MB")
                    self._cleanup_memory()
                
                time.sleep(self.check_interval)
                
            except Exception as e:
                self.logger.error(f"Memory monitoring error: {e}")
                time.sleep(60)  # Wait before retrying
    
    def _cleanup_memory(self):
        """Attempt to free memory"""
        try:
            # Force garbage collection
            collected = gc.collect()
            
            # Log memory cleanup
            process = psutil.Process()
            new_memory_mb = process.memory_info().rss / 1024 / 1024
            
            self.logger.info(f"Memory cleanup: collected {collected} objects, "
                           f"memory now {new_memory_mb:.1f}MB")
            
        except Exception as e:
            self.logger.error(f"Memory cleanup failed: {e}")