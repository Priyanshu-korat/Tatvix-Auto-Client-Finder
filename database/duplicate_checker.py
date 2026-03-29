"""Advanced duplicate detection system for Tatvix AI Client Discovery.

This module implements a sophisticated multi-level duplicate detection system
using domain normalization, embedding similarity, and business logic to prevent
duplicate leads in the discovery pipeline.
"""

import asyncio
import hashlib
import logging
import time
import uuid
from typing import List, Dict, Any, Optional, Tuple, Set
from urllib.parse import urlparse
import re

import numpy as np
from rapidfuzz import fuzz
from phonenumbers import parse as parse_phone, is_valid_number, format_number, PhoneNumberFormat
from phonenumbers.phonenumberutil import NumberParseException

from config.settings import Settings
from agents.models import CompanyData
from agents.url_utils import URLUtilities
from utils.logger import get_logger
from .models import (
    SimilarCompany, DuplicateDecision, DuplicateLevel, DuplicateDecisionType,
    SimilarityMetrics, DuplicateCheckRequest, DuplicateCheckResponse,
    BatchDuplicateCheckRequest, BatchDuplicateCheckResponse
)
from .vector_store import VectorStore, InMemoryVectorStore, SimilarityResult
from .vector_factory import create_vector_store


logger = get_logger(__name__)


