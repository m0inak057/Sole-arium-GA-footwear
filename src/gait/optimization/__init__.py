"""Performance optimization modules."""
from gait.optimization.cache_manager import (
    ComputationCache,
    CacheEntry,
    CacheStats,
    hash_input,
)
from gait.optimization.vectorization import (
    VectorizedAnalyzer,
    BatchMetrics,
)
from gait.optimization.profiler import (
    PerformanceProfiler,
    TimingStats,
    ProfilingReport,
)
from gait.optimization.fast_path import (
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

