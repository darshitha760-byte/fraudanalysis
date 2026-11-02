"""
Application Logging Configuration

Provides structured logging with rotation, separate access logs,
error tracking, and performance metrics logging.
"""

import logging
import logging.handlers
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
import sys
from pythonjsonlogger import jsonlogger

from app.core.config import settings


class JsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter for structured logging."""
    
    def add_fields(self, log_record, record, message_dict):
        """Add custom fields to log record."""
        super().add_fields(log_record, record, message_dict)
        
        # Add timestamp
        log_record['timestamp'] = datetime.utcnow().isoformat()
        
        # Add log level
        log_record['level'] = record.levelname
        
        # Add module and function
        log_record['module'] = record.module
        log_record['function'] = record.funcName
        log_record['line'] = record.lineno
        
        # Add process and thread info
        log_record['process_id'] = record.process
        log_record['thread_id'] = record.thread
        
        # Add exception info if present
        if record.exc_info:
            log_record['exception'] = self.formatException(record.exc_info)


def setup_logging(
    log_level: str = "INFO",
    log_dir: str = "./logs",
    console_enabled: bool = True,
    file_enabled: bool = True,
    json_format: bool = True
):
    """
    Configure application logging with rotation and structured format.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory for log files
        console_enabled: Enable console output
        file_enabled: Enable file output
        json_format: Use JSON format for structured logging
    """
    
    # Create log directory
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level))
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create formatters
    if json_format:
        app_formatter = JsonFormatter('%(message)s')
        access_formatter = JsonFormatter('%(message)s')
    else:
        log_format = (
            '%(asctime)s - %(name)s - %(levelname)s - '
            '%(module)s:%(funcName)s:%(lineno)d - %(message)s'
        )
        app_formatter = logging.Formatter(log_format)
        access_formatter = logging.Formatter(log_format)
    
    # ============================================
    # Console Handler
    # ============================================
    if console_enabled:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level))
        console_handler.setFormatter(app_formatter)
        root_logger.addHandler(console_handler)
    
    # ============================================
    # Application Log File Handler
    # ============================================
    if file_enabled:
        app_log_file = log_path / "app.log"
        
        app_file_handler = logging.handlers.RotatingFileHandler(
            app_log_file,
            maxBytes=settings.log_max_size,  # 100 MB
            backupCount=settings.log_backup_count,  # 7 days
            encoding='utf-8'
        )
        app_file_handler.setLevel(getattr(logging, log_level))
        app_file_handler.setFormatter(app_formatter)
        root_logger.addHandler(app_file_handler)
    
    # ============================================
    # Error Log File Handler
    # ============================================
    if file_enabled:
        error_log_file = log_path / "error.log"
        
        error_handler = logging.handlers.RotatingFileHandler(
            error_log_file,
            maxBytes=settings.log_max_size,
            backupCount=settings.log_backup_count,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(app_formatter)
        root_logger.addHandler(error_handler)
    
    # ============================================
    # Audit Log Handler (separate file)
    # ============================================
    if file_enabled:
        audit_log_file = log_path / "audit.log"
        audit_handler = logging.handlers.RotatingFileHandler(
            audit_log_file,
            maxBytes=settings.log_max_size,
            backupCount=settings.log_backup_count,
            encoding='utf-8'
        )
        audit_handler.setLevel(logging.INFO)
        audit_handler.setFormatter(app_formatter)
        
        audit_logger = logging.getLogger("audit")
        audit_logger.addHandler(audit_handler)
        audit_logger.setLevel(logging.INFO)
        audit_logger.propagate = False
    
    # ============================================
    # Access Log Handler (separate file)
    # ============================================
    if file_enabled:
        access_log_file = log_path / "access.log"
        access_handler = logging.handlers.RotatingFileHandler(
            access_log_file,
            maxBytes=settings.log_max_size,
            backupCount=settings.log_backup_count,
            encoding='utf-8'
        )
        access_handler.setLevel(logging.INFO)
        access_handler.setFormatter(access_formatter)
        
        access_logger = logging.getLogger("access")
        access_logger.addHandler(access_handler)
        access_logger.setLevel(logging.INFO)
        access_logger.propagate = False
    
    # ============================================
    # Performance Log Handler
    # ============================================
    if file_enabled:
        perf_log_file = log_path / "performance.log"
        perf_handler = logging.handlers.RotatingFileHandler(
            perf_log_file,
            maxBytes=settings.log_max_size,
            backupCount=settings.log_backup_count,
            encoding='utf-8'
        )
        perf_handler.setLevel(logging.INFO)
        perf_handler.setFormatter(app_formatter)
        
        perf_logger = logging.getLogger("performance")
        perf_logger.addHandler(perf_handler)
        perf_logger.setLevel(logging.INFO)
        perf_logger.propagate = False
    
    # Configure third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    
    root_logger.info(f"Logging configured: level={log_level}, format={'json' if json_format else 'text'}")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance.
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def get_audit_logger() -> logging.Logger:
    """Get audit logger instance."""
    return logging.getLogger("audit")


def get_access_logger() -> logging.Logger:
    """Get access logger instance."""
    return logging.getLogger("access")


def get_performance_logger() -> logging.Logger:
    """Get performance logger instance."""
    return logging.getLogger("performance")


def log_audit_event(
    event_type: str,
    user_id: int = None,
    resource_type: str = None,
    resource_id: int = None,
    action: str = None,
    details: Dict[str, Any] = None,
    status: str = "success"
):
    """
    Log an audit event.
    
    Args:
        event_type: Type of audit event
        user_id: User ID performing the action
        resource_type: Type of resource affected
        resource_id: ID of resource affected
        action: Action performed
        details: Additional details
        status: Event status (success, failure)
    """
    audit_logger = get_audit_logger()
    
    event = {
        "event_type": event_type,
        "user_id": user_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "action": action,
        "details": details or {},
        "status": status,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    audit_logger.info(json.dumps(event))


def log_access_event(
    method: str,
    path: str,
    status_code: int,
    response_time_ms: float,
    user_id: int = None,
    client_ip: str = None
):
    """
    Log an API access event.
    
    Args:
        method: HTTP method
        path: Request path
        status_code: HTTP response status code
        response_time_ms: Response time in milliseconds
        user_id: User ID (if authenticated)
        client_ip: Client IP address
    """
    access_logger = get_access_logger()
    
    event = {
        "method": method,
        "path": path,
        "status_code": status_code,
        "response_time_ms": response_time_ms,
        "user_id": user_id,
        "client_ip": client_ip,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    access_logger.info(json.dumps(event))


def log_performance_metric(
    metric_name: str,
    value: float,
    unit: str = "ms",
    tags: Dict[str, str] = None
):
    """
    Log a performance metric.
    
    Args:
        metric_name: Name of the metric
        value: Metric value
        unit: Unit of measurement
        tags: Additional tags for filtering
    """
    perf_logger = get_performance_logger()
    
    metric = {
        "metric_name": metric_name,
        "value": value,
        "unit": unit,
        "tags": tags or {},
        "timestamp": datetime.utcnow().isoformat()
    }
    
    perf_logger.info(json.dumps(metric))


def log_error_with_context(
    error: Exception,
    context: Dict[str, Any] = None,
    user_id: int = None
):
    """
    Log an error with context information.
    
    Args:
        error: Exception instance
        context: Additional context
        user_id: User ID if available
    """
    logger = get_logger(__name__)
    
    error_details = {
        "error_type": type(error).__name__,
        "error_message": str(error),
        "context": context or {},
        "user_id": user_id,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    logger.error(json.dumps(error_details), exc_info=True)


class PerformanceTimer:
    """Context manager for measuring operation performance."""
    
    def __init__(self, operation_name: str, log_threshold_ms: float = 100):
        """
        Initialize timer.
        
        Args:
            operation_name: Name of operation being timed
            log_threshold_ms: Log if operation exceeds this duration
        """
        self.operation_name = operation_name
        self.log_threshold_ms = log_threshold_ms
        self.start_time = None
    
    def __enter__(self):
        """Start timer."""
        import time
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop timer and log if needed."""
        import time
        duration_ms = (time.time() - self.start_time) * 1000
        
        if duration_ms >= self.log_threshold_ms:
            log_performance_metric(
                self.operation_name,
                duration_ms,
                "ms",
                {"threshold_exceeded": "true"}
            )
        
        return False


__all__ = [
    "setup_logging",
    "get_logger",
    "get_audit_logger",
    "get_access_logger",
    "get_performance_logger",
    "log_audit_event",
    "log_access_event",
    "log_performance_metric",
    "log_error_with_context",
    "PerformanceTimer",
]
