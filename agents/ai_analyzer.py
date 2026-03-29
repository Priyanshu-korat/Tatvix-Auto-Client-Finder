"""AI-powered company analysis using Groq models.

This module implements intelligent company analysis for business classification,
relevance scoring, and lead qualification using multiple Groq AI models.
"""

import asyncio
import hashlib
import json
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
import logging

import httpx
from groq import Groq, AsyncGroq
from pydantic import ValidationError

from config.settings import Settings
from utils.logger import get_logger
from utils.exceptions import (
    APIError,
    ConfigurationError,
    ValidationError as CustomValidationError,
    RateLimitError
)
from .models import (
    CompanyData,
    CompanyAnalysis,
    IndustryClassification,
    RelevanceScore,
    TechnologyNeeds,
    AnalysisRequest,
    AnalysisResponse,
    AnalysisCache,
    IndustryCategory,
    CompanySizeCategory,
    BusinessStage,
    GeographicRelevance,
    TechnologyStack
)


class GroqModelConfig:
    """Configuration for Groq model selection and fallbacks."""
    
    # Primary models for different tasks
    CLASSIFICATION_MODELS = [
        "llama-3.1-70b-versatile",
        "mixtral-8x7b-32768",
        "llama-3.1-8b-instant"
    ]
    
    ANALYSIS_MODELS = [
        "llama-3.1-70b-versatile",
        "mixtral-8x7b-32768"
    ]
    
    SCORING_MODELS = [
        "llama-3.1-70b-versatile",
        "mixtral-8x7b-32768"
    ]
    
    # Model parameters
    DEFAULT_TEMPERATURE = 0.1
    DEFAULT_MAX_TOKENS = 4000
    DEFAULT_TIMEOUT = 30.0


