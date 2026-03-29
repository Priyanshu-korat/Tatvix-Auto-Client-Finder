"""Database module for Tatvix AI Client Discovery System.

This module provides database operations, duplicate detection,
and data persistence functionality.
"""

from .duplicate_checker import DuplicateChecker, SimilarCompany, DuplicateDecision
from .vector_store import VectorStore, InMemoryVectorStore

__all__ = [
    'DuplicateChecker',
    'SimilarCompany', 
    'DuplicateDecision',
    'VectorStore',
    'InMemoryVectorStore'
]