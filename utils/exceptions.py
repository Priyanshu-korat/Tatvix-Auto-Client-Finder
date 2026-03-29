"""Custom exception classes for Tatvix AI Client Discovery System.

This module defines a hierarchical exception structure for domain-specific
error handling throughout the application.
"""

from typing import Optional, Dict, Any


class TatvixError(Exception):
    """Base exception class for all Tatvix-specific errors.
    
    This is the root exception class that all other custom exceptions inherit from.
    It provides common functionality for error handling and logging.
    """
    
    def __init__(self, message: str, error_code: Optional[str] = None,
                 details: Optional[Dict[str, Any]] = None) -> None:
        """Initialize Tatvix error.
        
        Args:
            message: Human-readable error message.
            error_code: Optional error code for programmatic handling.
            details: Optional dictionary with additional error details.
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary format.
        
        Returns:
            Dictionary representation of the exception.
        """
        return {
            'error_type': self.__class__.__name__,
            'message': self.message,
            'error_code': self.error_code,
            'details': self.details
        }
    
    def __str__(self) -> str:
        """String representation of the exception."""
        if self.error_code:
            return f"[{self.error_code}] {self.message}"
        return self.message


class ConfigurationError(TatvixError):
    """Exception raised for configuration-related errors.
    
    This includes missing configuration files, invalid configuration values,
    missing environment variables, and other configuration issues.
    """
    
    def __init__(self, message: str, config_key: Optional[str] = None,
                 config_value: Optional[str] = None) -> None:
        """Initialize configuration error.
        
        Args:
            message: Error message.
            config_key: Configuration key that caused the error.
            config_value: Configuration value that caused the error.
        """
        details = {}
        if config_key:
            details['config_key'] = config_key
        if config_value:
            details['config_value'] = config_value
        
        super().__init__(message, 'CONFIG_ERROR', details)


class ValidationError(TatvixError):
    """Exception raised for input validation errors.
    
    This includes invalid email addresses, URLs, company names,
    and other input validation failures.
    """
    
    def __init__(self, message: str, field_name: Optional[str] = None,
                 field_value: Optional[str] = None, 
                 validation_rule: Optional[str] = None) -> None:
        """Initialize validation error.
        
        Args:
            message: Error message.
            field_name: Name of the field that failed validation.
            field_value: Value that failed validation.
            validation_rule: Validation rule that was violated.
        """
        details = {}
        if field_name:
            details['field_name'] = field_name
        if field_value:
            details['field_value'] = field_value
        if validation_rule:
            details['validation_rule'] = validation_rule
        
        super().__init__(message, 'VALIDATION_ERROR', details)


class DataValidationError(ValidationError):
    """Exception raised for data validation errors in database operations."""
    
    def __init__(self, message: str, field_name: Optional[str] = None,
                 field_value: Optional[str] = None) -> None:
        """Initialize data validation error.
        
        Args:
            message: Error message.
            field_name: Name of the field that failed validation.
            field_value: Value that failed validation.
        """
        super().__init__(message, field_name, field_value, 'DATA_VALIDATION')


class ExternalServiceError(TatvixError):
    """Exception raised for external service errors."""
    
    def __init__(self, message: str, service_name: Optional[str] = None,
                 error_code: Optional[str] = None) -> None:
        """Initialize external service error.
        
        Args:
            message: Error message.
            service_name: Name of the external service.
            error_code: Service-specific error code.
        """
        details = {}
        if service_name:
            details['service_name'] = service_name
        if error_code:
            details['service_error_code'] = error_code
        
        super().__init__(message, 'EXTERNAL_SERVICE_ERROR', details)


class DiscoveryError(TatvixError):
    """Exception raised for lead discovery errors."""
    
    def __init__(self, message: str, source: Optional[str] = None,
                 discovery_type: Optional[str] = None) -> None:
        """Initialize discovery error.
        
        Args:
            message: Error message.
            source: Discovery source that failed.
            discovery_type: Type of discovery operation.
        """
        details = {}
        if source:
            details['source'] = source
        if discovery_type:
            details['discovery_type'] = discovery_type
        
        super().__init__(message, 'DISCOVERY_ERROR', details)


class SearchError(TatvixError):
    """Exception raised for web search-related errors.
    
    This includes search API failures, rate limiting, invalid queries,
    and other search-related issues.
    """
    
    def __init__(self, message: str, search_query: Optional[str] = None,
                 search_engine: Optional[str] = None,
                 http_status: Optional[int] = None) -> None:
        """Initialize search error.
        
        Args:
            message: Error message.
            search_query: Search query that caused the error.
            search_engine: Search engine that was used.
            http_status: HTTP status code if applicable.
        """
        details = {}
        if search_query:
            details['search_query'] = search_query
        if search_engine:
            details['search_engine'] = search_engine
        if http_status:
            details['http_status'] = http_status
        
        super().__init__(message, 'SEARCH_ERROR', details)


