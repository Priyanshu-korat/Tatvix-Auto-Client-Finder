"""Configuration package for Tatvix AI Client Discovery System.

This package provides centralized configuration management, logging setup,
and system constants for the application.
"""

from .settings import Settings
from .logging_config import LoggingConfig
from .constants import (
    DEFAULT_LOG_LEVEL,
    DEFAULT_LOG_FORMAT,
    API_TIMEOUT,
    MAX_RETRIES,
    SUPPORTED_ENVIRONMENTS
)

__all__ = [
    'Settings',
    'LoggingConfig',
    'DEFAULT_LOG_LEVEL',
    'DEFAULT_LOG_FORMAT',
    'API_TIMEOUT',
    'MAX_RETRIES',
    'SUPPORTED_ENVIRONMENTS'
]