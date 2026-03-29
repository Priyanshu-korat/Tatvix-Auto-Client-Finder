"""Logger utilities for Tatvix AI Client Discovery System.

This module provides a centralized logger factory and utility functions
for consistent logging across the application.
"""

import logging
from typing import Dict, Optional, Any
from functools import wraps

from config.logging_config import LoggingConfig
from config.settings import Settings


class LoggerFactory:
    """Factory class for creating and managing loggers."""
    
    _loggers: Dict[str, logging.Logger] = {}
    _logging_config: Optional[LoggingConfig] = None
    
    @classmethod
    def initialize(cls, settings: Optional[Settings] = None) -> None:
        """Initialize the logger factory with configuration.
        
        Args:
            settings: Application settings instance.
        """
        if settings is None:
            settings = Settings()
        
        log_level = settings.get('general', 'log_level', 'INFO')
        log_format = settings.get('logging', 'format', 'json')
        log_directory = settings.get('logging', 'directory', 'logs')
        
        cls._logging_config = LoggingConfig(
            log_level=log_level,
            log_format=log_format,
            log_directory=log_directory
        )
        
        # Configure root logger
        cls._logging_config.configure_root_logger()
    
    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """Get or create a logger instance.
        
        Args:
            name: Logger name (typically module name).
            
        Returns:
            Configured logger instance.
        """
        if cls._logging_config is None:
            cls.initialize()
        
        if name not in cls._loggers:
            cls._loggers[name] = cls._logging_config.create_module_logger(name)
        
        return cls._loggers[name]
    
    @classmethod
    def get_logger_for_module(cls, module_name: str) -> logging.Logger:
        """Get logger for a specific module.
        
        Args:
            module_name: Name of the module.
            
        Returns:
            Configured logger for the module.
        """
        return cls.get_logger(module_name)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Get logger instance.
    
    Args:
        name: Logger name. If None, uses the calling module's name.
        
    Returns:
        Configured logger instance.
    """
    if name is None:
        import inspect
        frame = inspect.currentframe()
        if frame and frame.f_back:
            name = frame.f_back.f_globals.get('__name__', 'unknown')
    
    return LoggerFactory.get_logger(name or 'unknown')


def log_execution_time(logger: Optional[logging.Logger] = None):
    """Decorator to log function execution time.
    
    Args:
        logger: Logger instance to use. If None, creates one for the module.
    
    Returns:
        Decorator function.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            import time
            
            if logger is None:
                func_logger = get_logger(func.__module__)
            else:
                func_logger = logger
            
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                func_logger.info(
                    f"Function {func.__name__} executed successfully",
                    extra={
                        'extra_fields': {
                            'function': func.__name__,
                            'execution_time_seconds': round(execution_time, 3),
                            'success': True
                        }
                    }
                )
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                func_logger.error(
                    f"Function {func.__name__} failed with error: {str(e)}",
                    extra={
                        'extra_fields': {
                            'function': func.__name__,
                            'execution_time_seconds': round(execution_time, 3),
                            'success': False,
                            'error_type': type(e).__name__
                        }
                    },
                    exc_info=True
                )
                raise
        return wrapper
    return decorator


def log_method_calls(logger: Optional[logging.Logger] = None):
    """Decorator to log method calls with parameters.
    
    Args:
        logger: Logger instance to use. If None, creates one for the module.
    
    Returns:
        Decorator function.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if logger is None:
                func_logger = get_logger(func.__module__)
            else:
                func_logger = logger
            
            # Log method entry
            func_logger.debug(
                f"Entering method {func.__name__}",
                extra={
                    'extra_fields': {
                        'method': func.__name__,
                        'args_count': len(args),
                        'kwargs_keys': list(kwargs.keys()),
                        'event_type': 'method_entry'
                    }
                }
            )
            
            try:
                result = func(*args, **kwargs)
                
                # Log method exit
                func_logger.debug(
                    f"Exiting method {func.__name__}",
                    extra={
                        'extra_fields': {
                            'method': func.__name__,
                            'success': True,
                            'event_type': 'method_exit'
                        }
                    }
                )
                
                return result
            except Exception as e:
                # Log method error
                func_logger.error(
                    f"Method {func.__name__} failed with error: {str(e)}",
                    extra={
                        'extra_fields': {
                            'method': func.__name__,
                            'success': False,
                            'error_type': type(e).__name__,
                            'event_type': 'method_error'
                        }
                    },
                    exc_info=True
                )
                raise
        return wrapper
    return decorator


def log_api_call(api_name: str, logger: Optional[logging.Logger] = None):
    """Decorator to log API calls.
    
    Args:
        api_name: Name of the API being called.
        logger: Logger instance to use. If None, creates one for the module.
    
    Returns:
        Decorator function.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if logger is None:
                func_logger = get_logger(func.__module__)
            else:
                func_logger = logger
            
            import time
            start_time = time.time()
            
            func_logger.info(
                f"Making API call to {api_name}",
                extra={
                    'extra_fields': {
                        'api_name': api_name,
                        'function': func.__name__,
                        'event_type': 'api_call_start'
                    }
                }
            )
            
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                
                func_logger.info(
                    f"API call to {api_name} completed successfully",
                    extra={
                        'extra_fields': {
                            'api_name': api_name,
                            'function': func.__name__,
                            'execution_time_seconds': round(execution_time, 3),
                            'success': True,
                            'event_type': 'api_call_success'
                        }
                    }
                )
                
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                
                func_logger.error(
                    f"API call to {api_name} failed: {str(e)}",
                    extra={
                        'extra_fields': {
                            'api_name': api_name,
                            'function': func.__name__,
                            'execution_time_seconds': round(execution_time, 3),
                            'success': False,
                            'error_type': type(e).__name__,
                            'event_type': 'api_call_error'
                        }
                    },
                    exc_info=True
                )
                raise
        return wrapper
    return decorator


class StructuredLogger:
    """Wrapper class for structured logging with consistent extra fields."""
    
    def __init__(self, logger: logging.Logger, component: str):
        """Initialize structured logger.
        
        Args:
            logger: Base logger instance.
            component: Component name for structured logging.
        """
        self.logger = logger
        self.component = component
    
    def _log_with_structure(self, level: int, message: str, 
                           extra_fields: Optional[Dict[str, Any]] = None) -> None:
        """Log message with structured extra fields.
        
        Args:
            level: Log level.
            message: Log message.
            extra_fields: Additional fields to include.
        """
        fields = {'component': self.component}
        if extra_fields:
            fields.update(extra_fields)
        
        self.logger.log(level, message, extra={'extra_fields': fields})
    
    def debug(self, message: str, **kwargs) -> None:
        """Log debug message."""
        self._log_with_structure(logging.DEBUG, message, kwargs)
    
    def info(self, message: str, **kwargs) -> None:
        """Log info message."""
        self._log_with_structure(logging.INFO, message, kwargs)
    
    def warning(self, message: str, **kwargs) -> None:
        """Log warning message."""
        self._log_with_structure(logging.WARNING, message, kwargs)
    
    def error(self, message: str, **kwargs) -> None:
        """Log error message."""
        self._log_with_structure(logging.ERROR, message, kwargs)
    
    def critical(self, message: str, **kwargs) -> None:
        """Log critical message."""
        self._log_with_structure(logging.CRITICAL, message, kwargs)