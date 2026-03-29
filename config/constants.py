"""System constants for Tatvix AI Client Discovery System.

This module defines all system-wide constants used throughout the application.
"""

from typing import List, Dict, Any

# Logging Configuration
DEFAULT_LOG_LEVEL: str = "INFO"
DEFAULT_LOG_FORMAT: str = "json"
LOG_ROTATION_SIZE: str = "10MB"
LOG_BACKUP_COUNT: int = 5

# API Configuration
API_TIMEOUT: int = 30
MAX_RETRIES: int = 3
RETRY_BACKOFF_FACTOR: float = 2.0
REQUEST_DELAY_MIN: float = 1.0
REQUEST_DELAY_MAX: float = 5.0

# Environment Configuration
SUPPORTED_ENVIRONMENTS: List[str] = ["development", "staging", "production"]
DEFAULT_ENVIRONMENT: str = "development"

# Search Configuration
DEFAULT_SEARCH_RESULTS_LIMIT: int = 50
MAX_CONCURRENT_SEARCHES: int = 5
SEARCH_QUERY_TIMEOUT: int = 15

# Web Scraping Configuration
USER_AGENT_DESKTOP: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
USER_AGENT_MOBILE: str = "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
SCRAPING_TIMEOUT: int = 30
MAX_PAGE_SIZE: int = 10485760  # 10MB

# Email Configuration
EMAIL_REGEX_PATTERN: str = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
EMAIL_VERIFICATION_TIMEOUT: int = 10
MAX_EMAIL_LENGTH: int = 254

# Database Configuration
VECTOR_SIMILARITY_THRESHOLD: float = 0.85
DUPLICATE_DETECTION_THRESHOLD: float = 0.90
MAX_BATCH_SIZE: int = 100

# Lead Scoring Configuration
LEAD_SCORE_WEIGHTS: Dict[str, float] = {
    "iot_software_focus": 0.30,
    "embedded_systems": 0.25,
    "company_size_fit": 0.20,
    "technology_stack": 0.15,
    "geographic_match": 0.10
}

LEAD_SCORE_MAX_POINTS: Dict[str, int] = {
    "iot_software_focus": 4,
    "embedded_systems": 3,
    "company_size_fit": 3,
    "technology_stack": 2,
    "geographic_match": 1
}

# Geographic Configuration
TARGET_COUNTRIES: List[str] = [
    "Germany", "USA", "Netherlands", "Sweden", 
    "India", "UK", "Canada"
]

# Company Classification
IOT_KEYWORDS: List[str] = [
    "iot", "internet of things", "connected devices", "smart sensors",
    "embedded systems", "firmware", "microcontroller", "hardware",
    "smart home", "industrial iot", "edge computing", "wireless"
]

TECHNOLOGY_STACK_INDICATORS: List[str] = [
    "python", "c++", "embedded c", "arduino", "raspberry pi",
    "mqtt", "coap", "zigbee", "lora", "bluetooth", "wifi",
    "aws iot", "azure iot", "google cloud iot"
]

# File and Directory Configuration
CONFIG_FILE_NAME: str = "config.ini"
LOG_DIRECTORY: str = "logs"
DATA_DIRECTORY: str = "data"
BACKUP_DIRECTORY: str = "backups"

# Validation Configuration
MIN_COMPANY_NAME_LENGTH: int = 2
MAX_COMPANY_NAME_LENGTH: int = 100
MIN_DESCRIPTION_LENGTH: int = 10
MAX_DESCRIPTION_LENGTH: int = 1000
URL_VALIDATION_TIMEOUT: int = 5

# Performance Configuration
MEMORY_LIMIT_MB: int = 512
CPU_CORES_LIMIT: int = 4
PROCESSING_TIMEOUT_HOURS: int = 4

# Lead Generation Configuration
DEFAULT_LEAD_COUNTRY: str = "US"
DEFAULT_LEAD_INDUSTRY: str = "IoT/Hardware"
DEFAULT_LEAD_SCORE: int = 8
DEFAULT_LEAD_SOURCE: str = "Web Search"
DEFAULT_EMAIL_SUBJECT_TEMPLATE: str = "Engineering partnership opportunities with {company_name}"

# Email Pattern Configuration
DEFAULT_EMAIL_PATTERNS: List[str] = [
    "info@{domain}",
    "contact@{domain}",
    "sales@{domain}",
    "hello@{domain}",
    "support@{domain}"
]

# Search Keywords Configuration - Targeting Small Startups & Companies
DEFAULT_SEARCH_KEYWORDS: List[str] = [
    "IoT startup seed funding",
    "hardware startup early stage", 
    "smart device startup prototype",
    "embedded systems startup MVP",
    "connected device prototype development",
    "IoT hardware startup Series A",
    "smart sensor startup funding",
    "wearable device startup development",
    "industrial IoT startup early stage",
    "home automation startup prototype"
]

MULTI_SOURCE_SEARCH_KEYWORDS: List[str] = [
    "startup IoT", "hardware startup", "embedded startup", "sensor startup", 
    "device startup", "prototype development", "MVP IoT", "seed stage hardware",
    "early stage connected", "startup firmware"
]

# AI Email Generation Configuration
TATVIX_COMPANY_DESCRIPTION: str = """At Tatvix Technologies we work with companies building connected hardware systems where embedded firmware, device connectivity, and backend infrastructure need to operate together reliably."""

TATVIX_CAPABILITIES: List[str] = [
    "Embedded firmware development",
    "IoT connectivity platforms",
    "Device monitoring and telemetry systems", 
    "Backend infrastructure for distributed hardware",
    "Cloud monitoring platforms",
    "Analytics dashboards",
    "Hardware-driven systems integration"
]

# Domain Filtering Configuration
EXCLUDED_DOMAINS: List[str] = [
    'example.com', 'test.com', 'localhost', '127.0.0.1', '0.0.0.0',
    'github.com', 'gitlab.com', 'bitbucket.org'
]

EXCLUDED_TLD_PATTERNS: List[str] = [
    '.local', '.test', '.example', '.invalid'
]

# Email Testing Configuration
SMTP_TEST_EMAIL: str = 'test@example.com'