"""Rate limiting utilities for API requests.

This module provides rate limiting functionality with exponential backoff
to prevent API blocks and ensure respectful service usage.
"""

import asyncio
import time
import logging
from typing import Dict, Optional, Callable, Any
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
import random

from utils.logger import get_logger


logger = get_logger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    
    requests_per_window: int = 10
    window_seconds: int = 60
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff_multiplier: float = 2.0
    jitter: bool = True


class RateLimiter:
    """Async rate limiter with exponential backoff.
    
    Implements token bucket algorithm with request tracking
    and automatic retry with exponential backoff.
    """
    
    def __init__(self, config: RateLimitConfig):
        """Initialize rate limiter.
        
        Args:
            config: Rate limiting configuration.
        """
        self.config = config
        self.request_times: deque = deque()
        self.lock = asyncio.Lock()
        self._last_reset = time.time()
        
        logger.info(
            f"RateLimiter initialized: {config.requests_per_window} requests "
            f"per {config.window_seconds}s window"
        )
    
    async def acquire(self) -> None:
        """Acquire permission to make a request.
        
        Blocks until request can be made within rate limits.
        """
        async with self.lock:
            now = time.time()
            
            # Remove expired request timestamps
            cutoff = now - self.config.window_seconds
            while self.request_times and self.request_times[0] < cutoff:
                self.request_times.popleft()
            
            # Check if we need to wait
            if len(self.request_times) >= self.config.requests_per_window:
                # Calculate wait time until oldest request expires
                oldest_request = self.request_times[0]
                wait_time = (oldest_request + self.config.window_seconds) - now
                
                if wait_time > 0:
                    logger.debug(f"Rate limit reached, waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
                    
                    # Clean up expired requests after waiting
                    cutoff = time.time() - self.config.window_seconds
                    while self.request_times and self.request_times[0] < cutoff:
                        self.request_times.popleft()
            
            # Record this request
            self.request_times.append(time.time())
            
            logger.debug(
                f"Request acquired, {len(self.request_times)} requests "
                f"in current window"
            )
    
    async def execute_with_backoff(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """Execute function with rate limiting and exponential backoff.
        
        Args:
            func: Function to execute (can be async or sync).
            *args: Function positional arguments.
            **kwargs: Function keyword arguments.
            
        Returns:
            Function result.
            
        Raises:
            Exception: If all retry attempts fail.
        """
        last_exception = None
        delay = self.config.base_delay
        
        for attempt in range(self.config.max_retries + 1):
            try:
                # Acquire rate limit permission
                await self.acquire()
                
                # Execute function
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                if attempt > 0:
                    logger.info(f"Request succeeded after {attempt} retries")
                
                return result
                
            except Exception as e:
                last_exception = e
                
                if attempt < self.config.max_retries:
                    # Calculate delay with jitter
                    actual_delay = delay
                    if self.config.jitter:
                        actual_delay *= (0.5 + random.random() * 0.5)
                    
                    logger.warning(
                        f"Request failed (attempt {attempt + 1}/{self.config.max_retries + 1}): "
                        f"{str(e)}. Retrying in {actual_delay:.2f}s"
                    )
                    
                    await asyncio.sleep(actual_delay)
                    delay = min(delay * self.config.backoff_multiplier, self.config.max_delay)
                else:
                    logger.error(
                        f"Request failed after {self.config.max_retries} retries: {str(e)}"
                    )
        
        # All retries exhausted
        raise last_exception
    
    def get_status(self) -> Dict[str, Any]:
        """Get current rate limiter status.
        
        Returns:
            Dictionary with status information.
        """
        now = time.time()
        cutoff = now - self.config.window_seconds
        
        # Count current requests in window
        current_requests = sum(1 for t in self.request_times if t >= cutoff)
        
        # Calculate time until next available slot
        time_to_next_slot = 0.0
        if current_requests >= self.config.requests_per_window and self.request_times:
            oldest_request = min(self.request_times)
            time_to_next_slot = max(0, (oldest_request + self.config.window_seconds) - now)
        
        return {
            'requests_in_window': current_requests,
            'max_requests': self.config.requests_per_window,
            'window_seconds': self.config.window_seconds,
            'time_to_next_slot': time_to_next_slot,
            'is_limited': current_requests >= self.config.requests_per_window,
            'total_requests': len(self.request_times)
        }
    
    def reset(self) -> None:
        """Reset rate limiter state."""
        self.request_times.clear()
        self._last_reset = time.time()
        logger.info("Rate limiter reset")


class AdaptiveRateLimiter(RateLimiter):
    """Adaptive rate limiter that adjusts limits based on response patterns.
    
    Automatically reduces request rate when encountering rate limit errors
    and gradually increases when requests succeed.
    """
    
    def __init__(self, config: RateLimitConfig):
        """Initialize adaptive rate limiter.
        
        Args:
            config: Base rate limiting configuration.
        """
        super().__init__(config)
        self.original_requests_per_window = config.requests_per_window
        self.success_count = 0
        self.failure_count = 0
        self.last_adjustment = time.time()
        self.adjustment_window = 300  # 5 minutes
        
        logger.info("AdaptiveRateLimiter initialized with adaptive behavior")
    
    async def execute_with_backoff(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """Execute with adaptive rate limiting.
        
        Adjusts rate limits based on success/failure patterns.
        """
        try:
            result = await super().execute_with_backoff(func, *args, **kwargs)
            self._record_success()
            return result
            
        except Exception as e:
            self._record_failure(e)
            raise
    
    def _record_success(self) -> None:
        """Record successful request and potentially increase rate limit."""
        self.success_count += 1
        
        # Consider increasing rate limit after sustained success
        if (self.success_count >= 20 and 
            time.time() - self.last_adjustment > self.adjustment_window):
            
            if self.config.requests_per_window < self.original_requests_per_window:
                old_limit = self.config.requests_per_window
                self.config.requests_per_window = min(
                    self.config.requests_per_window + 1,
                    self.original_requests_per_window
                )
                
                logger.info(
                    f"Rate limit increased: {old_limit} -> {self.config.requests_per_window} "
                    f"after {self.success_count} successes"
                )
                
                self.success_count = 0
                self.failure_count = 0
                self.last_adjustment = time.time()
    
    def _record_failure(self, exception: Exception) -> None:
        """Record failed request and potentially decrease rate limit."""
        self.failure_count += 1
        
        # Check if this looks like a rate limit error
        error_str = str(exception).lower()
        is_rate_limit_error = any(
            phrase in error_str for phrase in [
                'rate limit', 'too many requests', '429', 'quota exceeded',
                'throttled', 'rate exceeded'
            ]
        )
        
        if is_rate_limit_error:
            # Immediately reduce rate limit
            old_limit = self.config.requests_per_window
            self.config.requests_per_window = max(
                self.config.requests_per_window // 2,
                1
            )
            
            logger.warning(
                f"Rate limit decreased due to rate limit error: "
                f"{old_limit} -> {self.config.requests_per_window}"
            )
            
            self.success_count = 0
            self.failure_count = 0
            self.last_adjustment = time.time()
        
        elif (self.failure_count >= 5 and 
              time.time() - self.last_adjustment > self.adjustment_window):
            
            # Reduce rate limit after sustained failures
            old_limit = self.config.requests_per_window
            self.config.requests_per_window = max(
                int(self.config.requests_per_window * 0.8),
                1
            )
            
            logger.warning(
                f"Rate limit decreased due to failures: "
                f"{old_limit} -> {self.config.requests_per_window} "
                f"after {self.failure_count} failures"
            )
            
            self.success_count = 0
            self.failure_count = 0
            self.last_adjustment = time.time()


class MultiServiceRateLimiter:
    """Rate limiter for multiple services with different limits."""
    
    def __init__(self):
        """Initialize multi-service rate limiter."""
        self.limiters: Dict[str, RateLimiter] = {}
        logger.info("MultiServiceRateLimiter initialized")
    
    def add_service(self, service_name: str, config: RateLimitConfig) -> None:
        """Add rate limiter for a service.
        
        Args:
            service_name: Unique service identifier.
            config: Rate limiting configuration for this service.
        """
        self.limiters[service_name] = AdaptiveRateLimiter(config)
        logger.info(f"Added rate limiter for service: {service_name}")
    
    async def execute_for_service(
        self,
        service_name: str,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """Execute function with service-specific rate limiting.
        
        Args:
            service_name: Service identifier.
            func: Function to execute.
            *args: Function arguments.
            **kwargs: Function keyword arguments.
            
        Returns:
            Function result.
            
        Raises:
            ValueError: If service not configured.
        """
        if service_name not in self.limiters:
            raise ValueError(f"Service '{service_name}' not configured")
        
        limiter = self.limiters[service_name]
        return await limiter.execute_with_backoff(func, *args, **kwargs)
    
    def get_service_status(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Get status for specific service.
        
        Args:
            service_name: Service identifier.
            
        Returns:
            Service status or None if not found.
        """
        limiter = self.limiters.get(service_name)
        if limiter:
            status = limiter.get_status()
            status['service_name'] = service_name
            return status
        return None
    
    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status for all services.
        
        Returns:
            Dictionary mapping service names to their status.
        """
        return {
            name: limiter.get_status()
            for name, limiter in self.limiters.items()
        }