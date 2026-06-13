"""Unit tests for Phase D performance optimization."""
from __future__ import annotations

import numpy as np
import pytest
import time

from src.gait.optimization.cache_manager import (
    ComputationCache,
    CacheEntry,
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


class TestCacheEntry:
    """Tests for cache entry."""

    def test_cache_entry_creation(self):
        """Test cache entry creation."""
        entry = CacheEntry(value=42, timestamp=time.time(), ttl_seconds=100.0)
        assert entry.value == 42
        assert entry.hit_count == 0
        assert not entry.is_expired()

    def test_cache_entry_expiration(self):
        """Test cache entry expiration."""
        entry = CacheEntry(value=42, timestamp=time.time() - 200, ttl_seconds=100.0)
        assert entry.is_expired()

    def test_cache_entry_hit_recording(self):
        """Test hit recording."""
        entry = CacheEntry(value=42, timestamp=time.time(), ttl_seconds=100.0)
        assert entry.hit_count == 0

        entry.record_hit()
        assert entry.hit_count == 1
        assert len(entry.access_times) == 1

        entry.record_hit()
        assert entry.hit_count == 2


class TestComputationCache:
    """Tests for computation cache."""

    @pytest.fixture
    def cache(self):
        """Create cache."""
        return ComputationCache(max_entries=10, default_ttl_seconds=1.0)

    def test_cache_put_get(self, cache):
        """Test put and get operations."""
        cache.put("key1", 42)
        result = cache.get("key1")
        assert result == 42

    def test_cache_miss(self, cache):
        """Test cache miss."""
        result = cache.get("nonexistent")
        assert result is None

    def test_cache_expiration(self, cache):
        """Test cache expiration."""
        cache.put("key1", 42, ttl_seconds=0.1)
        result = cache.get("key1")
        assert result == 42

        time.sleep(0.2)
        result = cache.get("key1")
        assert result is None

    def test_cache_capacity(self, cache):
        """Test cache eviction at capacity."""
        for i in range(15):
            cache.put(f"key{i}", i)

        # Should have evicted oldest entries
        assert len(cache.cache) <= cache.max_entries

    def test_cache_clear(self, cache):
        """Test cache clearing."""
        cache.put("key1", 42)
        cache.put("key2", 43)
        assert len(cache.cache) == 2

        cache.clear()
        assert len(cache.cache) == 0

    def test_compute_or_cache(self, cache):
        """Test compute-or-cache pattern."""
        call_count = [0]

        def expensive_fn():
            call_count[0] += 1
            return 42

        # First call computes
        result1 = cache.compute_or_cache("key1", expensive_fn)
        assert result1 == 42
        assert call_count[0] == 1

        # Second call uses cache
        result2 = cache.compute_or_cache("key1", expensive_fn)
        assert result2 == 42
        assert call_count[0] == 1  # Not called again

    def test_cache_stats(self, cache):
        """Test cache statistics."""
        cache.put("key1", 42)
        cache.get("key1")
        cache.get("nonexistent")

        stats = cache.get_stats()
        assert stats.total_puts == 1
        assert stats.total_gets == 2
        assert stats.total_hits == 1
        assert stats.hit_rate == 0.5


class TestHashInput:
    """Tests for input hashing."""

    def test_hash_consistency(self):
        """Test hash consistency."""
        data = {"a": 1, "b": 2}
        hash1 = hash_input(data)
        hash2 = hash_input(data)
        assert hash1 == hash2

    def test_hash_different_inputs(self):
        """Test different inputs produce different hashes."""
        hash1 = hash_input({"a": 1})
        hash2 = hash_input({"a": 2})
        assert hash1 != hash2

    def test_hash_unhashable_types(self):
        """Test hashing unhashable types."""
        data = [1, 2, 3]
        hash_result = hash_input(data)
        assert isinstance(hash_result, str)
        assert len(hash_result) == 64  # SHA256 hex length


class TestVectorizedAnalyzer:
    """Tests for vectorized analyzer."""

    @pytest.fixture
    def analyzer(self):
        """Create analyzer."""
        return VectorizedAnalyzer(fps=120.0)

    def test_cadence_batch_basic(self, analyzer):
        """Test batch cadence computation."""
        heel_strikes = [
            [0, 120, 240],  # 1 Hz
            [0, 100, 200],  # 1.2 Hz
        ]

        cadences = analyzer.compute_cadence_batch(heel_strikes)

        assert len(cadences) == 2
        assert cadences[0] > 0
        assert cadences[1] > cadences[0]  # Higher cadence

    def test_cadence_batch_empty(self, analyzer):
        """Test with empty data."""
        heel_strikes = [[], [0]]

        cadences = analyzer.compute_cadence_batch(heel_strikes)

        assert len(cadences) == 2
        assert cadences[0] == 0.0
        assert cadences[1] == 0.0

    def test_speed_batch(self, analyzer):
        """Test batch speed computation."""
        cadence = np.array([120.0, 140.0])
        stride_length = np.array([0.7, 0.75])

        speeds = analyzer.compute_speed_batch(cadence, stride_length)

        assert len(speeds) == 2
        assert all(speeds > 0)
        assert speeds[1] > speeds[0]

    def test_stability_batch(self, analyzer):
        """Test batch stability computation."""
        heel_positions = [
            np.array([0.5] * 100),  # Perfect stability
            np.array(np.random.normal(0.5, 0.1, 100)),  # Variable
        ]

        stabilities = analyzer.compute_stability_batch(heel_positions)

        assert len(stabilities) == 2
        assert stabilities[0] > stabilities[1]  # More stable first

    def test_symmetry_batch(self, analyzer):
        """Test batch symmetry computation."""
        left_params = [{"stride_length_m": 0.7}]
        right_params = [{"stride_length_m": 0.72}]

        symmetries = analyzer.compute_symmetry_batch(left_params, right_params)

        assert len(symmetries) == 1
        assert 0 <= symmetries[0] <= 100

    def test_outlier_filtering(self, analyzer):
        """Test outlier filtering."""
        values = np.array([1.0, 2.0, 3.0, 100.0, 2.5])  # 100 is outlier

        filtered, outlier_mask = analyzer.filter_outliers_batch(values, std_threshold=1.5)

        assert np.sum(outlier_mask) >= 1  # Should detect outlier
        assert len(filtered) < len(values)

    def test_normalization(self, analyzer):
        """Test batch normalization."""
        values = np.array([0.0, 50.0, 100.0])

        normalized = analyzer.normalize_batch(values)

        assert normalized[0] == 0.0
        assert normalized[-1] == 1.0
        assert 0 <= normalized[1] <= 1

    def test_resampling(self, analyzer):
        """Test batch resampling."""
        data = [np.array([0.0, 1.0, 2.0])]
        resampled = analyzer.resample_batch(data, target_size=6)

        assert len(resampled) == 1
        assert len(resampled[0]) == 6


class TestTimingStats:
    """Tests for timing statistics."""

    def test_timing_stats_creation(self):
        """Test timing stats creation."""
        stats = TimingStats("operation")
        assert stats.operation_name == "operation"
        assert stats.call_count == 0

    def test_timing_stats_update(self):
        """Test updating stats."""
        stats = TimingStats("op")
        stats.update(10.0)
        stats.update(20.0)

        assert stats.call_count == 2
        assert stats.total_time_ms == 30.0
        assert stats.avg_time_ms == 15.0
        assert stats.min_time_ms == 10.0
        assert stats.max_time_ms == 20.0

    def test_timing_stats_summary(self):
        """Test stats summary."""
        stats = TimingStats("op")
        stats.update(15.0)

        summary = stats.get_summary()
        assert summary["operation"] == "op"
        assert summary["calls"] == 1
        assert summary["avg_ms"] == 15.0


class TestPerformanceProfiler:
    """Tests for performance profiler."""

    @pytest.fixture
    def profiler(self):
        """Create profiler."""
        return PerformanceProfiler()

    def test_profiler_recording(self, profiler):
        """Test recording operations."""
        profiler.record("operation_a", 10.0)
        profiler.record("operation_a", 20.0)
        profiler.record("operation_b", 5.0)

        summary = profiler.get_summary()
        assert "operation_a" in summary
        assert summary["operation_a"]["calls"] == 2
        assert summary["operation_a"]["avg_ms"] == 15.0

    def test_profiler_context_manager(self, profiler):
        """Test profiler context manager."""
        with profiler.profile("test_operation"):
            time.sleep(0.01)

        summary = profiler.get_summary()
        assert "test_operation" in summary
        assert summary["test_operation"]["calls"] == 1

    def test_profiler_session(self, profiler):
        """Test profiler session."""
        profiler.start_session()
        profiler.record("op_a", 50.0)
        profiler.record("op_b", 30.0)
        profiler.record("op_a", 20.0)

        report = profiler.end_session()

        assert len(report.operations) == 2
        assert report.operations["op_a"].call_count == 2

    def test_profiler_bottleneck_detection(self, profiler):
        """Test bottleneck detection."""
        profiler.record("slow_op", 80.0)
        profiler.record("fast_op", 20.0)

        summary = profiler.get_summary()
        # Manual report creation for testing
        report = ProfilingReport(total_time_ms=100.0)
        for name, stats in profiler.timings.items():
            report.operations[name] = stats

        bottlenecks = report.identify_bottlenecks(threshold_pct=50.0)
        assert "slow_op" in str(bottlenecks)

    def test_profiler_slowest_operations(self, profiler):
        """Test getting slowest operations."""
        profiler.record("slow1", 100.0)
        profiler.record("slow2", 80.0)
        profiler.record("fast", 10.0)

        slowest = profiler.get_slowest_operations(count=2)

        assert len(slowest) == 2
        assert slowest[0]["total_ms"] >= slowest[1]["total_ms"]

    def test_profiler_reset(self, profiler):
        """Test profiler reset."""
        profiler.record("op", 10.0)
        assert len(profiler.timings) == 1

        profiler.reset()
        assert len(profiler.timings) == 0


class TestFastPathOptimizer:
    """Tests for fast path optimization."""

    @pytest.fixture
    def optimizer(self):
        """Create optimizer."""
        return FastPathOptimizer()

    def test_fast_cadence_estimation(self, optimizer):
        """Test fast cadence estimation."""
        heel_strikes = np.array([0, 120, 240, 360])

        cadence = optimizer.fast_cadence_estimation(heel_strikes)

        assert cadence > 0
        assert 30 <= cadence <= 250  # Reasonable range (SPM)

    def test_fast_distance_computation(self, optimizer):
        """Test fast distance computation."""
        points1 = np.array([[0.0, 0.0], [1.0, 1.0]])
        points2 = np.array([[0.0, 0.0], [3.0, 4.0]])

        distances = optimizer.fast_distance_computation(points1, points2)

        assert distances.shape == (2, 2)
        assert distances[0, 0] < 0.01  # First points are same
        assert distances[1, 1] > 0  # Different points

    def test_fast_filtering(self, optimizer):
        """Test fast moving average filtering."""
        # Create signal with noise
        signal = np.array([1.0, 1.1, 1.2, 4.0, 4.1, 4.0, 3.9, 4.1, 4.0])

        filtered = optimizer.fast_filtering(signal, window_size=3)

        assert len(filtered) == len(signal)
        # Filtered values should smooth out high-frequency noise
        assert filtered.dtype == np.float32

    def test_fast_peak_detection(self, optimizer):
        """Test fast peak detection."""
        signal = np.array([0, 1, 2, 1, 0, 0, 1, 2, 1, 0])

        peaks = optimizer.fast_peak_detection(signal)

        assert len(peaks) >= 1
        assert all(0 <= p < len(signal) for p in peaks)

    def test_fast_correlation(self, optimizer):
        """Test fast correlation computation."""
        signal1 = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        signal2 = np.array([1.0, 2.0, 3.0, 4.0, 5.0])

        corr = optimizer.fast_correlation(signal1, signal2)

        assert 0.99 < corr <= 1.0  # Perfect correlation

    def test_fast_correlation_uncorrelated(self, optimizer):
        """Test correlation of uncorrelated signals."""
        signal1 = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        signal2 = np.array([5.0, 4.0, 3.0, 2.0, 1.0])

        corr = optimizer.fast_correlation(signal1, signal2)

        assert -1.0 <= corr < 0  # Negative correlation


class TestOptimizationIntegration:
    """Integration tests for optimization modules."""

    def test_cache_with_vectorization(self):
        """Test caching vectorized operations."""
        cache = ComputationCache()
        analyzer = VectorizedAnalyzer()

        def compute_cadences():
            heel_strikes = [[0, 120, 240], [0, 100, 200]]
            return analyzer.compute_cadence_batch(heel_strikes)

        # First call computes
        result1 = cache.compute_or_cache("cadences", compute_cadences)

        # Second call uses cache
        result2 = cache.compute_or_cache("cadences", compute_cadences)

        assert np.allclose(result1, result2)

    def test_profiler_with_fast_path(self):
        """Test profiling fast path operations."""
        profiler = PerformanceProfiler()
        optimizer = FastPathOptimizer()

        with profiler.profile("distance_computation"):
            points1 = np.random.randn(100, 2)
            points2 = np.random.randn(100, 2)
            optimizer.fast_distance_computation(points1, points2)

        summary = profiler.get_summary()
        assert "distance_computation" in summary

    def test_optimization_pipeline(self):
        """Test complete optimization pipeline."""
        cache = ComputationCache()
        vectorizer = VectorizedAnalyzer()
        profiler = PerformanceProfiler()
        optimizer = FastPathOptimizer()

        profiler.start_session()

        # Simulate pipeline
        heel_strikes_batch = [[0, 120, 240], [0, 110, 220]]

        with profiler.profile("cadence_batch"):
            cadences = vectorizer.compute_cadence_batch(heel_strikes_batch)

        with profiler.profile("fast_path"):
            for heel_strikes in heel_strikes_batch:
                if len(heel_strikes) > 0:
                    optimizer.fast_cadence_estimation(np.array(heel_strikes))

        report = profiler.end_session()

        assert len(report.operations) >= 2
        assert report.total_time_ms > 0
