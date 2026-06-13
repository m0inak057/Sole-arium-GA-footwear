"""Performance optimization modules."""
from src.gait.optimization.cache_manager import (
    ComputationCache,
    CacheEntry,
    CacheStats,
    hash_input,
)
from src.gait.optimization.vectorization import (
    VectorizedAnalyzer,
    BatchMetrics,
)
from src.gait.optimization.profiler import (
    PerformanceProfiler,
    TimingStats,
    ProfilingReport,
)
from src.gait.optimization.fast_path import (
    FastPathOptimizer,
    FastPathConfig,
)

__all__ = [
    "ComputationCache",
    "CacheEntry",
    "CacheStats",
    "hash_input",
    "VectorizedAnalyzer",
    "BatchMetrics",
    "PerformanceProfiler",
    "TimingStats",
    "ProfilingReport",
    "FastPathOptimizer",
    "FastPathConfig",
]
