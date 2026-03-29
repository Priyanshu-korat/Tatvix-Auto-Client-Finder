"""Input validation utilities for Tatvix AI Client Discovery System.

This module provides validation functions and decorators for ensuring
data integrity and security throughout the application.
"""

import re
import urllib.parse
from typing import Any, Callable, Dict, List, Optional, Union
from functools import wraps

from utils.exceptions import ValidationError
from config.constants import (
    EMAIL_REGEX_PATTERN,
    MIN_COMPANY_NAME_LENGTH,
    MAX_COMPANY_NAME_LENGTH,
    MIN_DESCRIPTION_LENGTH,
    MAX_DESCRIPTION_LENGTH,
    MAX_EMAIL_LENGTH,
    URL_VALIDATION_TIMEOUT
)


def validate_required(value: Any, field_name: str) -> Any:
    """Validate that a value is not None or empty.
    
    Args:
        value: Value to validate.
        field_name: Name of the field being validated.
        
    Returns:
        The validated value.
        
    Raises:
        ValidationError: If value is None or empty.
    """
    if value is None:
        raise ValidationError(
            f"Field '{field_name}' is required",
            field_name=field_name,
            validation_rule="required"
        )
    
    if isinstance(value, str) and not value.strip():
        raise ValidationError(
            f"Field '{field_name}' cannot be empty",
            field_name=field_name,
            field_value=value,
            validation_rule="not_empty"
        )
    
    return value


def validate_email(email: str, field_name: str = "email") -> str:
    """Validate email address format.
    
    Args:
        email: Email address to validate.
        field_name: Name of the field being validated.
        
    Returns:
        Normalized email address (lowercase).
        
    Raises:
        ValidationError: If email format is invalid.
    """
    validate_required(email, field_name)
    
    # Check length
    if len(email) > MAX_EMAIL_LENGTH:
        raise ValidationError(
            f"Email address too long (maximum {MAX_EMAIL_LENGTH} characters)",
            field_name=field_name,
            field_value=email,
            validation_rule="max_length"
        )
    
    # Check format using regex
    if not re.match(EMAIL_REGEX_PATTERN, email):
        raise ValidationError(
            f"Invalid email format: {email}",
            field_name=field_name,
            field_value=email,
            validation_rule="email_format"
        )
    
    # Additional validation for common issues
    if email.count('@') != 1:
        raise ValidationError(
            "Email must contain exactly one '@' symbol",
            field_name=field_name,
            field_value=email,
            validation_rule="single_at_symbol"
        )
    
    local_part, domain = email.split('@')
    
    # Validate local part
    if not local_part or len(local_part) > 64:
        raise ValidationError(
            "Email local part must be 1-64 characters",
            field_name=field_name,
            field_value=email,
            validation_rule="local_part_length"
        )
    
    # Validate domain
    if not domain or len(domain) > 253:
        raise ValidationError(
            "Email domain must be 1-253 characters",
            field_name=field_name,
            field_value=email,
            validation_rule="domain_length"
        )
    
    # Check for valid domain format
    domain_parts = domain.split('.')
    if len(domain_parts) < 2:
        raise ValidationError(
            "Email domain must contain at least one dot",
            field_name=field_name,
            field_value=email,
            validation_rule="domain_format"
        )
    
    return email.lower().strip()


def validate_url(url: str, field_name: str = "url", 
                 allowed_schemes: Optional[List[str]] = None) -> str:
    """Validate URL format and structure.
    
    Args:
        url: URL to validate.
        field_name: Name of the field being validated.
        allowed_schemes: List of allowed URL schemes (default: ['http', 'https']).
        
    Returns:
        Normalized URL.
        
    Raises:
        ValidationError: If URL format is invalid.
    """
    validate_required(url, field_name)
    
    if allowed_schemes is None:
        allowed_schemes = ['http', 'https']
    
    try:
        parsed = urllib.parse.urlparse(url.strip())
    except Exception as e:
        raise ValidationError(
            f"Invalid URL format: {str(e)}",
            field_name=field_name,
            field_value=url,
            validation_rule="url_parse"
        )
    
    # Check scheme
    if not parsed.scheme:
        raise ValidationError(
            "URL must include a scheme (http:// or https://)",
            field_name=field_name,
            field_value=url,
            validation_rule="missing_scheme"
        )
    
    if parsed.scheme.lower() not in allowed_schemes:
        raise ValidationError(
            f"URL scheme must be one of: {', '.join(allowed_schemes)}",
            field_name=field_name,
            field_value=url,
            validation_rule="invalid_scheme"
        )
    
    # Check netloc (domain)
    if not parsed.netloc:
        raise ValidationError(
            "URL must include a domain name",
            field_name=field_name,
            field_value=url,
            validation_rule="missing_domain"
        )
    
    # Basic domain format validation
    domain_pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
    if not re.match(domain_pattern, parsed.netloc.split(':')[0]):
        raise ValidationError(
            "Invalid domain name format",
            field_name=field_name,
            field_value=url,
            validation_rule="invalid_domain"
        )
    
    return url.strip()


