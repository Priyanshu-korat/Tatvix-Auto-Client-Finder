"""Tatvix AI Client Discovery System.

A comprehensive system for discovering, analyzing, and qualifying potential
IoT and embedded systems clients using AI-powered analysis and multi-source
discovery techniques.
"""

from .main import TatvixClientFinder
from .orchestration_models import (
    ExecutionResult,
    PipelineResult, 
    HealthStatus,
    RecoveryAction,
    PerformanceReport,
    PipelineConfiguration
)

__version__ = "1.0.0"
__author__ = "Tatvix AI Team"

__all__ = [
    "TatvixClientFinder",
    "ExecutionResult",
    "PipelineResult",
    "HealthStatus", 
    "RecoveryAction",
    "PerformanceReport",
    "PipelineConfiguration"
]