class ScrapingError(TatvixError):
    """Exception raised for web scraping-related errors.
    
    This includes website access failures, parsing errors, timeout issues,
    and other scraping-related problems.
    """
    
    def __init__(self, message: str, url: Optional[str] = None,
                 http_status: Optional[int] = None,
                 timeout: Optional[bool] = None) -> None:
        """Initialize scraping error.
        
        Args:
            message: Error message.
            url: URL that was being scraped.
            http_status: HTTP status code if applicable.
            timeout: Whether the error was due to timeout.
        """
        details = {}
        if url:
            details['url'] = url
        if http_status:
            details['http_status'] = http_status
        if timeout is not None:
            details['timeout'] = timeout
        
        super().__init__(message, 'SCRAPING_ERROR', details)


class DatabaseError(TatvixError):
    """Exception raised for database-related errors.
    
    This includes connection failures, query errors, data integrity issues,
    and other database-related problems.
    """
    
    def __init__(self, message: str, operation: Optional[str] = None,
                 table_name: Optional[str] = None,
                 query: Optional[str] = None) -> None:
        """Initialize database error.
        
        Args:
            message: Error message.
            operation: Database operation that failed (insert, update, delete, select).
            table_name: Name of the table involved.
            query: SQL query that caused the error.
        """
        details = {}
        if operation:
            details['operation'] = operation
        if table_name:
            details['table_name'] = table_name
        if query:
            details['query'] = query
        
        super().__init__(message, 'DATABASE_ERROR', details)


class EmailError(TatvixError):
    """Exception raised for email-related errors.
    
    This includes email validation failures, SMTP errors, delivery issues,
    and other email-related problems.
    """
    
    def __init__(self, message: str, email_address: Optional[str] = None,
                 smtp_server: Optional[str] = None,
                 smtp_code: Optional[int] = None) -> None:
        """Initialize email error.
        
        Args:
            message: Error message.
            email_address: Email address that caused the error.
            smtp_server: SMTP server involved.
            smtp_code: SMTP response code if applicable.
        """
        details = {}
        if email_address:
            details['email_address'] = email_address
        if smtp_server:
            details['smtp_server'] = smtp_server
        if smtp_code:
            details['smtp_code'] = smtp_code
        
        super().__init__(message, 'EMAIL_ERROR', details)


class APIError(TatvixError):
    """Exception raised for external API-related errors.
    
    This includes API authentication failures, rate limiting, service unavailability,
    and other API-related issues.
    """
    
    def __init__(self, message: str, api_name: Optional[str] = None,
                 endpoint: Optional[str] = None,
                 http_status: Optional[int] = None,
                 api_error_code: Optional[str] = None) -> None:
        """Initialize API error.
        
        Args:
            message: Error message.
            api_name: Name of the API service.
            endpoint: API endpoint that was called.
            http_status: HTTP status code.
            api_error_code: API-specific error code.
        """
        details = {}
        if api_name:
            details['api_name'] = api_name
        if endpoint:
            details['endpoint'] = endpoint
        if http_status:
            details['http_status'] = http_status
        if api_error_code:
            details['api_error_code'] = api_error_code
        
        super().__init__(message, 'API_ERROR', details)


class RateLimitError(APIError):
    """Exception raised when API rate limits are exceeded."""
    
    def __init__(self, message: str, retry_after: Optional[int] = None,
                 api_name: Optional[str] = None) -> None:
        """Initialize rate limit error.
        
        Args:
            message: Error message.
            retry_after: Seconds to wait before retrying.
            api_name: Name of the API service.
        """
        details = {'retry_after': retry_after} if retry_after else {}
        super().__init__(message, api_name, None, 429, 'RATE_LIMIT_EXCEEDED')
        self.details.update(details)


class AuthenticationError(APIError):
    """Exception raised for API authentication failures."""
    
    def __init__(self, message: str, api_name: Optional[str] = None,
                 credential_type: Optional[str] = None) -> None:
        """Initialize authentication error.
        
        Args:
            message: Error message.
            api_name: Name of the API service.
            credential_type: Type of credential that failed (api_key, token, etc.).
        """
        details = {'credential_type': credential_type} if credential_type else {}
        super().__init__(message, api_name, None, 401, 'AUTHENTICATION_FAILED')
        self.details.update(details)


class DataIntegrityError(DatabaseError):
    """Exception raised for data integrity violations."""
    
    def __init__(self, message: str, constraint_name: Optional[str] = None,
                 table_name: Optional[str] = None) -> None:
        """Initialize data integrity error.
        
        Args:
            message: Error message.
            constraint_name: Name of the violated constraint.
            table_name: Name of the affected table.
        """
        details = {'constraint_name': constraint_name} if constraint_name else {}
        super().__init__(message, 'CONSTRAINT_VIOLATION', table_name)
        self.details.update(details)


class TimeoutError(TatvixError):
    """Exception raised for operation timeout errors."""
    
    def __init__(self, message: str, operation: str, timeout_seconds: int) -> None:
        """Initialize timeout error.
        
        Args:
            message: Error message.
            operation: Operation that timed out.
            timeout_seconds: Timeout duration in seconds.
        """
        details = {
            'operation': operation,
            'timeout_seconds': timeout_seconds
        }
        super().__init__(message, 'TIMEOUT_ERROR', details)