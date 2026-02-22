"""
Structured Logging Module for Sturgeon AI Service

Provides JSON-formatted logging with request ID tracking for production debugging.
"""

import logging
import json
import sys
import time
from datetime import datetime, timezone
from typing import Any, Optional
from contextvars import ContextVar
import uuid

request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def get_request_id() -> Optional[str]:
    """Get the current request ID from context."""
    return request_id_var.get()


def set_request_id(request_id: Optional[str] = None) -> str:
    """Set a new request ID in context. Returns the ID."""
    if request_id is None:
        request_id = str(uuid.uuid4())[:8]
    request_id_var.set(request_id)
    return request_id


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def __init__(self, service_name: str = "sturgeon"):
        super().__init__()
        self.service_name = service_name
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service_name,
        }
        
        request_id = get_request_id()
        if request_id:
            log_data["request_id"] = request_id
        
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        if hasattr(record, "extra_data") and record.extra_data:
            log_data["data"] = record.extra_data
        
        return json.dumps(log_data)


class StructuredLogger:
    """Wrapper around logging.Logger that supports structured logging."""
    
    def __init__(self, name: str, service_name: str = "sturgeon"):
        self.logger = logging.getLogger(name)
        self.service_name = service_name
    
    def _log(self, level: int, message: str, **kwargs: Any) -> None:
        """Internal log method with extra data support."""
        extra = {"extra_data": kwargs} if kwargs else {}
        self.logger.log(level, message, extra=extra)
    
    def debug(self, message: str, **kwargs: Any) -> None:
        self._log(logging.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs: Any) -> None:
        self._log(logging.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs: Any) -> None:
        self._log(logging.WARNING, message, **kwargs)
    
    def error(self, message: str, **kwargs: Any) -> None:
        self._log(logging.ERROR, message, **kwargs)
    
    def critical(self, message: str, **kwargs: Any) -> None:
        self._log(logging.CRITICAL, message, **kwargs)
    
    def exception(self, message: str, **kwargs: Any) -> None:
        kwargs["exception_type"] = "uncaught"
        self.logger.exception(message, extra={"extra_data": kwargs})


def setup_logging(
    level: int = logging.INFO,
    service_name: str = "sturgeon",
    use_json: bool = True
) -> None:
    """Set up structured logging for the application.
    
    Args:
        level: Logging level (default: INFO)
        service_name: Service name for log entries
        use_json: Whether to use JSON formatting (default: True)
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    
    if use_json:
        handler.setFormatter(JSONFormatter(service_name))
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))
    
    root_logger.addHandler(handler)
    
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)


def log_request(
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    client_ip: Optional[str] = None,
    error: Optional[str] = None
) -> None:
    """Log an HTTP request with structured data."""
    logger = StructuredLogger("http")
    
    data = {
        "method": method,
        "path": path,
        "status_code": status_code,
        "duration_ms": round(duration_ms, 2),
    }
    
    if client_ip:
        data["client_ip"] = _mask_ip(client_ip)
    
    if error:
        data["error"] = error
        logger.error(f"{method} {path} {status_code}", **data)
    else:
        logger.info(f"{method} {path} {status_code}", **data)


def _mask_ip(ip: str) -> str:
    """Mask IP address for privacy."""
    if "." in ip:
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.xxx.xxx"
    return "xxx"
