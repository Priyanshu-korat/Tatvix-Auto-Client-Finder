"""Search result caching with TTL support.

This module provides TTL-based caching for search results to improve
performance and reduce API calls for repeated queries.
"""

import asyncio
import hashlib
import json
import logging
import pickle
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from collections import OrderedDict
import threading

from .models import SearchResult, CacheEntry, SearchQuery
from utils.logger import get_logger


logger = get_logger(__name__)


class SearchCache:
    """TTL-based cache for search results.
    
    Implements in-memory caching with TTL expiration, LRU eviction,
    and optional persistent storage.
    """
    
    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: int = 3600,
        persistent: bool = True,
        cache_dir: Optional[Path] = None
    ):
        """Initialize search cache.
        
        Args:
            max_size: Maximum number of cache entries.
            default_ttl: Default TTL in seconds.
            persistent: Enable persistent storage.
            cache_dir: Directory for cache files.
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.persistent = persistent
        
        # In-memory cache storage
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        
        # Cache statistics
        self._stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'expired': 0,
            'total_queries': 0
        }
        
        # Persistent storage setup
        if persistent:
            self.cache_dir = cache_dir or Path("cache")
            self.cache_dir.mkdir(exist_ok=True)
            self.cache_file = self.cache_dir / "search_cache.pkl"
            self._load_persistent_cache()
        
        logger.info(
            f"SearchCache initialized: max_size={max_size}, "
            f"ttl={default_ttl}s, persistent={persistent}"
        )
    
    def _generate_cache_key(self, query: Union[str, SearchQuery]) -> str:
        """Generate cache key from query.
        
        Args:
            query: Search query string or SearchQuery object.
            
        Returns:
            Cache key string.
        """
        if isinstance(query, SearchQuery):
            # Create deterministic key from query components
            key_data = {
                'query': query.query.lower().strip(),
                'target_type': query.target_type.value,
                'country': query.country,
                'max_results': query.max_results
            }
            key_string = json.dumps(key_data, sort_keys=True)
        else:
            key_string = str(query).lower().strip()
        
        # Generate hash for consistent key length
        return hashlib.sha256(key_string.encode()).hexdigest()[:16]
    
    async def get(
        self,
        query: Union[str, SearchQuery],
        ttl: Optional[int] = None
    ) -> Optional[List[SearchResult]]:
        """Get cached search results.
        
        Args:
            query: Search query.
            ttl: Custom TTL override.
            
        Returns:
            Cached results or None if not found/expired.
        """
        cache_key = self._generate_cache_key(query)
        
        with self._lock:
            self._stats['total_queries'] += 1
            
            if cache_key not in self._cache:
                self._stats['misses'] += 1
                logger.debug(f"Cache miss for key: {cache_key}")
                return None
            
            entry = self._cache[cache_key]
            
            # Check if entry is expired
            if entry.is_expired:
                self._stats['expired'] += 1
                del self._cache[cache_key]
                logger.debug(f"Cache entry expired for key: {cache_key}")
                return None
            
            # Move to end (LRU)
            self._cache.move_to_end(cache_key)
            entry.mark_accessed()
            
            self._stats['hits'] += 1
            logger.debug(
                f"Cache hit for key: {cache_key}, "
                f"age: {(datetime.utcnow() - entry.created_at).total_seconds():.1f}s"
            )
            
            return entry.results.copy()
    
    async def set(
        self,
        query: Union[str, SearchQuery],
        results: List[SearchResult],
        ttl: Optional[int] = None
    ) -> None:
        """Store search results in cache.
        
        Args:
            query: Search query.
            results: Search results to cache.
            ttl: Custom TTL in seconds.
        """
        if not results:
            logger.debug("Not caching empty results")
            return
        
        cache_key = self._generate_cache_key(query)
        effective_ttl = ttl or self.default_ttl
        expires_at = datetime.utcnow() + timedelta(seconds=effective_ttl)
        
        entry = CacheEntry(
            query_hash=cache_key,
            results=results,
            expires_at=expires_at
        )
        
        with self._lock:
            # Remove oldest entries if cache is full
            while len(self._cache) >= self.max_size:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                self._stats['evictions'] += 1
            
            self._cache[cache_key] = entry
            logger.debug(
                f"Cached {len(results)} results for key: {cache_key}, "
                f"TTL: {effective_ttl}s"
            )
        
        # Persist to disk if enabled
        if self.persistent:
            await self._save_persistent_cache()
    
    async def invalidate(self, query: Union[str, SearchQuery]) -> bool:
        """Invalidate cached entry for query.
        
        Args:
            query: Search query to invalidate.
            
        Returns:
            True if entry was found and removed.
        """
        cache_key = self._generate_cache_key(query)
        
        with self._lock:
            if cache_key in self._cache:
                del self._cache[cache_key]
                logger.debug(f"Invalidated cache entry: {cache_key}")
                return True
            
            return False
    
    async def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
            self._stats = {key: 0 for key in self._stats}
            logger.info("Cache cleared")
        
        if self.persistent and self.cache_file.exists():
            self.cache_file.unlink()
    
    async def cleanup_expired(self) -> int:
        """Remove expired cache entries.
        
        Returns:
            Number of entries removed.
        """
        removed_count = 0
        
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.is_expired
            ]
            
            for key in expired_keys:
                del self._cache[key]
                removed_count += 1
            
            self._stats['expired'] += removed_count
        
        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} expired cache entries")
        
        return removed_count
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Dictionary with cache statistics.
        """
        with self._lock:
            hit_rate = (
                self._stats['hits'] / max(self._stats['total_queries'], 1)
            ) * 100
            
            return {
                'size': len(self._cache),
                'max_size': self.max_size,
                'hit_rate': round(hit_rate, 2),
                'hits': self._stats['hits'],
                'misses': self._stats['misses'],
                'evictions': self._stats['evictions'],
                'expired': self._stats['expired'],
                'total_queries': self._stats['total_queries']
            }
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get detailed cache information.
        
        Returns:
            Dictionary with cache details.
        """
        with self._lock:
            entries_info = []
            for key, entry in self._cache.items():
                age_seconds = (datetime.utcnow() - entry.created_at).total_seconds()
                ttl_remaining = (entry.expires_at - datetime.utcnow()).total_seconds()
                
                entries_info.append({
                    'key': key,
                    'result_count': len(entry.results),
                    'age_seconds': round(age_seconds, 1),
                    'ttl_remaining': round(max(ttl_remaining, 0), 1),
                    'access_count': entry.access_count,
                    'last_accessed': entry.last_accessed.isoformat() if entry.last_accessed else None
                })
            
            return {
                'entries': entries_info,
                'stats': self.get_stats(),
                'persistent': self.persistent,
                'cache_file': str(self.cache_file) if self.persistent else None
            }
    
    def _load_persistent_cache(self) -> None:
        """Load cache from persistent storage."""
        if not self.cache_file.exists():
            logger.debug("No persistent cache file found")
            return
        
        try:
            with open(self.cache_file, 'rb') as f:
                data = pickle.load(f)
            
            # Validate and load entries
            loaded_count = 0
            for key, entry_data in data.get('cache', {}).items():
                try:
                    entry = CacheEntry(**entry_data)
                    if not entry.is_expired:
                        self._cache[key] = entry
                        loaded_count += 1
                except Exception as e:
                    logger.warning(f"Failed to load cache entry {key}: {e}")
            
            # Load statistics
            if 'stats' in data:
                self._stats.update(data['stats'])
            
            logger.info(f"Loaded {loaded_count} cache entries from persistent storage")
            
        except Exception as e:
            logger.error(f"Failed to load persistent cache: {e}")
            # Create backup of corrupted file
            backup_file = self.cache_file.with_suffix('.backup')
            try:
                self.cache_file.rename(backup_file)
                logger.info(f"Corrupted cache file backed up to: {backup_file}")
            except Exception:
                pass
    
    async def _save_persistent_cache(self) -> None:
        """Save cache to persistent storage."""
        if not self.persistent:
            return
        
        try:
            # Prepare data for serialization
            cache_data = {}
            for key, entry in self._cache.items():
                if not entry.is_expired:
                    cache_data[key] = {
                        'query_hash': entry.query_hash,
                        'results': [result.dict() for result in entry.results],
                        'created_at': entry.created_at.isoformat(),
                        'expires_at': entry.expires_at.isoformat(),
                        'access_count': entry.access_count,
                        'last_accessed': entry.last_accessed.isoformat() if entry.last_accessed else None
                    }
            
            data = {
                'cache': cache_data,
                'stats': self._stats,
                'version': '1.0',
                'saved_at': datetime.utcnow().isoformat()
            }
            
            # Write to temporary file first
            temp_file = self.cache_file.with_suffix('.tmp')
            with open(temp_file, 'wb') as f:
                pickle.dump(data, f)
            
            # Atomic rename
            temp_file.replace(self.cache_file)
            
            logger.debug(f"Saved {len(cache_data)} cache entries to persistent storage")
            
        except Exception as e:
            logger.error(f"Failed to save persistent cache: {e}")


class AsyncSearchCache(SearchCache):
    """Async-optimized search cache with background cleanup.
    
    Extends SearchCache with async-specific optimizations and
    automatic background cleanup of expired entries.
    """
    
    def __init__(self, *args, cleanup_interval: int = 300, **kwargs):
        """Initialize async search cache.
        
        Args:
            cleanup_interval: Cleanup interval in seconds.
            *args, **kwargs: Arguments passed to SearchCache.
        """
        super().__init__(*args, **kwargs)
        self.cleanup_interval = cleanup_interval
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info(f"AsyncSearchCache initialized with {cleanup_interval}s cleanup interval")
    
    async def start(self) -> None:
        """Start background cleanup task."""
        if self._running:
            return
        
        self._running = True
        self._cleanup_task = asyncio.create_task(self._background_cleanup())
        logger.info("Background cache cleanup started")
    
    async def stop(self) -> None:
        """Stop background cleanup task."""
        self._running = False
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            
            self._cleanup_task = None
        
        # Final save to persistent storage
        if self.persistent:
            await self._save_persistent_cache()
        
        logger.info("Background cache cleanup stopped")
    
    async def _background_cleanup(self) -> None:
        """Background task for cleaning expired entries."""
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                if self._running:
                    await self.cleanup_expired()
                    
                    # Save to persistent storage periodically
                    if self.persistent:
                        await self._save_persistent_cache()
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Background cleanup error: {e}")
                await asyncio.sleep(60)  # Wait before retrying
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()