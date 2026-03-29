"""Logging configuration for Tatvix AI Client Discovery System.

This module provides production-grade logging configuration with JSON formatting,
file rotation, and multiple handlers for different log levels.
"""

import os
import logging
import logging.handlers
import json
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime

from .constants import (
    DEFAULT_LOG_LEVEL,
    DEFAULT_LOG_FORMAT,
    LOG_ROTATION_SIZE,
    LOG_BACKUP_COUNT,
    LOG_DIRECTORY
)


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.
        
        Args:
            record: Log record to format.
            
        Returns:
            JSON-formatted log message.
        """
        log_entry = {
            'timestamp': datetime.utcfromtimestamp(record.created).isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add exception information if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        # Add extra fields if present
        if hasattr(record, 'extra_fields'):
            log_entry.update(record.extra_fields)
        
        # Add process and thread information
        log_entry['process_id'] = record.process
        log_entry['thread_id'] = record.thread
        
        return json.dumps(log_entry, ensure_ascii=False)


class LoggingConfig:
    """Centralized logging configuration management."""
    
    def __init__(self, log_level: str = DEFAULT_LOG_LEVEL, 
                 log_format: str = DEFAULT_LOG_FORMAT,
                 log_directory: str = LOG_DIRECTORY) -> None:
        """Initialize logging configuration.
        
        Args:
            log_level: Default logging level.
            log_format: Log format type ('json' or 'text').
            log_directory: Directory for log files.
        """
        self.log_level = self._validate_log_level(log_level)
        self.log_format = log_format
        self.log_directory = Path(log_directory)
        self._ensure_log_directory()
    
    def _validate_log_level(self, level: str) -> int:
        """Validate and convert log level string to integer.
        
        Args:
            level: Log level string.
            
        Returns:
            Log level as integer.
            
        Raises:
            ValueError: If log level is invalid.
        """
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        
        level_upper = level.upper()
        if level_upper not in level_map:
            raise ValueError(
                f"Invalid log level '{level}'. "
                f"Valid levels: {', '.join(level_map.keys())}"
            )
        
        return level_map[level_upper]
    
    def _ensure_log_directory(self) -> None:
        """Create log directory if it doesn't exist."""
        self.log_directory.mkdir(parents=True, exist_ok=True)
    
    def _create_formatter(self) -> logging.Formatter:
        """Create appropriate formatter based on configuration.
        
        Returns:
            Configured log formatter.
        """
        if self.log_format.lower() == 'json':
            return JSONFormatter()
        else:
            return logging.Formatter(
                fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
    
    def _create_console_handler(self) -> logging.StreamHandler:
        """Create console handler for log output.
        
        Returns:
            Configured console handler.
        """
        handler = logging.StreamHandler()
        handler.setLevel(self.log_level)
        handler.setFormatter(self._create_formatter())
        return handler
    
    def _create_file_handler(self, filename: str, level: int) -> logging.handlers.RotatingFileHandler:
        """Create rotating file handler for log output.
        
        Args:
            filename: Log file name.
            level: Log level for this handler.
            
        Returns:
            Configured file handler.
        """
        log_file = self.log_directory / filename
        handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=self._parse_size(LOG_ROTATION_SIZE),
            backupCount=LOG_BACKUP_COUNT,
            encoding='utf-8'
        )
        handler.setLevel(level)
        handler.setFormatter(self._create_formatter())
        return handler
    
    def _parse_size(self, size_str: str) -> int:
        """Parse size string to bytes.
        
        Args:
            size_str: Size string (e.g., '10MB', '1GB').
            
        Returns:
            Size in bytes.
        """
        size_str = size_str.upper()
        if size_str.endswith('KB'):
            return int(size_str[:-2]) * 1024
        elif size_str.endswith('MB'):
            return int(size_str[:-2]) * 1024 * 1024
        elif size_str.endswith('GB'):
            return int(size_str[:-2]) * 1024 * 1024 * 1024
        else:
            return int(size_str)
    
    def configure_logger(self, logger_name: str, 
                        additional_handlers: Optional[list] = None) -> logging.Logger:
        """Configure logger with appropriate handlers.
        
        Args:
            logger_name: Name of the logger.
            additional_handlers: Additional handlers to add.
            
        Returns:
            Configured logger instance.
        """
        logger = logging.getLogger(logger_name)
        logger.setLevel(self.log_level)
        
        # Clear existing handlers to avoid duplicates
        logger.handlers.clear()
        
        # Add console handler
        logger.addHandler(self._create_console_handler())
        
        # Add file handlers
        logger.addHandler(self._create_file_handler('application.log', logging.INFO))
        logger.addHandler(self._create_file_handler('errors.log', logging.ERROR))
        
        # Add debug file handler if debug level is enabled
        if self.log_level <= logging.DEBUG:
            logger.addHandler(self._create_file_handler('debug.log', logging.DEBUG))
        
        # Add additional handlers if provided
        if additional_handlers:
            for handler in additional_handlers:
                logger.addHandler(handler)
        
        # Prevent propagation to root logger
        logger.propagate = False
        
        return logger
    
    def configure_root_logger(self) -> None:
        """Configure root logger with basic settings."""
        root_logger = logging.getLogger()
        root_logger.setLevel(self.log_level)
        
        # Clear existing handlers
        root_logger.handlers.clear()
        
        # Add console handler only for root logger
        root_logger.addHandler(self._create_console_handler())
    
    def create_module_logger(self, module_name: str) -> logging.Logger:
        """Create logger for specific module.
        
        Args:
            module_name: Name of the module.
            
        Returns:
            Configured module logger.
        """
        logger_name = f"tatvix.{module_name}"
        return self.configure_logger(logger_name)
    
    def get_logger_config(self) -> Dict[str, Any]:
        """Get logging configuration as dictionary.
        
        Returns:
            Logging configuration dictionary.
        """
        return {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'json': {
                    '()': JSONFormatter
                },
                'standard': {
                    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    'datefmt': '%Y-%m-%d %H:%M:%S'
                }
            },
            'handlers': {
                'console': {
                    'class': 'logging.StreamHandler',
                    'level': logging.getLevelName(self.log_level),
                    'formatter': 'json' if self.log_format == 'json' else 'standard',
                    'stream': 'ext://sys.stdout'
                },
                'file': {
                    'class': 'logging.handlers.RotatingFileHandler',
                    'level': 'INFO',
                    'formatter': 'json' if self.log_format == 'json' else 'standard',
                    'filename': str(self.log_directory / 'application.log'),
                    'maxBytes': self._parse_size(LOG_ROTATION_SIZE),
                    'backupCount': LOG_BACKUP_COUNT,
                    'encoding': 'utf-8'
                },
                'error_file': {
                    'class': 'logging.handlers.RotatingFileHandler',
                    'level': 'ERROR',
                    'formatter': 'json' if self.log_format == 'json' else 'standard',
                    'filename': str(self.log_directory / 'errors.log'),
                    'maxBytes': self._parse_size(LOG_ROTATION_SIZE),
                    'backupCount': LOG_BACKUP_COUNT,
                    'encoding': 'utf-8'
                }
            },
            'loggers': {
                'tatvix': {
                    'level': logging.getLevelName(self.log_level),
                    'handlers': ['console', 'file', 'error_file'],
                    'propagate': False
                }
            },
            'root': {
                'level': logging.getLevelName(self.log_level),
                'handlers': ['console']
            }
        }