def validate_domain(domain: str, field_name: str = "domain") -> str:
    """Validate domain name format.
    
    Args:
        domain: Domain name to validate.
        field_name: Name of the field being validated.
        
    Returns:
        Normalized domain name (lowercase).
        
    Raises:
        ValidationError: If domain format is invalid.
    """
    validate_required(domain, field_name)
    
    cleaned_domain = domain.strip().lower()
    
    # Remove protocol if present
    if cleaned_domain.startswith(('http://', 'https://')):
        parsed = urllib.parse.urlparse(cleaned_domain)
        cleaned_domain = parsed.netloc
    
    # Remove port if present
    if ':' in cleaned_domain:
        cleaned_domain = cleaned_domain.split(':')[0]
    
    # Basic domain format validation
    domain_pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
    if not re.match(domain_pattern, cleaned_domain):
        raise ValidationError(
            "Invalid domain name format",
            field_name=field_name,
            field_value=domain,
            validation_rule="invalid_domain"
        )
    
    # Check for at least one dot (TLD required)
    if '.' not in cleaned_domain:
        raise ValidationError(
            "Domain must include a top-level domain",
            field_name=field_name,
            field_value=domain,
            validation_rule="missing_tld"
        )
    
    return cleaned_domain


def validate_company_name(name: str, field_name: str = "company_name") -> str:
    """Validate company name.
    
    Args:
        name: Company name to validate.
        field_name: Name of the field being validated.
        
    Returns:
        Cleaned company name.
        
    Raises:
        ValidationError: If company name is invalid.
    """
    validate_required(name, field_name)
    
    cleaned_name = name.strip()
    
    # Check length
    if len(cleaned_name) < MIN_COMPANY_NAME_LENGTH:
        raise ValidationError(
            f"Company name too short (minimum {MIN_COMPANY_NAME_LENGTH} characters)",
            field_name=field_name,
            field_value=name,
            validation_rule="min_length"
        )
    
    if len(cleaned_name) > MAX_COMPANY_NAME_LENGTH:
        raise ValidationError(
            f"Company name too long (maximum {MAX_COMPANY_NAME_LENGTH} characters)",
            field_name=field_name,
            field_value=name,
            validation_rule="max_length"
        )
    
    # Check for valid characters (letters, numbers, spaces, common punctuation)
    valid_pattern = r'^[a-zA-Z0-9\s\.\-_&,()]+$'
    if not re.match(valid_pattern, cleaned_name):
        raise ValidationError(
            "Company name contains invalid characters",
            field_name=field_name,
            field_value=name,
            validation_rule="invalid_characters"
        )
    
    return cleaned_name


def validate_description(description: str, field_name: str = "description") -> str:
    """Validate company description.
    
    Args:
        description: Description to validate.
        field_name: Name of the field being validated.
        
    Returns:
        Cleaned description.
        
    Raises:
        ValidationError: If description is invalid.
    """
    validate_required(description, field_name)
    
    cleaned_description = description.strip()
    
    # Check length
    if len(cleaned_description) < MIN_DESCRIPTION_LENGTH:
        raise ValidationError(
            f"Description too short (minimum {MIN_DESCRIPTION_LENGTH} characters)",
            field_name=field_name,
            field_value=description,
            validation_rule="min_length"
        )
    
    if len(cleaned_description) > MAX_DESCRIPTION_LENGTH:
        raise ValidationError(
            f"Description too long (maximum {MAX_DESCRIPTION_LENGTH} characters)",
            field_name=field_name,
            field_value=description,
            validation_rule="max_length"
        )
    
    return cleaned_description


