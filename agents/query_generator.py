"""Query generation utilities for targeted search.

This module provides intelligent query generation with templates,
geographic targeting, and industry-specific optimization.
"""

import random
import logging
from typing import List, Dict, Optional, Set, Tuple
from enum import Enum
from dataclasses import dataclass

from .models import TargetType, SearchQuery
from utils.logger import get_logger


logger = get_logger(__name__)


class QueryCategory(str, Enum):
    """Query category enumeration."""
    COMPANY_TYPE = "company_type"
    TECHNOLOGY = "technology"
    SERVICE = "service"
    INDUSTRY = "industry"
    GEOGRAPHIC = "geographic"
    COMBINATION = "combination"


@dataclass
class QueryTemplate:
    """Query template configuration."""
    
    template: str
    category: QueryCategory
    target_type: TargetType
    priority: int = 1
    requires_location: bool = False
    variations: Optional[List[str]] = None


class QueryGenerator:
    """Intelligent search query generator.
    
    Generates optimized search queries based on target types,
    geographic regions, and industry focus areas.
    """
    
    # Base query templates by target type
    QUERY_TEMPLATES = {
        TargetType.IOT_SOFTWARE: [
            QueryTemplate(
                "iot software development company",
                QueryCategory.COMPANY_TYPE,
                TargetType.IOT_SOFTWARE,
                priority=5
            ),
            QueryTemplate(
                "iot application development services",
                QueryCategory.SERVICE,
                TargetType.IOT_SOFTWARE,
                priority=4
            ),
            QueryTemplate(
                "internet of things software solutions",
                QueryCategory.TECHNOLOGY,
                TargetType.IOT_SOFTWARE,
                priority=4
            ),
            QueryTemplate(
                "iot platform development",
                QueryCategory.TECHNOLOGY,
                TargetType.IOT_SOFTWARE,
                priority=3
            ),
            QueryTemplate(
                "connected device software",
                QueryCategory.TECHNOLOGY,
                TargetType.IOT_SOFTWARE,
                priority=3
            ),
            QueryTemplate(
                "iot cloud platform",
                QueryCategory.TECHNOLOGY,
                TargetType.IOT_SOFTWARE,
                priority=2
            ),
            QueryTemplate(
                "smart device application development",
                QueryCategory.SERVICE,
                TargetType.IOT_SOFTWARE,
                priority=2
            )
        ],
        
        TargetType.EMBEDDED_SYSTEMS: [
            QueryTemplate(
                "embedded systems company",
                QueryCategory.COMPANY_TYPE,
                TargetType.EMBEDDED_SYSTEMS,
                priority=5
            ),
            QueryTemplate(
                "firmware development services",
                QueryCategory.SERVICE,
                TargetType.EMBEDDED_SYSTEMS,
                priority=5
            ),
            QueryTemplate(
                "embedded software development",
                QueryCategory.TECHNOLOGY,
                TargetType.EMBEDDED_SYSTEMS,
                priority=4
            ),
            QueryTemplate(
                "microcontroller programming",
                QueryCategory.TECHNOLOGY,
                TargetType.EMBEDDED_SYSTEMS,
                priority=3
            ),
            QueryTemplate(
                "real-time systems development",
                QueryCategory.TECHNOLOGY,
                TargetType.EMBEDDED_SYSTEMS,
                priority=3
            ),
            QueryTemplate(
                "embedded linux development",
                QueryCategory.TECHNOLOGY,
                TargetType.EMBEDDED_SYSTEMS,
                priority=2
            ),
            QueryTemplate(
                "rtos development services",
                QueryCategory.SERVICE,
                TargetType.EMBEDDED_SYSTEMS,
                priority=2
            )
        ],
        
        TargetType.HARDWARE_STARTUP: [
            QueryTemplate(
                "hardware startup",
                QueryCategory.COMPANY_TYPE,
                TargetType.HARDWARE_STARTUP,
                priority=5
            ),
            QueryTemplate(
                "iot product development",
                QueryCategory.SERVICE,
                TargetType.HARDWARE_STARTUP,
                priority=4
            ),
            QueryTemplate(
                "electronic product design",
                QueryCategory.SERVICE,
                TargetType.HARDWARE_STARTUP,
                priority=4
            ),
            QueryTemplate(
                "hardware prototyping company",
                QueryCategory.COMPANY_TYPE,
                TargetType.HARDWARE_STARTUP,
                priority=3
            ),
            QueryTemplate(
                "pcb design services",
                QueryCategory.SERVICE,
                TargetType.HARDWARE_STARTUP,
                priority=3
            ),
            QueryTemplate(
                "consumer electronics startup",
                QueryCategory.COMPANY_TYPE,
                TargetType.HARDWARE_STARTUP,
                priority=2
            ),
            QueryTemplate(
                "hardware innovation company",
                QueryCategory.COMPANY_TYPE,
                TargetType.HARDWARE_STARTUP,
                priority=2
            )
        ],
        
        TargetType.INDUSTRY_SPECIFIC: [
            QueryTemplate(
                "smart agriculture iot",
                QueryCategory.INDUSTRY,
                TargetType.INDUSTRY_SPECIFIC,
                priority=4
            ),
            QueryTemplate(
                "industrial iot solutions",
                QueryCategory.INDUSTRY,
                TargetType.INDUSTRY_SPECIFIC,
                priority=4
            ),
            QueryTemplate(
                "smart manufacturing systems",
                QueryCategory.INDUSTRY,
                TargetType.INDUSTRY_SPECIFIC,
                priority=3
            ),
            QueryTemplate(
                "automotive iot technology",
                QueryCategory.INDUSTRY,
                TargetType.INDUSTRY_SPECIFIC,
                priority=3
            ),
            QueryTemplate(
                "healthcare iot devices",
                QueryCategory.INDUSTRY,
                TargetType.INDUSTRY_SPECIFIC,
                priority=3
            ),
            QueryTemplate(
                "smart city solutions",
                QueryCategory.INDUSTRY,
                TargetType.INDUSTRY_SPECIFIC,
                priority=2
            ),
            QueryTemplate(
                "energy monitoring systems",
                QueryCategory.INDUSTRY,
                TargetType.INDUSTRY_SPECIFIC,
                priority=2
            ),
            QueryTemplate(
                "retail iot solutions",
                QueryCategory.INDUSTRY,
                TargetType.INDUSTRY_SPECIFIC,
                priority=2
            )
        ]
    }
    
    # Geographic modifiers
    GEOGRAPHIC_MODIFIERS = {
        'US': ['USA', 'United States', 'America'],
        'CA': ['Canada', 'Canadian'],
        'GB': ['UK', 'United Kingdom', 'Britain', 'British'],
        'DE': ['Germany', 'German'],
        'FR': ['France', 'French'],
        'IT': ['Italy', 'Italian'],
        'ES': ['Spain', 'Spanish'],
        'NL': ['Netherlands', 'Dutch'],
        'SE': ['Sweden', 'Swedish'],
        'NO': ['Norway', 'Norwegian'],
        'DK': ['Denmark', 'Danish'],
        'FI': ['Finland', 'Finnish'],
        'AU': ['Australia', 'Australian'],
        'JP': ['Japan', 'Japanese'],
        'KR': ['Korea', 'Korean', 'South Korea'],
        'SG': ['Singapore'],
        'IN': ['India', 'Indian'],
        'IL': ['Israel', 'Israeli'],
        'CH': ['Switzerland', 'Swiss']
    }
    
    # City modifiers for major tech hubs
    TECH_CITIES = {
        'US': [
            'Silicon Valley', 'San Francisco', 'Seattle', 'Austin', 'Boston',
            'New York', 'Los Angeles', 'Denver', 'Portland', 'San Diego'
        ],
        'CA': ['Toronto', 'Vancouver', 'Montreal', 'Ottawa'],
        'GB': ['London', 'Cambridge', 'Edinburgh', 'Manchester'],
        'DE': ['Berlin', 'Munich', 'Hamburg', 'Frankfurt'],
        'FR': ['Paris', 'Lyon', 'Toulouse', 'Nice'],
        'NL': ['Amsterdam', 'Eindhoven', 'Utrecht'],
        'SE': ['Stockholm', 'Gothenburg', 'Malmö'],
        'AU': ['Sydney', 'Melbourne', 'Brisbane'],
        'JP': ['Tokyo', 'Osaka', 'Kyoto'],
        'IN': ['Bangalore', 'Mumbai', 'Delhi', 'Hyderabad', 'Chennai', 'Pune'],
        'IL': ['Tel Aviv', 'Jerusalem', 'Haifa']
    }
    
    # Query modifiers and variations
    COMPANY_MODIFIERS = [
        'company', 'startup', 'firm', 'business', 'enterprise',
        'corporation', 'solutions', 'technologies', 'systems',
        'services', 'consulting', 'development'
    ]
    
    def __init__(self):
        """Initialize query generator."""
        self._used_queries: Set[str] = set()
        logger.info("QueryGenerator initialized")
    
    def generate_queries(
        self,
        target_type: TargetType,
        country: Optional[str] = None,
        max_queries: int = 10,
        include_geographic: bool = True,
        include_variations: bool = True
    ) -> List[SearchQuery]:
        """Generate search queries for target type and location.
        
        Args:
            target_type: Type of companies to target.
            country: ISO country code for geographic targeting.
            max_queries: Maximum number of queries to generate.
            include_geographic: Whether to include location-based queries.
            include_variations: Whether to include query variations.
            
        Returns:
            List of generated search queries.
        """
        queries = []
        
        # Get base templates for target type
        templates = self.QUERY_TEMPLATES.get(target_type, [])
        if not templates:
            logger.warning(f"No templates found for target type: {target_type}")
            return queries
        
        # Sort templates by priority
        templates = sorted(templates, key=lambda t: t.priority, reverse=True)
        
        # Generate base queries
        for template in templates[:max_queries]:
            query = SearchQuery(
                query=template.template,
                target_type=target_type,
                country=country,
                max_results=50,
                timeout=15
            )
            queries.append(query)
        
        # Add geographic variations if requested
        if include_geographic and country:
            geo_queries = self._generate_geographic_queries(
                templates[:max_queries//2], country, target_type
            )
            queries.extend(geo_queries)
        
        # Add query variations if requested
        if include_variations:
            variation_queries = self._generate_query_variations(
                templates[:max_queries//3], target_type, country
            )
            queries.extend(variation_queries)
        
        # Limit to max_queries and remove duplicates
        unique_queries = self._deduplicate_queries(queries)
        result_queries = unique_queries[:max_queries]
        
        logger.info(
            f"Generated {len(result_queries)} queries for {target_type} "
            f"in {country or 'global'}"
        )
        
        return result_queries
    
    def _generate_geographic_queries(
        self,
        templates: List[QueryTemplate],
        country: str,
        target_type: TargetType
    ) -> List[SearchQuery]:
        """Generate location-specific queries.
        
        Args:
            templates: Base query templates.
            country: ISO country code.
            target_type: Target company type.
            
        Returns:
            List of geographic queries.
        """
        geo_queries = []
        
        # Get country modifiers
        country_names = self.GEOGRAPHIC_MODIFIERS.get(country, [country])
        cities = self.TECH_CITIES.get(country, [])
        
        for template in templates:
            # Country-based queries
            for country_name in country_names[:2]:  # Limit variations
                query_text = f"{template.template} {country_name}"
                geo_queries.append(SearchQuery(
                    query=query_text,
                    target_type=target_type,
                    country=country,
                    region=country_name,
                    max_results=30
                ))
            
            # City-based queries for major tech hubs
            for city in cities[:3]:  # Limit to top 3 cities
                query_text = f"{template.template} {city}"
                geo_queries.append(SearchQuery(
                    query=query_text,
                    target_type=target_type,
                    country=country,
                    region=city,
                    max_results=20
                ))
        
        return geo_queries
    
    def _generate_query_variations(
        self,
        templates: List[QueryTemplate],
        target_type: TargetType,
        country: Optional[str]
    ) -> List[SearchQuery]:
        """Generate query variations using synonyms and modifiers.
        
        Args:
            templates: Base query templates.
            target_type: Target company type.
            country: ISO country code.
            
        Returns:
            List of query variations.
        """
        variations = []
        
        for template in templates:
            # Generate modifier variations
            base_words = template.template.split()
            
            # Replace 'company' with other modifiers
            if 'company' in base_words:
                for modifier in self.COMPANY_MODIFIERS[:3]:
                    if modifier != 'company':
                        varied_query = template.template.replace('company', modifier)
                        variations.append(SearchQuery(
                            query=varied_query,
                            target_type=target_type,
                            country=country,
                            max_results=30
                        ))
            
            # Add service-oriented variations
            if template.category == QueryCategory.COMPANY_TYPE:
                service_variation = f"{template.template} services"
                variations.append(SearchQuery(
                    query=service_variation,
                    target_type=target_type,
                    country=country,
                    max_results=25
                ))
        
        return variations
    
    def _deduplicate_queries(self, queries: List[SearchQuery]) -> List[SearchQuery]:
        """Remove duplicate queries based on normalized text.
        
        Args:
            queries: List of queries to deduplicate.
            
        Returns:
            Deduplicated query list.
        """
        seen_queries = set()
        unique_queries = []
        
        for query in queries:
            normalized = self._normalize_query(query.query)
            if normalized not in seen_queries:
                seen_queries.add(normalized)
                unique_queries.append(query)
        
        return unique_queries
    
    def _normalize_query(self, query: str) -> str:
        """Normalize query for deduplication.
        
        Args:
            query: Query string to normalize.
            
        Returns:
            Normalized query string.
        """
        # Convert to lowercase and remove extra spaces
        normalized = ' '.join(query.lower().split())
        
        # Remove common variations that don't change meaning
        replacements = {
            'internet of things': 'iot',
            'iot iot': 'iot',  # Handle double replacements
            'company services': 'company',
            'startup company': 'startup'
        }
        
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)
        
        return normalized
    
    def generate_batch_queries(
        self,
        target_types: List[TargetType],
        countries: List[str],
        queries_per_combination: int = 5
    ) -> Dict[Tuple[TargetType, str], List[SearchQuery]]:
        """Generate queries for multiple target types and countries.
        
        Args:
            target_types: List of target company types.
            countries: List of ISO country codes.
            queries_per_combination: Queries per type/country combination.
            
        Returns:
            Dictionary mapping (target_type, country) to query lists.
        """
        batch_queries = {}
        
        for target_type in target_types:
            for country in countries:
                key = (target_type, country)
                queries = self.generate_queries(
                    target_type=target_type,
                    country=country,
                    max_queries=queries_per_combination,
                    include_geographic=True,
                    include_variations=True
                )
                batch_queries[key] = queries
        
        total_queries = sum(len(queries) for queries in batch_queries.values())
        logger.info(
            f"Generated batch queries: {total_queries} total queries "
            f"for {len(target_types)} types and {len(countries)} countries"
        )
        
        return batch_queries
    
    def get_query_statistics(self) -> Dict[str, int]:
        """Get statistics about available query templates.
        
        Returns:
            Dictionary with template statistics.
        """
        stats = {}
        
        for target_type, templates in self.QUERY_TEMPLATES.items():
            stats[target_type.value] = {
                'total_templates': len(templates),
                'high_priority': len([t for t in templates if t.priority >= 4]),
                'categories': len(set(t.category for t in templates))
            }
        
        stats['geographic_countries'] = len(self.GEOGRAPHIC_MODIFIERS)
        stats['tech_cities'] = sum(len(cities) for cities in self.TECH_CITIES.values())
        
        return stats
    
    def clear_used_queries(self) -> None:
        """Clear the used queries cache."""
        self._used_queries.clear()
        logger.debug("Cleared used queries cache")