"""
TCG Scan - Professional Logging System
Centralized logging configuration with multiple handlers
"""
import logging
import logging.handlers
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from functools import wraps
import traceback
import json
from typing import Optional, Any, Dict

# Base directory for logs
BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# Log levels
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'DEBUG').upper()
LOG_FORMAT = '%(asctime)s | %(levelname)-8s | %(name)-20s | %(funcName)-20s | %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# JSON format for structured logging
class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'message': record.getMessage(),
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                'message': str(record.exc_info[1]) if record.exc_info[1] else None,
                'traceback': traceback.format_exception(*record.exc_info) if record.exc_info[0] else None
            }
        
        # Add extra fields
        if hasattr(record, 'extra_data'):
            log_data['extra'] = record.extra_data
            
        return json.dumps(log_data, default=str)


class ColoredFormatter(logging.Formatter):
    """Colored formatter for console output"""
    
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


def setup_logger(name: str = 'TCG Scan') -> logging.Logger:
    """
    Setup and configure a logger with multiple handlers
    
    Args:
        name: Logger name (default: 'TCG Scan')
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger
    
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.DEBUG))
    logger.propagate = False
    
    # Console Handler with colors - INFO level to reduce spam
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.WARNING)  # Only show warnings and errors in console
    console_formatter = ColoredFormatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File Handler - All logs
    all_logs_file = LOG_DIR / 'TCG Scan.log'
    file_handler = logging.handlers.RotatingFileHandler(
        all_logs_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # File Handler - Errors only
    error_logs_file = LOG_DIR / 'errors.log'
    error_handler = logging.handlers.RotatingFileHandler(
        error_logs_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_formatter)
    logger.addHandler(error_handler)
    
    # JSON File Handler - For structured logging
    json_logs_file = LOG_DIR / 'TCG Scan.json.log'
    json_handler = logging.handlers.RotatingFileHandler(
        json_logs_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    json_handler.setLevel(logging.INFO)
    json_handler.setFormatter(JSONFormatter())
    logger.addHandler(json_handler)
    
    return logger


def get_logger(name: str = None) -> logging.Logger:
    """
    Get a child logger for a specific module
    
    Args:
        name: Module name (will be prefixed with 'TCG Scan.')
        
    Returns:
        Logger instance
    """
    if name:
        return logging.getLogger(f'TCG Scan.{name}')
    return logging.getLogger('TCG Scan')


def log_function_call(logger: logging.Logger = None):
    """
    Decorator to log function entry, exit and errors
    
    Args:
        logger: Optional logger instance
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            _logger = logger or get_logger(func.__module__)
            func_name = func.__name__
            
            # Log entry
            _logger.debug(f"ENTER {func_name} | args={args[1:] if args else ()} | kwargs={kwargs}")
            
            try:
                result = func(*args, **kwargs)
                # Log exit
                _logger.debug(f"EXIT {func_name} | result_type={type(result).__name__}")
                return result
            except Exception as e:
                # Log error
                _logger.error(f"ERROR in {func_name}: {str(e)}", exc_info=True)
                raise
        return wrapper
    return decorator


def log_api_call(logger: logging.Logger = None):
    """
    Decorator specifically for API endpoint logging
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            _logger = logger or get_logger('api')
            func_name = func.__name__
            
            from flask import request
            
            # Log request
            _logger.info(f"API REQUEST | {request.method} {request.path} | endpoint={func_name}")
            
            try:
                result = func(*args, **kwargs)
                
                # Get status code from result
                status_code = 200
                if isinstance(result, tuple) and len(result) > 1:
                    status_code = result[1]
                
                _logger.info(f"API RESPONSE | {request.method} {request.path} | status={status_code}")
                return result
            except Exception as e:
                _logger.error(f"API ERROR | {request.method} {request.path} | error={str(e)}", exc_info=True)
                raise
        return wrapper
    return decorator


class LoggerAdapter(logging.LoggerAdapter):
    """Custom adapter to add extra context to logs"""
    
    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        extra = kwargs.get('extra', {})
        extra.update(self.extra)
        kwargs['extra'] = extra
        return msg, kwargs


def get_context_logger(name: str, **context) -> LoggerAdapter:
    """
    Get a logger with additional context
    
    Args:
        name: Logger name
        **context: Additional context to add to all logs
        
    Returns:
        LoggerAdapter with context
    """
    logger = get_logger(name)
    return LoggerAdapter(logger, context)


# Performance logging helper
class PerformanceLogger:
    """Context manager for logging performance metrics"""
    
    def __init__(self, operation: str, logger: logging.Logger = None):
        self.operation = operation
        self.logger = logger or get_logger('performance')
        self.start_time = None
        
    def __enter__(self):
        import time
        self.start_time = time.perf_counter()
        self.logger.debug(f"START | {self.operation}")
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        elapsed = time.perf_counter() - self.start_time
        
        if exc_type:
            self.logger.error(f"FAILED | {self.operation} | elapsed={elapsed:.4f}s | error={exc_val}")
        else:
            self.logger.info(f"COMPLETED | {self.operation} | elapsed={elapsed:.4f}s")
        
        return False  # Don't suppress exceptions


# Initialize main logger on import
_main_logger = setup_logger('TCG Scan')


# Export helper function for quick access
def log_info(msg: str, **kwargs):
    """Quick info logging"""
    _main_logger.info(msg, **kwargs)


def log_error(msg: str, exc_info: bool = False, **kwargs):
    """Quick error logging"""
    _main_logger.error(msg, exc_info=exc_info, **kwargs)


def log_warning(msg: str, **kwargs):
    """Quick warning logging"""
    _main_logger.warning(msg, **kwargs)


def log_debug(msg: str, **kwargs):
    """Quick debug logging"""
    _main_logger.debug(msg, **kwargs)


if __name__ == '__main__':
    # Test logging
    logger = get_logger('test')
    
    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")
    
    try:
        raise ValueError("Test exception")
    except Exception:
        logger.exception("This is an exception message")
    
    # Test performance logger
    with PerformanceLogger("test_operation"):
        import time
        time.sleep(0.1)
    
    print("\nLogs written to:", LOG_DIR)