def validate_country_code(country_code: str, field_name: str = "country_code") -> str:
    """Validate ISO country code.
    
    Args:
        country_code: Country code to validate.
        field_name: Name of the field being validated.
        
    Returns:
        Uppercase country code.
        
    Raises:
        ValidationError: If country code is invalid.
    """
    validate_required(country_code, field_name)
    
    cleaned_code = country_code.strip().upper()
    
    # Check length (ISO 3166-1 alpha-2)
    if len(cleaned_code) != 2:
        raise ValidationError(
            "Country code must be exactly 2 characters (ISO 3166-1 alpha-2)",
            field_name=field_name,
            field_value=country_code,
            validation_rule="iso_alpha2_length"
        )
    
    # Check format (letters only)
    if not cleaned_code.isalpha():
        raise ValidationError(
            "Country code must contain only letters",
            field_name=field_name,
            field_value=country_code,
            validation_rule="letters_only"
        )
    
    return cleaned_code


def validate_score(score: Union[int, float], field_name: str = "score",
                  min_score: float = 0.0, max_score: float = 10.0) -> float:
    """Validate score value.
    
    Args:
        score: Score to validate.
        field_name: Name of the field being validated.
        min_score: Minimum allowed score.
        max_score: Maximum allowed score.
        
    Returns:
        Validated score as float.
        
    Raises:
        ValidationError: If score is invalid.
    """
    validate_required(score, field_name)
    
    try:
        score_float = float(score)
    except (ValueError, TypeError):
        raise ValidationError(
            "Score must be a number",
            field_name=field_name,
            field_value=str(score),
            validation_rule="numeric"
        )
    
    if score_float < min_score:
        raise ValidationError(
            f"Score must be at least {min_score}",
            field_name=field_name,
            field_value=str(score),
            validation_rule="min_value"
        )
    
    if score_float > max_score:
        raise ValidationError(
            f"Score must not exceed {max_score}",
            field_name=field_name,
            field_value=str(score),
            validation_rule="max_value"
        )
    
    return score_float


def validation_decorator(*validators: Callable[[Any, str], Any]):
    """Decorator for applying multiple validators to function arguments.
    
    Args:
        validators: Validator functions to apply.
        
    Returns:
        Decorator function.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Get function signature for parameter names
            import inspect
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            
            # Apply validators to arguments
            for validator in validators:
                for param_name, param_value in bound_args.arguments.items():
                    if param_value is not None:
                        try:
                            validated_value = validator(param_value, param_name)
                            bound_args.arguments[param_name] = validated_value
                        except ValidationError:
                            # Re-raise validation errors
                            raise
                        except Exception:
                            # Skip validation if validator doesn't apply to this parameter
                            continue
            
            return func(*bound_args.args, **bound_args.kwargs)
        return wrapper
    return decorator


def validate_dict_schema(data: Dict[str, Any], schema: Dict[str, Dict[str, Any]],
                        strict: bool = True) -> Dict[str, Any]:
    """Validate dictionary against a schema.
    
    Args:
        data: Dictionary to validate.
        schema: Schema definition with field requirements.
        strict: If True, disallow extra fields not in schema.
        
    Returns:
        Validated and cleaned dictionary.
        
    Raises:
        ValidationError: If data doesn't match schema.
    """
    validated_data = {}
    
    # Check required fields
    for field_name, field_config in schema.items():
        is_required = field_config.get('required', False)
        field_type = field_config.get('type', str)
        validator_func = field_config.get('validator')
        
        if field_name not in data:
            if is_required:
                raise ValidationError(
                    f"Required field '{field_name}' is missing",
                    field_name=field_name,
                    validation_rule="required"
                )
            continue
        
        value = data[field_name]
        
        # Type validation
        if not isinstance(value, field_type):
            raise ValidationError(
                f"Field '{field_name}' must be of type {field_type.__name__}",
                field_name=field_name,
                field_value=str(value),
                validation_rule="type_check"
            )
        
        # Custom validator
        if validator_func:
            value = validator_func(value, field_name)
        
        validated_data[field_name] = value
    
    # Check for extra fields in strict mode
    if strict:
        extra_fields = set(data.keys()) - set(schema.keys())
        if extra_fields:
            raise ValidationError(
                f"Unexpected fields: {', '.join(extra_fields)}",
                validation_rule="no_extra_fields"
            )
    
    return validated_data