class DuplicateChecker:
    """Advanced duplicate detection system with multi-level checking.
    
    Implements three levels of duplicate detection:
    1. Level 1: Domain normalization and exact matching
    2. Level 2: Embedding similarity using vector search
    3. Level 3: Business logic with fuzzy matching
    """
    
    def __init__(self, config: Settings, vector_store: Optional[VectorStore] = None) -> None:
        """Initialize duplicate checker.
        
        Args:
            config: Application settings.
            vector_store: Vector store for embedding similarity. If None, creates InMemoryVectorStore.
        """
        self.config = config
        self.vector_store = vector_store or create_vector_store(config=config)
        
        # Load configuration
        self.similarity_threshold = config.get_float('duplicate_detection', 'similarity_threshold', 0.90)
        self.embedding_threshold = config.get_float('duplicate_detection', 'embedding_similarity_threshold', 0.85)
        self.business_logic_threshold = config.get_float('duplicate_detection', 'business_logic_threshold', 0.80)
        self.fuzzy_name_threshold = config.get_float('duplicate_detection', 'fuzzy_name_threshold', 0.85)
        self.location_threshold = config.get_float('duplicate_detection', 'location_similarity_threshold', 0.75)
        self.phone_threshold = config.get_float('duplicate_detection', 'phone_similarity_threshold', 0.90)
        self.technology_threshold = config.get_float('duplicate_detection', 'technology_overlap_threshold', 0.60)
        
        # Similarity weights
        self.name_weight = config.get_float('duplicate_detection', 'name_similarity_weight', 0.30)
        self.description_weight = config.get_float('duplicate_detection', 'description_similarity_weight', 0.25)
        self.location_weight = config.get_float('duplicate_detection', 'location_similarity_weight', 0.15)
        self.phone_weight = config.get_float('duplicate_detection', 'phone_similarity_weight', 0.10)
        self.technology_weight = config.get_float('duplicate_detection', 'technology_similarity_weight', 0.20)
        
        # Performance settings
        self.max_similar_companies = config.get_int('duplicate_detection', 'max_similar_companies', 10)
        self.performance_target_ms = config.get_float('duplicate_detection', 'performance_target_ms', 100.0)
        
        # Cache for domain normalization
        self._domain_cache: Dict[str, str] = {}
        self._known_domains: Set[str] = set()
        
        # Statistics
        self._stats = {
            'total_checks': 0,
            'duplicates_found': 0,
            'level_1_matches': 0,
            'level_2_matches': 0,
            'level_3_matches': 0,
            'cache_hits': 0,
            'average_duration_ms': 0.0
        }
        
        logger.info(f"Initialized DuplicateChecker with thresholds: "
                   f"similarity={self.similarity_threshold}, "
                   f"embedding={self.embedding_threshold}, "
                   f"business_logic={self.business_logic_threshold}")
    
    def normalize_domain(self, url: str) -> Optional[str]:
        """Normalize domain for consistent duplicate detection.
        
        Level 1: Domain normalization with URL parsing, scheme normalization,
        lowercase host, www stripping, and trailing slash handling.
        
        Args:
            url: Raw URL string to normalize.
            
        Returns:
            Normalized domain string or None if invalid.
        """
        if not url or not isinstance(url, str):
            return None
        
        # Check cache first
        if url in self._domain_cache:
            return self._domain_cache[url]
        
        try:
            # Use existing URL utilities for basic normalization
            normalized_url = URLUtilities.normalize_url(url)
            if not normalized_url:
                return None
            
            # Extract domain from normalized URL
            domain = URLUtilities.extract_domain(normalized_url)
            if not domain:
                return None
            
            # Additional normalization for duplicate detection
            normalized_domain = self._normalize_domain_for_duplicates(domain)
            
            # Cache result
            self._domain_cache[url] = normalized_domain
            
            logger.debug(f"Normalized domain: {url} -> {normalized_domain}")
            return normalized_domain
            
        except Exception as e:
            logger.error(f"Domain normalization failed for {url}: {e}")
            return None
    
    def _normalize_domain_for_duplicates(self, domain: str) -> str:
        """Additional domain normalization specific to duplicate detection.
        
        Args:
            domain: Basic normalized domain.
            
        Returns:
            Domain normalized for duplicate detection.
        """
        if not domain:
            return domain
        
        # Convert to lowercase
        domain = domain.lower().strip()
        
        # Remove common prefixes that might indicate the same company
        prefixes_to_remove = ['www.', 'web.', 'site.', 'home.', 'main.']
        for prefix in prefixes_to_remove:
            if domain.startswith(prefix):
                domain = domain[len(prefix):]
                break
        
        # Handle common subdomain variations
        parts = domain.split('.')
        if len(parts) > 2:
            # Check for common subdomains that should be collapsed
            subdomain = parts[0]
            if subdomain in {'app', 'portal', 'client', 'customer', 'admin', 'secure'}:
                domain = '.'.join(parts[1:])
        
        return domain
    
    async def check_domain_duplicates(self, domain: str) -> bool:
        """Check for domain-based duplicates.
        
        Level 1: Fast boolean check against known domain set.
        
        Args:
            domain: Normalized domain to check.
            
        Returns:
            True if domain is a duplicate, False otherwise.
        """
        if not domain:
            return False
        
        normalized_domain = self.normalize_domain(domain)
        if not normalized_domain:
            return False
        
        # Check against known domains
        is_duplicate = normalized_domain in self._known_domains
        
        if is_duplicate:
            self._stats['level_1_matches'] += 1
            logger.debug(f"Level 1 duplicate found: {normalized_domain}")
        
        return is_duplicate
    
    async def check_embedding_similarity(
        self,
        company_data: Dict[str, Any],
        similarity_threshold: Optional[float] = None
    ) -> List[SimilarCompany]:
        """Check for embedding-based similarity.
        
        Level 2: Vector-based company similarity detection using embeddings
        of company description and other textual content.
        
        Args:
            company_data: Company data dictionary.
            similarity_threshold: Override default similarity threshold.
            
        Returns:
            List of similar companies found above threshold.
        """
        threshold = similarity_threshold or self.embedding_threshold
        
        try:
            # Generate embedding for company
            embedding = await self._generate_company_embedding(company_data)
            if embedding is None:
                logger.warning("Failed to generate embedding for company")
                return []
            
            # Get domain for exclusion
            company_url = company_data.get('url') or company_data.get('company_url', '')
            exclude_domain = self.normalize_domain(company_url) if company_url else None
            exclude_domains = [exclude_domain] if exclude_domain else []
            
            # Search for similar embeddings
            start_time = time.time()
            similarity_results = await self.vector_store.find_similar(
                embedding=embedding,
                top_k=self.max_similar_companies,
                similarity_threshold=threshold,
                exclude_domains=exclude_domains
            )
            search_duration = (time.time() - start_time) * 1000
            
            # Convert to SimilarCompany objects
            similar_companies = []
            for result in similarity_results:
                similar_company = await self._create_similar_company_from_embedding(
                    result, company_data, DuplicateLevel.LEVEL_2_EMBEDDING
                )
                if similar_company:
                    similar_companies.append(similar_company)
            
            if similar_companies:
                self._stats['level_2_matches'] += len(similar_companies)
                logger.debug(f"Level 2 found {len(similar_companies)} similar companies "
                           f"in {search_duration:.1f}ms")
            
            return similar_companies
            
        except Exception as e:
            logger.error(f"Embedding similarity check failed: {e}")
            return []
    
    def check_business_logic_duplicates(self, company: CompanyData) -> List[SimilarCompany]:
        """Check for business logic-based duplicates.
        
        Level 3: Company name fuzzy matching, location comparison,
        phone number similarity, and technology stack overlap analysis.
        
        Args:
            company: Company data to check.
            
        Returns:
            List of similar companies found through business logic.
        """
        similar_companies = []
        
        try:
            # For this implementation, we'll check against a hypothetical database
            # In production, this would query the actual company database
            candidate_companies = self._get_candidate_companies_for_business_logic()
            
            for candidate in candidate_companies:
                similarity_metrics = self._calculate_business_logic_similarity(company, candidate)
                
                # Calculate overall similarity using weights
                overall_similarity = (
                    similarity_metrics.name_similarity * self.name_weight +
                    similarity_metrics.description_similarity * self.description_weight +
                    similarity_metrics.location_similarity * self.location_weight +
                    similarity_metrics.phone_similarity * self.phone_weight +
                    similarity_metrics.technology_overlap * self.technology_weight
                )
                
                if overall_similarity >= self.business_logic_threshold:
                    similar_company = SimilarCompany(
                        company_id=candidate.get('id', str(uuid.uuid4())),
                        company_name=candidate.get('company_name', ''),
                        company_url=candidate.get('url'),
                        domain=self.normalize_domain(candidate.get('url', '')) or '',
                        similarity_metrics=similarity_metrics,
                        overall_similarity=overall_similarity,
                        detection_level=DuplicateLevel.LEVEL_3_BUSINESS_LOGIC,
                        confidence_score=min(overall_similarity * 1.1, 1.0),
                        matched_fields=self._get_matched_fields(similarity_metrics),
                        match_reason=self._generate_match_reason(similarity_metrics)
                    )
                    similar_companies.append(similar_company)
            
            if similar_companies:
                self._stats['level_3_matches'] += len(similar_companies)
                logger.debug(f"Level 3 found {len(similar_companies)} similar companies")
            
            return similar_companies
            
        except Exception as e:
            logger.error(f"Business logic duplicate check failed: {e}")
            return []
    
    def calculate_similarity_score(self, company1: Dict[str, Any], company2: Dict[str, Any]) -> float:
        """Calculate comprehensive similarity score between two companies.
        
        Args:
            company1: First company data.
            company2: Second company data.
            
        Returns:
            Similarity score between 0.0 and 1.0.
        """
        try:
            # Calculate individual similarity metrics
            name_sim = self._calculate_name_similarity(
                company1.get('company_name', ''),
                company2.get('company_name', '')
            )
            
            description_sim = self._calculate_description_similarity(
                company1.get('description', ''),
                company2.get('description', '')
            )
            
            location_sim = self._calculate_location_similarity(
                company1.get('country', ''),
                company2.get('country', ''),
                company1.get('city', ''),
                company2.get('city', '')
            )
            
            phone_sim = self._calculate_phone_similarity(
                company1.get('contact_phones', []),
                company2.get('contact_phones', [])
            )
            
            tech_sim = self._calculate_technology_overlap(
                company1.get('technology_signals', []),
                company2.get('technology_signals', [])
            )
            
            # Calculate weighted overall similarity
            overall_similarity = (
                name_sim * self.name_weight +
                description_sim * self.description_weight +
                location_sim * self.location_weight +
                phone_sim * self.phone_weight +
                tech_sim * self.technology_weight
            )
            
            return min(max(overall_similarity, 0.0), 1.0)
            
        except Exception as e:
            logger.error(f"Similarity score calculation failed: {e}")
            return 0.0
    
    async def check_duplicates(
        self,
        company_data: Dict[str, Any],
        check_levels: Optional[List[DuplicateLevel]] = None,
        similarity_threshold: Optional[float] = None
    ) -> DuplicateDecision:
        """Perform comprehensive duplicate check across all levels.
        
        Args:
            company_data: Company data to check for duplicates.
            check_levels: Detection levels to check. If None, checks all levels in order.
            similarity_threshold: Override similarity threshold.
            
        Returns:
            Duplicate decision with detailed results.
        """
        start_time = time.time()
        decision_id = str(uuid.uuid4())
        
        # Default check levels in optimal order
        if check_levels is None:
            check_levels = [
                DuplicateLevel.LEVEL_1_DOMAIN,
                DuplicateLevel.LEVEL_3_BUSINESS_LOGIC,
                DuplicateLevel.LEVEL_2_EMBEDDING
            ]
        
        threshold = similarity_threshold or self.similarity_threshold
        
        try:
            # Extract company identifiers
            company_url = company_data.get('url') or company_data.get('company_url', '')
            company_domain = self.normalize_domain(company_url) if company_url else ''
            company_id = company_data.get('id', str(uuid.uuid4()))
            
            all_similar_companies = []
            triggered_level = None
            is_duplicate = False
            checked_companies_count = 0
            
            # Check each level in order
            for level in check_levels:
                level_start = time.time()
                
                if level == DuplicateLevel.LEVEL_1_DOMAIN and company_domain:
                    # Level 1: Domain check
                    if await self.check_domain_duplicates(company_domain):
                        is_duplicate = True
                        triggered_level = level
                        # Create a placeholder similar company for domain match
                        domain_match = SimilarCompany(
                            company_id=f"domain_match_{company_domain}",
                            company_name=f"Existing company with domain {company_domain}",
                            domain=company_domain,
                            similarity_metrics=SimilarityMetrics(domain_similarity=1.0),
                            overall_similarity=1.0,
                            detection_level=level,
                            confidence_score=1.0,
                            matched_fields=['domain'],
                            match_reason="Exact domain match found"
                        )
                        all_similar_companies.append(domain_match)
                        break
                
                elif level == DuplicateLevel.LEVEL_2_EMBEDDING:
                    # Level 2: Embedding similarity
                    embedding_matches = await self.check_embedding_similarity(
                        company_data, threshold
                    )
                    all_similar_companies.extend(embedding_matches)
                    checked_companies_count += len(embedding_matches)
                    
                    if embedding_matches and max(m.overall_similarity for m in embedding_matches) >= threshold:
                        is_duplicate = True
                        triggered_level = level
                        break
                
                elif level == DuplicateLevel.LEVEL_3_BUSINESS_LOGIC:
                    # Level 3: Business logic
                    if isinstance(company_data, dict):
                        # Convert dict to CompanyData if needed
                        company_obj = self._dict_to_company_data(company_data)
                    else:
                        company_obj = company_data
                    
                    business_matches = self.check_business_logic_duplicates(company_obj)
                    all_similar_companies.extend(business_matches)
                    checked_companies_count += len(business_matches)
                    
                    if business_matches and max(m.overall_similarity for m in business_matches) >= threshold:
                        is_duplicate = True
                        triggered_level = level
                        break
                
                level_duration = (time.time() - level_start) * 1000
                logger.debug(f"Level {level.value} completed in {level_duration:.1f}ms")
            
            # Determine decision type
            if is_duplicate:
                decision_type = DuplicateDecisionType.DUPLICATE
            elif all_similar_companies:
                decision_type = DuplicateDecisionType.SIMILAR
            else:
                decision_type = DuplicateDecisionType.UNIQUE
            
            # Find best match
            best_match = None
            max_similarity = 0.0
            if all_similar_companies:
                best_match = max(all_similar_companies, key=lambda x: x.overall_similarity)
                max_similarity = best_match.overall_similarity
            
            # Calculate processing duration
            processing_duration = (time.time() - start_time) * 1000
            
            # Create decision
            decision = DuplicateDecision(
                decision_id=decision_id,
                incoming_company_id=company_id,
                incoming_domain=company_domain or 'unknown',
                decision_type=decision_type,
                is_duplicate=is_duplicate,
                similar_companies=all_similar_companies,
                best_match=best_match,
                levels_checked=check_levels,
                triggered_level=triggered_level,
                similarity_threshold_used=threshold,
                max_similarity_found=max_similarity,
                processing_duration_ms=processing_duration,
                checked_companies_count=checked_companies_count,
                decision_reasoning=self._generate_decision_reasoning(
                    decision_type, triggered_level, max_similarity, threshold
                ),
                configuration_snapshot=self._get_configuration_snapshot()
            )
            
            # Update statistics
            self._update_statistics(decision, processing_duration)
            
            # Add domain to known domains if unique
            if not is_duplicate and company_domain:
                self._known_domains.add(company_domain)
            
            # Log audit trail if enabled
            if self.config.get_bool('duplicate_detection', 'audit_enabled', True):
                self._log_audit_trail(decision)
            
            return decision
            
        except Exception as e:
            logger.error(f"Duplicate check failed for company {company_id}: {e}")
            
            # Return error decision
            error_decision = DuplicateDecision(
                decision_id=decision_id,
                incoming_company_id=company_data.get('id', 'unknown'),
                incoming_domain=company_domain or 'unknown',
                decision_type=DuplicateDecisionType.UNIQUE,
                is_duplicate=False,
                levels_checked=check_levels,
                similarity_threshold_used=threshold,
                processing_duration_ms=(time.time() - start_time) * 1000,
                decision_reasoning=f"Error during duplicate check: {str(e)}"
            )
            
            return error_decision
    
    async def check_duplicates_batch(
        self,
        companies_data: List[Dict[str, Any]],
        **kwargs
    ) -> BatchDuplicateCheckResponse:
        """Perform batch duplicate checking with concurrent processing.
        
        Args:
            companies_data: List of company data to check.
            **kwargs: Additional parameters for duplicate checking.
            
        Returns:
            Batch duplicate check response with all results.
        """
        batch_id = kwargs.get('batch_id', str(uuid.uuid4()))
        max_concurrent = kwargs.get('max_concurrent_checks', 
                                  self.config.get_int('duplicate_detection', 'max_concurrent_checks', 5))
        
        start_time = time.time()
        
        try:
            # Create semaphore for concurrency control
            semaphore = asyncio.Semaphore(max_concurrent)
            
            async def check_single_company(company_data: Dict[str, Any]) -> Tuple[Optional[DuplicateDecision], Optional[str]]:
                async with semaphore:
                    try:
                        decision = await self.check_duplicates(company_data, **kwargs)
                        return decision, None
                    except Exception as e:
                        error_msg = f"Failed to check company {company_data.get('id', 'unknown')}: {str(e)}"
                        logger.error(error_msg)
                        return None, error_msg
            
            # Execute batch checks
            tasks = [check_single_company(company_data) for company_data in companies_data]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            decisions = []
            failed_checks = []
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    failed_checks.append({
                        'company_id': companies_data[i].get('id', f'company_{i}'),
                        'error': str(result)
                    })
                else:
                    decision, error_msg = result
                    if decision:
                        decisions.append(decision)
                    else:
                        failed_checks.append({
                            'company_id': companies_data[i].get('id', f'company_{i}'),
                            'error': error_msg or 'Unknown error'
                        })
            
            # Calculate statistics
            total_duration = time.time() - start_time
            duplicates_found = sum(1 for d in decisions if d.is_duplicate)
            unique_companies = len(decisions) - duplicates_found
            average_duration = (total_duration / len(companies_data) * 1000) if companies_data else 0
            
            response = BatchDuplicateCheckResponse(
                batch_id=batch_id,
                success=True,
                decisions=decisions,
                failed_checks=failed_checks,
                total_companies=len(companies_data),
                duplicates_found=duplicates_found,
                unique_companies=unique_companies,
                failed_companies=len(failed_checks),
                total_duration_seconds=total_duration,
                average_check_duration_ms=average_duration
            )
            
            logger.info(f"Batch duplicate check completed: {batch_id}, "
                       f"{len(decisions)} successful, {len(failed_checks)} failed, "
                       f"{duplicates_found} duplicates found in {total_duration:.2f}s")
            
            return response
            
        except Exception as e:
            logger.error(f"Batch duplicate check failed: {e}")
            return BatchDuplicateCheckResponse(
                batch_id=batch_id,
                success=False,
                total_companies=len(companies_data),
                total_duration_seconds=time.time() - start_time
            )
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get duplicate checker statistics.
        
        Returns:
            Dictionary with performance and accuracy statistics.
        """
        return {
            **self._stats,
            'configuration': {
                'similarity_threshold': self.similarity_threshold,
                'embedding_threshold': self.embedding_threshold,
                'business_logic_threshold': self.business_logic_threshold,
                'performance_target_ms': self.performance_target_ms
            },
            'cache_stats': {
                'domain_cache_size': len(self._domain_cache),
                'known_domains_count': len(self._known_domains)
            }
        }
    
    # Helper methods
    
    async def _generate_company_embedding(self, company_data: Dict[str, Any]) -> Optional[np.ndarray]:
        """Generate embedding for company data.
        
        This is a placeholder implementation. In production, this would
        use a proper embedding model like sentence-transformers.
        """
        try:
            # Combine textual fields for embedding
            text_parts = []
            
            if company_data.get('company_name'):
                text_parts.append(company_data['company_name'])
            
            if company_data.get('description'):
                text_parts.append(company_data['description'])
            
            if company_data.get('industry_hints'):
                text_parts.extend(company_data['industry_hints'][:5])  # Limit to 5
            
            if company_data.get('technology_signals'):
                text_parts.extend(company_data['technology_signals'][:5])  # Limit to 5
            
            combined_text = ' '.join(text_parts)
            
            if not combined_text.strip():
                return None
            
            # Generate a simple hash-based embedding (placeholder)
            # In production, use proper embedding model
            embedding_dim = self.config.get_int('duplicate_detection', 'embedding_dimension', 384)
            hash_value = hashlib.md5(combined_text.encode()).hexdigest()
            
            # Convert hash to numeric values
            numeric_values = [ord(c) for c in hash_value[:embedding_dim]]
            
            # Pad or truncate to desired dimension
            if len(numeric_values) < embedding_dim:
                numeric_values.extend([0] * (embedding_dim - len(numeric_values)))
            else:
                numeric_values = numeric_values[:embedding_dim]
            
            # Normalize to create a proper embedding
            embedding = np.array(numeric_values, dtype=np.float32)
            embedding = embedding / np.linalg.norm(embedding)
            
            return embedding
            
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return None
    
    async def _create_similar_company_from_embedding(
        self,
        similarity_result: SimilarityResult,
        query_company: Dict[str, Any],
        detection_level: DuplicateLevel
    ) -> Optional[SimilarCompany]:
        """Create SimilarCompany from embedding similarity result."""
        try:
            similarity_metrics = SimilarityMetrics(
                embedding_similarity=similarity_result.similarity_score
            )
            
            return SimilarCompany(
                company_id=similarity_result.company_id,
                company_name=similarity_result.metadata.get('company_name', 'Unknown'),
                domain=similarity_result.domain,
                similarity_metrics=similarity_metrics,
                overall_similarity=similarity_result.similarity_score,
                detection_level=detection_level,
                confidence_score=similarity_result.similarity_score,
                matched_fields=['embedding'],
                match_reason=f"Embedding similarity: {similarity_result.similarity_score:.3f}"
            )
            
        except Exception as e:
            logger.error(f"Failed to create SimilarCompany from embedding result: {e}")
            return None
    
    def _get_candidate_companies_for_business_logic(self) -> List[Dict[str, Any]]:
        """Get candidate companies for business logic checking.
        
        This is a placeholder that returns empty list. In production,
        this would query the actual company database.
        """
        # Placeholder implementation
        return []
    
    def _calculate_business_logic_similarity(
        self,
        company1: CompanyData,
        company2: Dict[str, Any]
    ) -> SimilarityMetrics:
        """Calculate business logic similarity metrics."""
        try:
            name_sim = self._calculate_name_similarity(
                company1.company_name or '',
                company2.get('company_name', '')
            )
            
            description_sim = self._calculate_description_similarity(
                company1.description or '',
                company2.get('description', '')
            )
            
            # Extract location info from company1
            location1 = getattr(company1, 'country', '') or ''
            city1 = getattr(company1, 'city', '') or ''
            
            location_sim = self._calculate_location_similarity(
                location1,
                company2.get('country', ''),
                city1,
                company2.get('city', '')
            )
            
            phone_sim = self._calculate_phone_similarity(
                company1.contact_phones or [],
                company2.get('contact_phones', [])
            )
            
            tech_sim = self._calculate_technology_overlap(
                company1.technology_signals or [],
                company2.get('technology_signals', [])
            )
            
            return SimilarityMetrics(
                name_similarity=name_sim,
                description_similarity=description_sim,
                location_similarity=location_sim,
                phone_similarity=phone_sim,
                technology_overlap=tech_sim
            )
            
        except Exception as e:
            logger.error(f"Failed to calculate business logic similarity: {e}")
            return SimilarityMetrics()
    
    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """Calculate fuzzy name similarity."""
        if not name1 or not name2:
            return 0.0
        
        # Normalize names
        norm_name1 = self._normalize_company_name(name1)
        norm_name2 = self._normalize_company_name(name2)
        
        if not norm_name1 or not norm_name2:
            return 0.0
        
        # Use rapidfuzz for fuzzy matching
        similarity = fuzz.ratio(norm_name1, norm_name2) / 100.0
        return min(max(similarity, 0.0), 1.0)
    
    def _normalize_company_name(self, name: str) -> str:
        """Normalize company name for comparison."""
        if not name:
            return ''
        
        # Convert to lowercase and remove extra whitespace
        normalized = re.sub(r'\s+', ' ', name.lower().strip())
        
        # Remove common company suffixes
        suffixes = [
            'inc', 'incorporated', 'corp', 'corporation', 'ltd', 'limited',
            'llc', 'llp', 'lp', 'co', 'company', 'group', 'holdings',
            'technologies', 'technology', 'tech', 'systems', 'solutions'
        ]
        
        for suffix in suffixes:
            patterns = [f' {suffix}$', f' {suffix}\\.$']
            for pattern in patterns:
                normalized = re.sub(pattern, '', normalized)
        
        return normalized.strip()
    
    def _calculate_description_similarity(self, desc1: str, desc2: str) -> float:
        """Calculate description similarity using simple word overlap."""
        if not desc1 or not desc2:
            return 0.0
        
        # Simple word-based similarity
        words1 = set(re.findall(r'\b\w+\b', desc1.lower()))
        words2 = set(re.findall(r'\b\w+\b', desc2.lower()))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        return intersection / union if union > 0 else 0.0
    
    def _calculate_location_similarity(
        self,
        country1: str, country2: str,
        city1: str, city2: str
    ) -> float:
        """Calculate location similarity."""
        if not any([country1, country2, city1, city2]):
            return 0.0
        
        country_match = 0.0
        city_match = 0.0
        
        # Country comparison
        if country1 and country2:
            country_match = 1.0 if country1.upper() == country2.upper() else 0.0
        
        # City comparison
        if city1 and city2:
            city_match = fuzz.ratio(city1.lower(), city2.lower()) / 100.0
        
        # Weighted combination (country is more important)
        return country_match * 0.7 + city_match * 0.3
    
    def _calculate_phone_similarity(self, phones1: List[str], phones2: List[str]) -> float:
        """Calculate phone number similarity."""
        if not phones1 or not phones2:
            return 0.0
        
        # Normalize phone numbers
        normalized_phones1 = [self._normalize_phone(p) for p in phones1]
        normalized_phones2 = [self._normalize_phone(p) for p in phones2]
        
        # Remove None values
        normalized_phones1 = [p for p in normalized_phones1 if p]
        normalized_phones2 = [p for p in normalized_phones2 if p]
        
        if not normalized_phones1 or not normalized_phones2:
            return 0.0
        
        # Check for exact matches
        for phone1 in normalized_phones1:
            for phone2 in normalized_phones2:
                if phone1 == phone2:
                    return 1.0
        
        return 0.0
    
    def _normalize_phone(self, phone: str) -> Optional[str]:
        """Normalize phone number for comparison."""
        if not phone:
            return None
        
        try:
            # Try to parse as international number
            parsed = parse_phone(phone, None)
            if is_valid_number(parsed):
                return format_number(parsed, PhoneNumberFormat.E164)
        except NumberParseException:
            pass
        
        # Fallback: extract digits only
        digits = re.sub(r'\D', '', phone)
        return digits if len(digits) >= 7 else None
    
    def _calculate_technology_overlap(self, tech1: List[str], tech2: List[str]) -> float:
        """Calculate technology stack overlap using Jaccard similarity."""
        if not tech1 or not tech2:
            return 0.0
        
        # Normalize technology terms
        norm_tech1 = set(t.lower().strip() for t in tech1 if t.strip())
        norm_tech2 = set(t.lower().strip() for t in tech2 if t.strip())
        
        if not norm_tech1 or not norm_tech2:
            return 0.0
        
        intersection = len(norm_tech1 & norm_tech2)
        union = len(norm_tech1 | norm_tech2)
        
        return intersection / union if union > 0 else 0.0
    
    def _get_matched_fields(self, metrics: SimilarityMetrics) -> List[str]:
        """Get list of fields that contributed to the match."""
        matched_fields = []
        
        if metrics.name_similarity > self.fuzzy_name_threshold:
            matched_fields.append('name')
        
        if metrics.description_similarity > 0.5:
            matched_fields.append('description')
        
        if metrics.location_similarity > self.location_threshold:
            matched_fields.append('location')
        
        if metrics.phone_similarity > self.phone_threshold:
            matched_fields.append('phone')
        
        if metrics.technology_overlap > self.technology_threshold:
            matched_fields.append('technology')
        
        if metrics.embedding_similarity > self.embedding_threshold:
            matched_fields.append('embedding')
        
        return matched_fields
    
    def _generate_match_reason(self, metrics: SimilarityMetrics) -> str:
        """Generate human-readable match reason."""
        reasons = []
        
        if metrics.name_similarity > self.fuzzy_name_threshold:
            reasons.append(f"name similarity: {metrics.name_similarity:.3f}")
        
        if metrics.description_similarity > 0.5:
            reasons.append(f"description similarity: {metrics.description_similarity:.3f}")
        
        if metrics.location_similarity > self.location_threshold:
            reasons.append(f"location match: {metrics.location_similarity:.3f}")
        
        if metrics.phone_similarity > self.phone_threshold:
            reasons.append(f"phone match: {metrics.phone_similarity:.3f}")
        
        if metrics.technology_overlap > self.technology_threshold:
            reasons.append(f"technology overlap: {metrics.technology_overlap:.3f}")
        
        if metrics.embedding_similarity > self.embedding_threshold:
            reasons.append(f"embedding similarity: {metrics.embedding_similarity:.3f}")
        
        return "; ".join(reasons) if reasons else "No specific match criteria met"
    
    def _dict_to_company_data(self, data: Dict[str, Any]) -> CompanyData:
        """Convert dictionary to CompanyData object."""
        try:
            # Create CompanyData with required fields
            return CompanyData(
                url=data.get('url', 'https://example.com'),
                company_name=data.get('company_name'),
                description=data.get('description'),
                contact_emails=data.get('contact_emails', []),
                contact_phones=data.get('contact_phones', []),
                technology_signals=data.get('technology_signals', []),
                industry_hints=data.get('industry_hints', [])
            )
        except Exception as e:
            logger.error(f"Failed to convert dict to CompanyData: {e}")
            # Return minimal CompanyData
            return CompanyData(url='https://example.com')
    
    def _generate_decision_reasoning(
        self,
        decision_type: DuplicateDecisionType,
        triggered_level: Optional[DuplicateLevel],
        max_similarity: float,
        threshold: float
    ) -> str:
        """Generate decision reasoning text."""
        if decision_type == DuplicateDecisionType.DUPLICATE:
            level_name = triggered_level.value if triggered_level else "unknown"
            return (f"Duplicate detected at {level_name} with similarity {max_similarity:.3f} "
                   f"above threshold {threshold:.3f}")
        elif decision_type == DuplicateDecisionType.SIMILAR:
            return (f"Similar companies found with max similarity {max_similarity:.3f} "
                   f"below duplicate threshold {threshold:.3f}")
        else:
            return f"No similar companies found above threshold {threshold:.3f}"
    
    def _get_configuration_snapshot(self) -> Dict[str, Any]:
        """Get current configuration snapshot for audit trail."""
        return {
            'similarity_threshold': self.similarity_threshold,
            'embedding_threshold': self.embedding_threshold,
            'business_logic_threshold': self.business_logic_threshold,
            'fuzzy_name_threshold': self.fuzzy_name_threshold,
            'location_threshold': self.location_threshold,
            'phone_threshold': self.phone_threshold,
            'technology_threshold': self.technology_threshold,
            'weights': {
                'name': self.name_weight,
                'description': self.description_weight,
                'location': self.location_weight,
                'phone': self.phone_weight,
                'technology': self.technology_weight
            }
        }
    
    def _update_statistics(self, decision: DuplicateDecision, duration_ms: float) -> None:
        """Update internal statistics."""
        self._stats['total_checks'] += 1
        
        if decision.is_duplicate:
            self._stats['duplicates_found'] += 1
        
        # Update average duration
        total_duration = self._stats['average_duration_ms'] * (self._stats['total_checks'] - 1) + duration_ms
        self._stats['average_duration_ms'] = total_duration / self._stats['total_checks']
    
    def _log_audit_trail(self, decision: DuplicateDecision) -> None:
        """Log audit trail for duplicate decision."""
        if self.config.get_bool('duplicate_detection', 'log_similarity_scores', False):
            # Log detailed similarity scores
            logger.info(f"Duplicate decision audit: {decision.decision_id}", extra={
                'decision_type': decision.decision_type.value,
                'is_duplicate': decision.is_duplicate,
                'max_similarity': decision.max_similarity_found,
                'threshold': decision.similarity_threshold_used,
                'triggered_level': decision.triggered_level.value if decision.triggered_level else None,
                'processing_duration_ms': decision.processing_duration_ms,
                'similar_companies_count': len(decision.similar_companies)
            })
        else:
            # Log basic audit information
            logger.info(f"Duplicate check completed: {decision.decision_type.value} "
                       f"for {decision.incoming_domain} in {decision.processing_duration_ms:.1f}ms")