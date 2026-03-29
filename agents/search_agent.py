"""Search agent for web search and company discovery.

This module implements the main SearchAgent class that orchestrates
web search operations using DuckDuckGo with rate limiting, caching,
and intelligent query generation.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple, Set
from urllib.parse import urlparse
import aiohttp

try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None
    logging.warning("duckduckgo-search not installed. Search functionality will be limited.")

from config.settings import Settings
from utils.logger import get_logger
from utils.exceptions import SearchError, ValidationError

from .models import (
    SearchResult, SearchQuery, SearchResponse, SearchStatus,
    TargetType, SearchConfig, SearchBatch
)
from .url_utils import URLUtilities
from .rate_limiter import RateLimitConfig, MultiServiceRateLimiter
from .query_generator import QueryGenerator
from .search_cache import AsyncSearchCache


logger = get_logger(__name__)


class SearchAgent:
    """Main search agent for web search and company discovery.
    
    Orchestrates search operations using DuckDuckGo with intelligent
    query generation, rate limiting, result caching, and comprehensive
    error handling.
    """
    
    def __init__(self, settings: Settings):
        """Initialize search agent.
        
        Args:
            settings: Application settings instance.
            
        Raises:
            SearchError: If DuckDuckGo search is not available.
        """
        self.settings = settings
        
        # Validate DuckDuckGo availability
        if DDGS is None:
            raise SearchError(
                "DuckDuckGo search not available. Install duckduckgo-search package."
            )
        
        # Initialize configuration
        self.config = self._load_search_config()
        
        # Initialize components
        self.url_utils = URLUtilities()
        self.query_generator = QueryGenerator()
        
        # Initialize rate limiter
        self.rate_limiter = MultiServiceRateLimiter()
        self._setup_rate_limiters()
        
        # Initialize cache
        self.cache: Optional[AsyncSearchCache] = None
        if self.config.cache_enabled:
            self.cache = AsyncSearchCache(
                max_size=1000,
                default_ttl=self.config.cache_ttl,
                persistent=True
            )
        
        # Search statistics
        self.stats = {
            'total_searches': 0,
            'successful_searches': 0,
            'failed_searches': 0,
            'cached_results': 0,
            'total_results': 0,
            'duplicate_results': 0,
            'invalid_urls': 0
        }
        
        logger.info(
            f"SearchAgent initialized with {self.config.concurrent_searches} "
            f"concurrent searches, cache {'enabled' if self.config.cache_enabled else 'disabled'}"
        )
    
    def _load_search_config(self) -> SearchConfig:
        """Load search configuration from settings.
        
        Returns:
            Search configuration instance.
        """
        return SearchConfig(
            max_results_per_query=self.settings.get_int('search', 'results_limit', 50),
            concurrent_searches=self.settings.get_int('search', 'concurrent_searches', 5),
            request_timeout=self.settings.get_int('search', 'query_timeout', 15),
            retry_attempts=self.settings.get_int('general', 'max_retries', 3),
            retry_delay=self.settings.get_float('search', 'retry_delay', 1.0),
            rate_limit_requests=self.settings.get_int('search', 'rate_limit_requests', 10),
            rate_limit_window=self.settings.get_int('search', 'rate_limit_window', 60),
            cache_enabled=self.settings.get_bool('search', 'cache_enabled', True),
            cache_ttl=self.settings.get_int('search', 'cache_ttl', 3600),
            user_agent=self.settings.get(
                'search', 'user_agent',
                'TatvixAI-ClientFinder/1.0 (+https://tatvix.com/bot)'
            )
        )
    
    def _setup_rate_limiters(self) -> None:
        """Setup rate limiters for different services."""
        # DuckDuckGo rate limiter
        ddg_config = RateLimitConfig(
            requests_per_window=self.config.rate_limit_requests,
            window_seconds=self.config.rate_limit_window,
            max_retries=self.config.retry_attempts,
            base_delay=self.config.retry_delay,
            max_delay=30.0,
            backoff_multiplier=2.0,
            jitter=True
        )
        self.rate_limiter.add_service('duckduckgo', ddg_config)
    
    async def start(self) -> None:
        """Start the search agent and its components."""
        if self.cache:
            await self.cache.start()
        
        logger.info("SearchAgent started")
    
    async def stop(self) -> None:
        """Stop the search agent and cleanup resources."""
        if self.cache:
            await self.cache.stop()
        
        logger.info("SearchAgent stopped")
    
    async def search_companies(
        self,
        queries: List[SearchQuery],
        deduplicate: bool = True
    ) -> List[SearchResponse]:
        """Execute multiple search queries concurrently.
        
        Args:
            queries: List of search queries to execute.
            deduplicate: Whether to deduplicate results across queries.
            
        Returns:
            List of search responses.
        """
        if not queries:
            logger.warning("No queries provided for search")
            return []
        
        logger.info(f"Starting search for {len(queries)} queries")
        start_time = time.time()
        
        # Create semaphore for concurrent search limit
        semaphore = asyncio.Semaphore(self.config.concurrent_searches)
        
        # Execute searches concurrently
        tasks = [
            self._execute_single_search(query, semaphore)
            for query in queries
        ]
        
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results and handle exceptions
        valid_responses = []
        for i, response in enumerate(responses):
            if isinstance(response, Exception):
                logger.error(f"Search failed for query {i}: {response}")
                # Create failed response
                failed_response = SearchResponse(
                    query=queries[i],
                    status=SearchStatus.FAILED,
                    error_message=str(response)
                )
                valid_responses.append(failed_response)
            else:
                valid_responses.append(response)
        
        # Deduplicate results across all queries if requested
        if deduplicate:
            valid_responses = self._deduplicate_responses(valid_responses)
        
        # Update statistics
        execution_time = time.time() - start_time
        self._update_search_stats(valid_responses, execution_time)
        
        logger.info(
            f"Completed search for {len(queries)} queries in {execution_time:.2f}s. "
            f"Total results: {sum(len(r.results) for r in valid_responses)}"
        )
        
        return valid_responses
    
    async def _execute_single_search(
        self,
        query: SearchQuery,
        semaphore: asyncio.Semaphore
    ) -> SearchResponse:
        """Execute a single search query.
        
        Args:
            query: Search query to execute.
            semaphore: Concurrency control semaphore.
            
        Returns:
            Search response.
        """
        async with semaphore:
            response = SearchResponse(
                query=query,
                started_at=datetime.utcnow()
            )
            
            try:
                response.status = SearchStatus.RUNNING
                
                # Check cache first
                if self.cache:
                    cached_results = await self.cache.get(query)
                    if cached_results:
                        response.results = cached_results
                        response.total_results = len(cached_results)
                        response.status = SearchStatus.COMPLETED
                        response.completed_at = datetime.utcnow()
                        response.execution_time = (
                            response.completed_at - response.started_at
                        ).total_seconds()
                        
                        self.stats['cached_results'] += 1
                        logger.debug(f"Cache hit for query: {query.query}")
                        return response
                
                # Execute search with rate limiting
                raw_results = await self.rate_limiter.execute_for_service(
                    'duckduckgo',
                    self._perform_duckduckgo_search,
                    query
                )
                
                # Process and validate results
                processed_results = await self._process_search_results(
                    raw_results, query
                )
                
                response.results = processed_results
                response.total_results = len(processed_results)
                response.status = SearchStatus.COMPLETED
                
                # Cache results if enabled
                if self.cache and processed_results:
                    await self.cache.set(query, processed_results)
                
                logger.debug(
                    f"Search completed for query: {query.query}, "
                    f"results: {len(processed_results)}"
                )
                
            except asyncio.TimeoutError:
                response.status = SearchStatus.TIMEOUT
                response.error_message = f"Search timeout after {query.timeout}s"
                logger.warning(f"Search timeout for query: {query.query}")
                
            except Exception as e:
                response.status = SearchStatus.FAILED
                response.error_message = str(e)
                logger.error(f"Search failed for query '{query.query}': {e}")
            
            finally:
                response.completed_at = datetime.utcnow()
                if response.started_at:
                    response.execution_time = (
                        response.completed_at - response.started_at
                    ).total_seconds()
            
            return response
    
    async def _perform_duckduckgo_search(self, query: SearchQuery) -> List[Dict[str, Any]]:
        """Perform DuckDuckGo search.
        
        Args:
            query: Search query to execute.
            
        Returns:
            Raw search results from DuckDuckGo.
            
        Raises:
            SearchError: If search fails.
        """
        try:
            # Create DDGS instance
            ddgs = DDGS(timeout=query.timeout)
            
            # Prepare search parameters
            search_params = {
                'max_results': min(query.max_results, self.config.max_results_per_query)
            }
            
            # Add region if specified
            if query.country:
                search_params['region'] = f'wt-{query.country.lower()}'
            
            logger.debug(f"Executing DuckDuckGo search: {query.query}")
            
            # Execute search
            results = list(ddgs.text(query.query, **search_params))
            
            logger.debug(f"DuckDuckGo returned {len(results)} results")
            return results
            
        except Exception as e:
            raise SearchError(f"DuckDuckGo search failed: {str(e)}")
    
    async def _process_search_results(
        self,
        raw_results: List[Dict[str, Any]],
        query: SearchQuery
    ) -> List[SearchResult]:
        """Process and validate raw search results.
        
        Args:
            raw_results: Raw results from search engine.
            query: Original search query.
            
        Returns:
            List of processed and validated search results.
        """
        processed_results = []
        seen_domains = set()
        
        for raw_result in raw_results:
            try:
                # Extract and validate URL
                url = raw_result.get('href', '')
                if not url:
                    continue
                
                # Clean and normalize URL
                normalized_url = self.url_utils.clean_search_url(url)
                if not normalized_url:
                    self.stats['invalid_urls'] += 1
                    continue
                
                # Validate URL
                is_valid, error_msg = self.url_utils.validate_url(normalized_url)
                if not is_valid:
                    logger.debug(f"Invalid URL filtered: {url} - {error_msg}")
                    self.stats['invalid_urls'] += 1
                    continue
                
                # Extract domain for deduplication
                domain = self.url_utils.extract_domain(normalized_url)
                if not domain:
                    self.stats['invalid_urls'] += 1
                    continue
                
                # Check for duplicate domains
                if domain in seen_domains:
                    self.stats['duplicate_results'] += 1
                    logger.debug(f"Duplicate domain filtered: {domain}")
                    continue
                
                seen_domains.add(domain)
                
                # Create SearchResult
                result = SearchResult(
                    title=raw_result.get('title', '').strip(),
                    url=normalized_url,
                    snippet=raw_result.get('body', ''),
                    domain=domain,
                    search_query=query.query,
                    source='duckduckgo'
                )
                
                processed_results.append(result)
                
            except Exception as e:
                logger.warning(f"Failed to process search result: {e}")
                continue
        
        logger.debug(
            f"Processed {len(processed_results)} valid results from "
            f"{len(raw_results)} raw results"
        )
        
        return processed_results
    
    def _deduplicate_responses(
        self,
        responses: List[SearchResponse]
    ) -> List[SearchResponse]:
        """Deduplicate results across multiple search responses.
        
        Args:
            responses: List of search responses.
            
        Returns:
            Responses with deduplicated results.
        """
        seen_domains = set()
        
        for response in responses:
            deduplicated_results = []
            
            for result in response.results:
                if result.domain not in seen_domains:
                    seen_domains.add(result.domain)
                    deduplicated_results.append(result)
                else:
                    self.stats['duplicate_results'] += 1
            
            response.results = deduplicated_results
            response.total_results = len(deduplicated_results)
        
        return responses
    
    def _update_search_stats(
        self,
        responses: List[SearchResponse],
        execution_time: float
    ) -> None:
        """Update search statistics.
        
        Args:
            responses: Search responses.
            execution_time: Total execution time.
        """
        self.stats['total_searches'] += len(responses)
        
        for response in responses:
            if response.status == SearchStatus.COMPLETED:
                self.stats['successful_searches'] += 1
                self.stats['total_results'] += len(response.results)
            else:
                self.stats['failed_searches'] += 1
        
        logger.info(
            f"Search stats - Total: {self.stats['total_searches']}, "
            f"Success: {self.stats['successful_searches']}, "
            f"Failed: {self.stats['failed_searches']}, "
            f"Results: {self.stats['total_results']}"
        )
    
    async def generate_search_queries(
        self,
        target_type: TargetType,
        country: Optional[str] = None,
        max_queries: int = 10
    ) -> List[SearchQuery]:
        """Generate search queries for target type and location.
        
        Args:
            target_type: Type of companies to target.
            country: ISO country code for geographic targeting.
            max_queries: Maximum number of queries to generate.
            
        Returns:
            List of generated search queries.
        """
        return self.query_generator.generate_queries(
            target_type=target_type,
            country=country,
            max_queries=max_queries,
            include_geographic=True,
            include_variations=True
        )
    
    async def search_batch(self, batch: SearchBatch) -> Dict[str, SearchResponse]:
        """Execute a batch of search queries.
        
        Args:
            batch: Search batch configuration.
            
        Returns:
            Dictionary mapping query strings to responses.
        """
        logger.info(f"Executing search batch: {batch.batch_id}")
        
        # Execute searches with timeout
        try:
            responses = await asyncio.wait_for(
                self.search_companies(batch.queries),
                timeout=batch.total_timeout
            )
            
            # Create response mapping
            response_map = {
                response.query.query: response
                for response in responses
            }
            
            logger.info(
                f"Batch {batch.batch_id} completed: "
                f"{len(responses)} queries processed"
            )
            
            return response_map
            
        except asyncio.TimeoutError:
            logger.error(f"Batch {batch.batch_id} timeout after {batch.total_timeout}s")
            raise SearchError(f"Batch search timeout: {batch.batch_id}")
    
    def get_search_stats(self) -> Dict[str, Any]:
        """Get comprehensive search statistics.
        
        Returns:
            Dictionary with search statistics and status.
        """
        stats = self.stats.copy()
        
        # Add rate limiter status
        stats['rate_limiter'] = self.rate_limiter.get_all_status()
        
        # Add cache statistics
        if self.cache:
            stats['cache'] = self.cache.get_stats()
        
        # Add configuration info
        stats['config'] = {
            'concurrent_searches': self.config.concurrent_searches,
            'max_results_per_query': self.config.max_results_per_query,
            'cache_enabled': self.config.cache_enabled,
            'rate_limit_requests': self.config.rate_limit_requests,
            'rate_limit_window': self.config.rate_limit_window
        }
        
        return stats
    
    async def validate_search_results(
        self,
        results: List[SearchResult]
    ) -> List[SearchResult]:
        """Validate and filter search results.
        
        Args:
            results: Search results to validate.
            
        Returns:
            Filtered list of valid results.
        """
        valid_results = []
        
        for result in results:
            try:
                # Validate URL accessibility (enabled by default for quality)
                if self.settings.get_bool('search', 'validate_urls', True):
                    is_accessible, error_msg = self.url_utils.check_url_accessibility(
                        str(result.url), timeout=5
                    )
                    if not is_accessible:
                        logger.debug(f"URL not accessible: {result.url} - {error_msg}")
                        continue
                
                valid_results.append(result)
                
            except Exception as e:
                logger.warning(f"Result validation failed: {e}")
                continue
        
        return valid_results
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()