class PromptTemplates:
    """Structured prompt templates for consistent AI analysis."""
    
    @staticmethod
    def get_classification_prompt(company_data: CompanyData) -> str:
        """Generate industry classification prompt."""
        return f"""Analyze the following company information and provide a structured industry classification.

Company URL: {company_data.url}
Company Name: {company_data.company_name or 'Unknown'}
Description: {company_data.description or 'No description available'}
Industry Hints: {', '.join(company_data.industry_hints[:10])}
Product/Service Cues: {', '.join(company_data.product_service_cues[:10])}
Technology Signals: {', '.join(company_data.technology_signals[:10])}

Respond with valid JSON matching this exact schema:
{{
    "primary_industry": "iot_software|embedded_systems|hardware_manufacturing|software_development|consulting_services|telecommunications|automotive|healthcare_tech|industrial_automation|smart_home|agriculture_tech|energy_utilities|fintech|retail_ecommerce|other",
    "secondary_industries": ["industry1", "industry2"],
    "confidence_score": 0.85,
    "reasoning": "Brief explanation of classification decision"
}}

Focus on IoT, embedded systems, and technology-related classifications. Be precise and factual."""
    
    @staticmethod
    def get_analysis_prompt(company_data: CompanyData) -> str:
        """Generate comprehensive company analysis prompt."""
        return f"""Perform a comprehensive business analysis of this company for B2B lead qualification.

Company Information:
- URL: {company_data.url}
- Name: {company_data.company_name or 'Unknown'}
- Description: {company_data.description or 'No description available'}
- Business Type: {company_data.business_type}
- Size Hint: {company_data.company_size_hint}
- Industry Hints: {', '.join(company_data.industry_hints[:15])}
- Technology Signals: {', '.join(company_data.technology_signals[:15])}
- Product/Service Cues: {', '.join(company_data.product_service_cues[:15])}
- Contact Info: {len(company_data.contact_emails)} emails, {len(company_data.contact_phones)} phones

Respond with valid JSON matching this exact schema:
{{
    "company_size": "startup_1_10|small_11_50|medium_51_200|large_200_plus|unknown",
    "business_stage": "idea|mvp|growth|mature|unknown",
    "geographic_relevance": "high|medium|low|unknown",
    "analysis_summary": "Executive summary of the company (50-1000 chars)",
    "key_insights": ["insight1", "insight2", "insight3"],
    "recommendation": "Lead qualification recommendation (20-500 chars)"
}}

Focus on technology readiness, business maturity, and potential for IoT/embedded systems partnerships."""
    
    @staticmethod
    def get_technology_prompt(company_data: CompanyData) -> str:
        """Generate technology needs analysis prompt."""
        return f"""Analyze the technology stack and needs of this company.

Company: {company_data.company_name or 'Unknown'}
Technology Signals: {', '.join(company_data.technology_signals[:20])}
Product/Service Cues: {', '.join(company_data.product_service_cues[:20])}
Industry Context: {', '.join(company_data.industry_hints[:10])}

Respond with valid JSON matching this exact schema:
{{
    "detected_technologies": ["embedded_c_cpp", "python_iot", "javascript_node"],
    "iot_relevance": 0.75,
    "embedded_relevance": 0.65,
    "cloud_integration": 0.80,
    "technology_maturity": "Brief maturity assessment (5-200 chars)",
    "compatibility_notes": "Optional compatibility observations"
}}

Focus on IoT, embedded systems, and technology stack compatibility."""
    
    @staticmethod
    def get_scoring_prompt(
        company_data: CompanyData,
        industry_classification: IndustryClassification,
        technology_needs: TechnologyNeeds
    ) -> str:
        """Generate relevance scoring prompt."""
        return f"""Score this company for B2B lead qualification using the exact weighted criteria.

Company: {company_data.company_name or 'Unknown'}
Primary Industry: {industry_classification.primary_industry}
IoT Relevance: {technology_needs.iot_relevance}
Embedded Relevance: {technology_needs.embedded_relevance}
Business Type: {company_data.business_type}
Size Hint: {company_data.company_size_hint}

Scoring Matrix (use exact weights):
- IoT Software Focus: 30% weight, max 4 points
- Embedded Systems: 25% weight, max 3 points  
- Company Size Fit: 20% weight, max 3 points
- Technology Stack: 15% weight, max 2 points
- Geographic Match: 10% weight, max 1 point

Respond with valid JSON matching this exact schema:
{{
    "iot_software_score": 3.2,
    "embedded_systems_score": 2.1,
    "company_size_score": 2.5,
    "technology_stack_score": 1.8,
    "geographic_score": 0.7,
    "total_score": 10.3,
    "weighted_percentage": 79.2,
    "score_breakdown": {{
        "iot_software_weighted": 0.96,
        "embedded_systems_weighted": 0.525,
        "company_size_weighted": 0.5,
        "technology_stack_weighted": 0.27,
        "geographic_weighted": 0.07
    }}
}}

Be precise with calculations. Total score = sum of individual scores. Weighted percentage = (total_score / 13.0) * 100."""


