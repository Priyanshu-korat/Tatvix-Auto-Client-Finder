"""Settings management for Tatvix AI Client Discovery System.

This module provides centralized configuration management using the singleton pattern
with support for environment variables and multiple configuration environments.
"""

import os
import configparser
from typing import Optional, Dict, Any, List
from pathlib import Path
import threading
from dotenv import load_dotenv

from .constants import (
    SUPPORTED_ENVIRONMENTS,
    DEFAULT_ENVIRONMENT,
    CONFIG_FILE_NAME,
    API_TIMEOUT,
    MAX_RETRIES,
    DEFAULT_LOG_LEVEL,
    USER_AGENT_DESKTOP,
    USER_AGENT_MOBILE,
)
# ConfigurationError will be defined locally to avoid circular imports


class ConfigurationError(Exception):
    """Local configuration error class to avoid circular imports."""
    pass


class Settings:
    """Singleton configuration management class.
    
    Provides centralized access to application configuration with support for
    environment variables, multiple environments, and secure credential handling.
    """
    
    _instance: Optional['Settings'] = None
    _lock: threading.Lock = threading.Lock()
    _initialized: bool = False
    
    def __new__(cls) -> 'Settings':
        """Create singleton instance with thread-safe initialization."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        """Initialize settings if not already initialized."""
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    self._config: configparser.ConfigParser = configparser.ConfigParser()
                    self._environment: str = self._get_environment()
                    self._config_path: Optional[Path] = None
                    self._load_configuration()
                    self._validate_configuration()
                    Settings._initialized = True
    
    def _get_environment(self) -> str:
        """Get current environment from environment variable.
        
        Returns:
            Environment name (development, staging, or production).
            
        Raises:
            ConfigurationError: If environment is not supported.
        """
        env = os.getenv('TATVIX_ENVIRONMENT', DEFAULT_ENVIRONMENT).lower()
        if env not in SUPPORTED_ENVIRONMENTS:
            raise ConfigurationError(
                f"Unsupported environment '{env}'. "
                f"Supported environments: {', '.join(SUPPORTED_ENVIRONMENTS)}"
            )
        return env
    
    def _load_configuration(self) -> None:
        """Load configuration from file and environment variables."""
        # Load .env file first
        env_file = Path('.env')
        if env_file.exists():
            load_dotenv(env_file)
        
        # Load from configuration file if exists
        config_file = Path(CONFIG_FILE_NAME)
        if config_file.exists():
            self._config_path = config_file
            self._config.read(config_file)
        
        # Load environment-specific configuration
        env_config_file = Path(f"config.{self._environment}.ini")
        if env_config_file.exists():
            self._config.read(env_config_file)
        
        # Set default values
        self._set_defaults()
    
    def _set_defaults(self) -> None:
        """Set default configuration values."""
        defaults = {
            'general': {
                'environment': self._environment,
                'debug': 'false',
                'log_level': DEFAULT_LOG_LEVEL,
                'api_timeout': str(API_TIMEOUT),
                'max_retries': str(MAX_RETRIES)
            },
            'api': {
                'timeout': '30',
                'max_tokens': '4000',
                'temperature': '0.1'
            },
            'google': {
                'sheets_timeout': '30',
                'batch_size': '100',
                'retry_attempts': '3',
                'worksheet_name': os.getenv('TATVIX_GOOGLE_WORKSHEET_NAME', 'March 2026')
            },
            'search': {
                'results_limit': '50',
                'concurrent_searches': '5',
                'query_timeout': '15'
            },
            'scraping': {
                'timeout': '30',
                'max_page_size': '10485760',
                'delay_min': '2.0',
                'delay_max': '5.0',
                'enabled': 'true',
                'max_retries': '3',
                'retry_backoff_base': '2.0',
                'max_concurrent': '3',
                'playwright_headless': 'true',
                'proxy_urls': '',
                'user_agent_desktop': USER_AGENT_DESKTOP,
                'user_agent_mobile': USER_AGENT_MOBILE,
            },
            'database': {
                'similarity_threshold': '0.85',
                'duplicate_threshold': '0.90',
                'batch_size': '100',
                'cache_ttl_hours': '24'
            },
            'chroma': {
                'persist_directory': './data/chroma_db',
                'collection_name': 'company_embeddings',
                'embedding_model': 'sentence-transformers/all-MiniLM-L6-v2',
                'embedding_dimension': '384',
                'distance_function': 'cosine',
                'batch_size': '32',
                'max_batch_size': '128',
                'search_timeout_seconds': '30',
                'embedding_timeout_seconds': '60',
                'backup_enabled': 'true',
                'backup_interval_hours': '24',
                'backup_retention_days': '30'
            },
            'duplicate_detection': {
                'enabled': 'true',
                'similarity_threshold': '0.90',
                'embedding_similarity_threshold': '0.85',
                'business_logic_threshold': '0.80',
                'domain_exact_match': 'true',
                'fuzzy_name_threshold': '0.85',
                'location_similarity_threshold': '0.75',
                'phone_similarity_threshold': '0.90',
                'technology_overlap_threshold': '0.60',
                'max_similar_companies': '10',
                'batch_size': '50',
                'max_concurrent_checks': '5',
                'timeout_seconds': '300',
                'cache_enabled': 'true',
                'cache_ttl_hours': '24',
                'audit_enabled': 'true',
                'log_similarity_scores': 'false',
                'performance_target_ms': '100',
                'embedding_dimension': '384',
                'vector_store_type': 'inmemory',
                'name_similarity_weight': '0.30',
                'description_similarity_weight': '0.25',
                'location_similarity_weight': '0.15',
                'phone_similarity_weight': '0.10',
                'technology_similarity_weight': '0.20'
            },
            'email': {
                'verification_timeout': '10',
                'max_length': '254'
            },
            'discovery': {
                'max_concurrent_sources': '4',
                'timeout_seconds': '7200',
                'duplicate_threshold': '0.9',
                'min_confidence_level': 'low',
                'min_relevance_score': '0.3',
                'default_keywords': 'IoT,embedded systems,smart devices,industrial IoT,connected devices,sensor networks,edge computing',
                'default_categories': 'hardware,iot,embedded,smart-home,industrial',
                'default_job_keywords': 'embedded software engineer,firmware engineer,IoT developer,hardware engineer,embedded systems engineer'
            },
            'github': {
                'enabled': 'true',
                'timeout': '30',
                'max_retries': '3',
                'max_results_per_query': '100',
                'min_stars': '5',
                'min_forks': '2'
            },
            'product_hunt': {
                'enabled': 'true',
                'timeout': '30',
                'max_retries': '3'
            },
            'crunchbase': {
                'enabled': 'true',
                'timeout': '30',
                'max_retries': '3'
            },
            'f6s': {
                'enabled': 'true',
                'timeout': '30',
                'max_retries': '3'
            },
            'gust': {
                'enabled': 'true',
                'timeout': '30',
                'max_retries': '3'
            },
            'angellist': {
                'enabled': 'true',
                'timeout': '30',
                'max_retries': '3'
            },
            'uspto': {
                'enabled': 'true',
                'timeout': '30',
                'max_retries': '3'
            },
            'google_patents': {
                'enabled': 'true',
                'timeout': '30',
                'max_retries': '3'
            },
            'linkedin_jobs': {
                'enabled': 'true',
                'timeout': '30',
                'max_retries': '3'
            },
            'indeed': {
                'enabled': 'true',
                'timeout': '30',
                'max_retries': '3'
            },
            'glassdoor': {
                'enabled': 'true',
                'timeout': '30',
                'max_retries': '3'
            },
            'startup_directories': {
                'timeout': '1800',
                'max_retries': '3'
            },
            'patents': {
                'timeout': '1800',
                'max_retries': '3'
            },
            'job_boards': {
                'timeout': '1800',
                'max_retries': '3'
            }
        }
        
        for section, options in defaults.items():
            if not self._config.has_section(section):
                self._config.add_section(section)
            for option, value in options.items():
                if not self._config.has_option(section, option):
                    self._config.set(section, option, value)
    
    def _validate_configuration(self) -> None:
        """Validate critical configuration parameters.
        
        Raises:
            ConfigurationError: If required configuration is missing or invalid.
        """
        required_sections = ['general', 'api', 'google', 'search', 'scraping', 'database', 'email']
        for section in required_sections:
            if not self._config.has_section(section):
                raise ConfigurationError(f"Required configuration section '{section}' is missing")
        
        # Validate numeric values
        try:
            self.get_int('general', 'api_timeout')
            self.get_int('general', 'max_retries')
            self.get_float('database', 'similarity_threshold')
            self.get_float('database', 'duplicate_threshold')
        except (ValueError, configparser.NoOptionError) as e:
            raise ConfigurationError(f"Invalid configuration value: {e}")
    
    def get(self, section: str, option: str, fallback: Optional[str] = None) -> str:
        """Get configuration value as string.
        
        Args:
            section: Configuration section name.
            option: Configuration option name.
            fallback: Default value if option not found.
            
        Returns:
            Configuration value as string.
        """
        # Check environment variable first
        env_key = f"TATVIX_{section.upper()}_{option.upper()}"
        env_value = os.getenv(env_key)
        if env_value is not None:
            return env_value
        
        return self._config.get(section, option, fallback=fallback)
    
    def get_string(self, section: str, option: str, fallback: Optional[str] = None) -> Optional[str]:
        """Get configuration value as string.
        
        Args:
            section: Configuration section name.
            option: Configuration option name.
            fallback: Default value if option not found.
            
        Returns:
            Configuration value as string or None if not found.
        """
        return self.get(section, option, fallback=fallback)
    
    def get_int(self, section: str, option: str, fallback: Optional[int] = None) -> int:
        """Get configuration value as integer.
        
        Args:
            section: Configuration section name.
            option: Configuration option name.
            fallback: Default value if option not found.
            
        Returns:
            Configuration value as integer.
            
        Raises:
            ConfigurationError: If value cannot be converted to integer.
        """
        try:
            value = self.get(section, option)
            if value is None and fallback is not None:
                return fallback
            return int(value)
        except (ValueError, TypeError) as e:
            raise ConfigurationError(
                f"Cannot convert configuration value '{section}.{option}' to integer: {e}"
            )
    
    def get_float(self, section: str, option: str, fallback: Optional[float] = None) -> float:
        """Get configuration value as float.
        
        Args:
            section: Configuration section name.
            option: Configuration option name.
            fallback: Default value if option not found.
            
        Returns:
            Configuration value as float.
            
        Raises:
            ConfigurationError: If value cannot be converted to float.
        """
        try:
            value = self.get(section, option)
            if value is None and fallback is not None:
                return fallback
            return float(value)
        except (ValueError, TypeError) as e:
            raise ConfigurationError(
                f"Cannot convert configuration value '{section}.{option}' to float: {e}"
            )
    
    def get_bool(self, section: str, option: str, fallback: Optional[bool] = None) -> bool:
        """Get configuration value as boolean.
        
        Args:
            section: Configuration section name.
            option: Configuration option name.
            fallback: Default value if option not found.
            
        Returns:
            Configuration value as boolean.
        """
        value = self.get(section, option)
        if value is None and fallback is not None:
            return fallback
        return self._config.getboolean(section, option)
    
    def get_list(self, section: str, option: str, separator: str = ',', 
                 fallback: Optional[List[str]] = None) -> List[str]:
        """Get configuration value as list.
        
        Args:
            section: Configuration section name.
            option: Configuration option name.
            separator: List item separator.
            fallback: Default value if option not found.
            
        Returns:
            Configuration value as list of strings.
        """
        value = self.get(section, option)
        if value is None:
            return fallback or []
        return [item.strip() for item in value.split(separator) if item.strip()]
    
    def get_secure(self, section: str, option: str) -> Optional[str]:
        """Get secure configuration value (API keys, passwords).
        
        This method prioritizes environment variables for security.
        
        Args:
            section: Configuration section name.
            option: Configuration option name.
            
        Returns:
            Secure configuration value or None if not found.
        """
        # Always check environment variable first for secure values
        env_key = f"TATVIX_{section.upper()}_{option.upper()}"
        env_value = os.getenv(env_key)
        if env_value:
            return env_value
        
        # Fallback to config file (not recommended for production)
        if self._config.has_option(section, option):
            return self._config.get(section, option)
        
        return None
    
    @property
    def environment(self) -> str:
        """Get current environment."""
        return self._environment
    
    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self._environment == 'development'
    
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self._environment == 'production'
    
    @property
    def debug_enabled(self) -> bool:
        """Check if debug mode is enabled."""
        return self.get_bool('general', 'debug', fallback=False)
    
    # API Configuration Properties
    @property
    def groq_api_key(self) -> Optional[str]:
        """Get Groq API key."""
        return self.get_string('api', 'groq_api_key')
    
    @property
    def openai_api_key(self) -> Optional[str]:
        """Get OpenAI API key."""
        return self.get_string('api', 'openai_api_key')
    
    # Google Services Properties
    @property
    def google_sheets_id(self) -> Optional[str]:
        """Get Google Sheets ID."""
        return self.get_string('google', 'sheets_id')
    
    @property
    def google_sheets_credentials_path(self) -> Optional[str]:
        """Get Google Sheets credentials file path."""
        return self.get_string('google', 'sheets_credentials_path')
    
    # Logging Properties
    @property
    def logging_directory(self) -> str:
        """Get logging directory."""
        return self.get_string('logging', 'directory', fallback='logs')
    
    # Lead Generation Configuration Properties
    @property
    def default_lead_country(self) -> str:
        """Get default lead country."""
        from .constants import DEFAULT_LEAD_COUNTRY
        return self.get_string('leads', 'default_country', fallback=DEFAULT_LEAD_COUNTRY)
    
    @property
    def default_lead_industry(self) -> str:
        """Get default lead industry."""
        from .constants import DEFAULT_LEAD_INDUSTRY
        return self.get_string('leads', 'default_industry', fallback=DEFAULT_LEAD_INDUSTRY)
    
    @property
    def default_lead_score(self) -> int:
        """Get default lead score."""
        from .constants import DEFAULT_LEAD_SCORE
        return self.get_int('leads', 'default_score', fallback=DEFAULT_LEAD_SCORE)
    
    @property
    def default_lead_source(self) -> str:
        """Get default lead source."""
        from .constants import DEFAULT_LEAD_SOURCE
        return self.get_string('leads', 'default_source', fallback=DEFAULT_LEAD_SOURCE)
    
    def to_dict(self) -> Dict[str, Dict[str, Any]]:
        """Convert configuration to dictionary format.
        
        Returns:
            Configuration as nested dictionary.
        """
        result = {}
        for section_name in self._config.sections():
            result[section_name] = dict(self._config.items(section_name))
        return result
    
    def validate_required_credentials(self) -> None:
        """Validate that all required credentials are available.
        
        Raises:
            ConfigurationError: If required credentials are missing.
        """
        required_credentials = [
            ('api', 'groq_api_key'),
            ('google', 'sheets_credentials_path'),
            ('google', 'sheets_id')
        ]
        
        # Optional credentials for enhanced functionality
        optional_credentials = [
            ('email', 'smtp_username'),
            ('email', 'smtp_password'),
            ('github', 'api_token'),
            ('product_hunt', 'api_token'),
            ('crunchbase', 'api_key')
        ]
        
        missing_credentials = []
        for section, option in required_credentials:
            if not self.get_secure(section, option):
                missing_credentials.append(f"{section}.{option}")
        
        if missing_credentials:
            raise ConfigurationError(
                f"Missing required credentials: {', '.join(missing_credentials)}. "
                "Please set the corresponding environment variables."
            )
    
    def __repr__(self) -> str:
        """String representation of settings."""
        return f"Settings(environment='{self._environment}', sections={list(self._config.sections())})"