"""Utilities package for Tatvix AI Client Discovery System.

This package provides logging utilities, custom exceptions, and input validation
functions used throughout the application.
"""

from .logger import LoggerFactory, get_logger
from .exceptions import (
    TatvixError,
    ConfigurationError,
    ValidationError,
    SearchError,
    ScrapingError,
    DatabaseError,
    EmailError,
    APIError
)
from .validators import (
    validate_email,
    validate_url,
    validate_company_name,
    validate_required,
    validation_decorator
)

__all__ = [
    'LoggerFactory',
    'get_logger',
    'TatvixError',
    'ConfigurationError',
    'ValidationError',
    'SearchError',
    'ScrapingError',
    'DatabaseError',
    'EmailError',
    'APIError',
    'validate_email',
    'validate_url',
    'validate_company_name',
    'validate_required',
    'validation_decorator'
]