class AIAnalyzer:
    """AI-powered company analysis system using Groq models."""
    
    def __init__(self, config: Settings):
        """Initialize AI analyzer with configuration.
        
        Args:
            config: Application settings instance.
            
        Raises:
            ConfigurationError: If required configuration is missing.
        """
        self.config = config
        self.logger = get_logger(__name__)
        
        # Initialize Groq client
        api_key = self.config.get_secure('api', 'groq_api_key')
        if not api_key:
            raise ConfigurationError("Groq API key not found in configuration")
        
        self.groq_client = AsyncGroq(api_key=api_key)
        self.sync_groq_client = Groq(api_key=api_key)
        
        # Analysis cache
        self._analysis_cache: Dict[str, AnalysisCache] = {}
        
        # Model configuration
        self.model_config = GroqModelConfig()
        
        # Performance metrics
        self._metrics = {
            'total_analyses': 0,
            'cache_hits': 0,
            'api_calls': 0,
            'errors': 0,
            'average_duration': 0.0
        }
        
        self.logger.info("AIAnalyzer initialized with Groq integration")
    
    def _generate_cache_key(self, company_data: CompanyData) -> str:
        """Generate stable cache key from company data.
        
        Args:
            company_data: Company data for analysis.
            
        Returns:
            Stable hash key for caching.
        """
        # Create deterministic content fingerprint
        content_parts = [
            str(company_data.url),
            company_data.company_name or '',
            company_data.description or '',
            '|'.join(sorted(company_data.industry_hints)),
            '|'.join(sorted(company_data.technology_signals)),
            '|'.join(sorted(company_data.product_service_cues)),
            str(company_data.business_type),
            str(company_data.company_size_hint)
        ]
        
        content_string = '||'.join(content_parts)
        return hashlib.sha256(content_string.encode('utf-8')).hexdigest()[:16]
    
    def _get_cached_analysis(self, cache_key: str) -> Optional[CompanyAnalysis]:
        """Retrieve cached analysis if valid.
        
        Args:
            cache_key: Cache key to lookup.
            
        Returns:
            Cached analysis if valid, None otherwise.
        """
        if cache_key not in self._analysis_cache:
            return None
        
        cache_entry = self._analysis_cache[cache_key]
        
        if cache_entry.is_expired:
            del self._analysis_cache[cache_key]
            return None
        
        cache_entry.mark_accessed()
        self._metrics['cache_hits'] += 1
        
        # Mark as cache hit
        analysis = cache_entry.analysis_result.copy(deep=True)
        analysis.cache_hit = True
        
        return analysis
    
    def _cache_analysis(self, cache_key: str, analysis: CompanyAnalysis) -> None:
        """Cache analysis result.
        
        Args:
            cache_key: Cache key for storage.
            analysis: Analysis result to cache.
        """
        cache_ttl_hours = self.config.get_int('database', 'cache_ttl_hours', fallback=24)
        expires_at = datetime.utcnow() + timedelta(hours=cache_ttl_hours)
        
        cache_entry = AnalysisCache(
            cache_key=cache_key,
            analysis_result=analysis,
            expires_at=expires_at
        )
        
        self._analysis_cache[cache_key] = cache_entry
        
        # Cleanup old entries periodically
        if len(self._analysis_cache) > 1000:
            self._cleanup_cache()
    
    def _cleanup_cache(self) -> None:
        """Remove expired cache entries."""
        expired_keys = [
            key for key, entry in self._analysis_cache.items()
            if entry.is_expired
        ]
        
        for key in expired_keys:
            del self._analysis_cache[key]
        
        self.logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
    
    async def _make_groq_request(
        self,
        prompt: str,
        model: str,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """Make request to Groq API with retry logic.
        
        Args:
            prompt: Prompt text for analysis.
            model: Model name to use.
            max_retries: Maximum retry attempts.
            
        Returns:
            Parsed JSON response from API.
            
        Raises:
            APIError: If API request fails after retries.
            RateLimitError: If rate limit is exceeded.
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                self._metrics['api_calls'] += 1
                
                response = await self.groq_client.chat.completions.create(
                    model=model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a business analyst specializing in B2B lead qualification. Respond only with valid JSON matching the requested schema."
                        },
                        {
                            "role": "user", 
                            "content": prompt
                        }
                    ],
                    temperature=self.model_config.DEFAULT_TEMPERATURE,
                    max_tokens=self.model_config.DEFAULT_MAX_TOKENS,
                    timeout=self.model_config.DEFAULT_TIMEOUT
                )
                
                content = response.choices[0].message.content.strip()
                
                # Parse JSON response
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    # Try to extract JSON from response
                    import re
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        return json.loads(json_match.group())
                    raise APIError(f"Invalid JSON response from model {model}: {e}")
                
            except httpx.TimeoutException:
                last_error = APIError(f"Timeout calling Groq API with model {model}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                    
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    last_error = RateLimitError(f"Rate limit exceeded for model {model}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(5 * (attempt + 1))
                        continue
                else:
                    last_error = APIError(f"HTTP error {e.response.status_code} for model {model}")
                    
            except Exception as e:
                last_error = APIError(f"Unexpected error calling Groq API: {e}")
                
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
        
        self._metrics['errors'] += 1
        raise last_error or APIError("Failed to get response from Groq API")
    
    async def _try_models(
        self,
        prompt: str,
        models: List[str],
        operation: str
    ) -> Dict[str, Any]:
        """Try multiple models with fallback logic.
        
        Args:
            prompt: Prompt for analysis.
            models: List of models to try in order.
            operation: Operation name for logging.
            
        Returns:
            Parsed response from successful model.
            
        Raises:
            APIError: If all models fail.
        """
        last_error = None
        
        for model in models:
            try:
                self.logger.debug(f"Trying model {model} for {operation}")
                return await self._make_groq_request(prompt, model)
                
            except (APIError, RateLimitError) as e:
                last_error = e
                self.logger.warning(f"Model {model} failed for {operation}: {e}")
                continue
        
        raise last_error or APIError(f"All models failed for {operation}")
    
    async def classify_industry(self, company_data: CompanyData) -> IndustryClassification:
        """Classify company industry using AI analysis.
        
        Args:
            company_data: Scraped company data.
            
        Returns:
            Industry classification result.
            
        Raises:
            APIError: If classification fails.
        """
        prompt = PromptTemplates.get_classification_prompt(company_data)
        
        try:
            response = await self._try_models(
                prompt,
                self.model_config.CLASSIFICATION_MODELS,
                "industry_classification"
            )
            
            return IndustryClassification(**response)
            
        except ValidationError as e:
            raise CustomValidationError(f"Invalid classification response: {e}")
    
    async def detect_technology_needs(self, company_data: CompanyData) -> TechnologyNeeds:
        """Detect technology stack and needs.
        
        Args:
            company_data: Scraped company data.
            
        Returns:
            Technology needs analysis.
            
        Raises:
            APIError: If detection fails.
        """
        prompt = PromptTemplates.get_technology_prompt(company_data)
        
        try:
            response = await self._try_models(
                prompt,
                self.model_config.ANALYSIS_MODELS,
                "technology_detection"
            )
            
            return TechnologyNeeds(**response)
            
        except ValidationError as e:
            raise CustomValidationError(f"Invalid technology response: {e}")
    
    async def score_relevance(
        self,
        company_data: CompanyData,
        industry_classification: IndustryClassification,
        technology_needs: TechnologyNeeds
    ) -> RelevanceScore:
        """Score company relevance for lead qualification.
        
        Args:
            company_data: Scraped company data.
            industry_classification: Industry classification result.
            technology_needs: Technology needs analysis.
            
        Returns:
            Multi-dimensional relevance score.
            
        Raises:
            APIError: If scoring fails.
        """
        prompt = PromptTemplates.get_scoring_prompt(
            company_data,
            industry_classification,
            technology_needs
        )
        
        try:
            response = await self._try_models(
                prompt,
                self.model_config.SCORING_MODELS,
                "relevance_scoring"
            )
            
            return RelevanceScore(**response)
            
        except ValidationError as e:
            raise CustomValidationError(f"Invalid scoring response: {e}")
    
    async def analyze_company(self, company_data: CompanyData) -> CompanyAnalysis:
        """Perform complete AI-powered company analysis.
        
        Args:
            company_data: Scraped company data for analysis.
            
        Returns:
            Complete company analysis result.
            
        Raises:
            APIError: If analysis fails.
        """
        start_time = time.time()
        
        try:
            # Check cache first
            cache_key = self._generate_cache_key(company_data)
            cached_result = self._get_cached_analysis(cache_key)
            
            if cached_result:
                self.logger.debug(f"Using cached analysis for {company_data.url}")
                return cached_result
            
            # Generate unique analysis ID
            analysis_id = str(uuid.uuid4())[:8]
            
            # Perform parallel analysis components
            industry_task = self.classify_industry(company_data)
            technology_task = self.detect_technology_needs(company_data)
            
            # Get basic analysis
            analysis_prompt = PromptTemplates.get_analysis_prompt(company_data)
            analysis_task = self._try_models(
                analysis_prompt,
                self.model_config.ANALYSIS_MODELS,
                "company_analysis"
            )
            
            # Wait for all components
            industry_classification, technology_needs, analysis_data = await asyncio.gather(
                industry_task,
                technology_task,
                analysis_task
            )
            
            # Perform relevance scoring
            relevance_score = await self.score_relevance(
                company_data,
                industry_classification,
                technology_needs
            )
            
            # Determine model used (first successful model)
            model_used = self.model_config.ANALYSIS_MODELS[0]
            
            # Create complete analysis
            analysis = CompanyAnalysis(
                company_url=company_data.url,
                analysis_id=analysis_id,
                industry_classification=industry_classification,
                company_size=CompanySizeCategory(analysis_data.get('company_size', 'unknown')),
                business_stage=BusinessStage(analysis_data.get('business_stage', 'unknown')),
                geographic_relevance=GeographicRelevance(analysis_data.get('geographic_relevance', 'unknown')),
                technology_needs=technology_needs,
                relevance_score=relevance_score,
                analysis_summary=analysis_data.get('analysis_summary', 'Analysis completed'),
                key_insights=analysis_data.get('key_insights', ['Analysis completed']),
                recommendation=analysis_data.get('recommendation', 'Review required'),
                model_used=model_used,
                analysis_duration_seconds=time.time() - start_time,
                cache_hit=False
            )
            
            # Cache result
            self._cache_analysis(cache_key, analysis)
            
            # Update metrics
            self._metrics['total_analyses'] += 1
            duration = time.time() - start_time
            self._metrics['average_duration'] = (
                (self._metrics['average_duration'] * (self._metrics['total_analyses'] - 1) + duration)
                / self._metrics['total_analyses']
            )
            
            self.logger.info(
                f"Completed analysis for {company_data.url} in {duration:.2f}s "
                f"(score: {relevance_score.weighted_percentage:.1f}%)"
            )
            
            return analysis
            
        except Exception as e:
            self._metrics['errors'] += 1
            self.logger.error(f"Analysis failed for {company_data.url}: {e}")
            raise
    
    def validate_analysis_output(self, analysis: Dict[str, Any]) -> bool:
        """Validate analysis output structure and content.
        
        Args:
            analysis: Analysis dictionary to validate.
            
        Returns:
            True if valid, False otherwise.
        """
        try:
            # Validate against Pydantic model
            CompanyAnalysis(**analysis)
            
            # Additional business logic validation
            relevance_score = analysis.get('relevance_score', {})
            
            # Check score bounds
            if not (0 <= relevance_score.get('total_score', 0) <= 13):
                return False
                
            if not (0 <= relevance_score.get('weighted_percentage', 0) <= 100):
                return False
            
            # Check required fields
            required_fields = [
                'analysis_summary',
                'key_insights',
                'recommendation',
                'model_used'
            ]
            
            for field in required_fields:
                if not analysis.get(field):
                    return False
            
            return True
            
        except (ValidationError, KeyError, TypeError):
            return False
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics.
        
        Returns:
            Dictionary of performance metrics.
        """
        cache_hit_rate = (
            (self._metrics['cache_hits'] / max(self._metrics['total_analyses'], 1)) * 100
            if self._metrics['total_analyses'] > 0 else 0
        )
        
        return {
            **self._metrics,
            'cache_hit_rate_percent': round(cache_hit_rate, 2),
            'cache_entries': len(self._analysis_cache)
        }
    
    def clear_cache(self) -> None:
        """Clear analysis cache."""
        self._analysis_cache.clear()
        self.logger.info("Analysis cache cleared")