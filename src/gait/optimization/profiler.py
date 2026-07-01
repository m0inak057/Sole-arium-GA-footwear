"""Performance profiling and bottleneck detection."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import time
from contextlib import contextmanager

from gait.common.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class TimingStats:
    """Statistics for a single operation."""
    operation_name: str
    call_count: int = 0
    total_time_ms: float = 0.0
    min_time_ms: float = float("inf")
    max_time_ms: float = 0.0
    avg_time_ms: float = 0.0

    def update(self, elapsed_ms: float) -> None:
        """Update statistics with new measurement."""
        self.call_count += 1
        self.total_time_ms += elapsed_ms
        self.min_time_ms = min(self.min_time_ms, elapsed_ms)
        self.max_time_ms = max(self.max_time_ms, elapsed_ms)
        self.avg_time_ms = self.total_time_ms / self.call_count

    def get_summary(self) -> dict:
        """Get summary dictionary."""
        return {
            "operation": self.operation_name,
            "calls": self.call_count,
            "total_ms": round(self.total_time_ms, 2),
            "avg_ms": round(self.avg_time_ms, 2),
            "min_ms": round(self.min_time_ms, 2),
            "max_ms": round(self.max_time_ms, 2),
        }


@dataclass
class ProfilingReport:
    """Complete profiling report."""
    total_time_ms: float
    operations: dict[str, TimingStats] = field(default_factory=dict)
    bottlenecks: list[str] = field(default_factory=list)

    def add_operation(self, name: str, elapsed_ms: float) -> None:
        """Add operation timing."""
        if name not in self.operations:
            self.operations[name] = TimingStats(name)
        self.operations[name].update(elapsed_ms)

    def identify_bottlenecks(self, threshold_pct: float = 20.0) -> list[str]:
        """Identify bottleneck operations (>threshold% of total time)."""
        bottlenecks = []

        for name, stats in self.operations.items():
            pct = (stats.total_time_ms / self.total_time_ms) * 100 if self.total_time_ms > 0 else 0
            if pct > threshold_pct:
                bottlenecks.append(f"{name} ({pct:.1f}%)")

        self.bottlenecks = bottlenecks
        return bottlenecks


class PerformanceProfiler:
    """Profiles gait analysis operations."""

    def __init__(self):
        """Initialize profiler."""
        self.timings: dict[str, TimingStats] = {}
        self.session_start_time: Optional[float] = None

    @contextmanager
    def profile(self, operation_name: str):
        """Context manager for profiling a code block.

        Usage:
            with profiler.profile("heel_strike_detection"):
                # ... code ...
        """
        try:
            start_time = time.perf_counter()

            yield

        finally:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self.record(operation_name, elapsed_ms)

    def record(self, operation_name: str, elapsed_ms: float) -> None:
        """Record operation timing.

        Args:
            operation_name: Name of operation
            elapsed_ms: Time in milliseconds
        """
        try:
            if operation_name not in self.timings:
                self.timings[operation_name] = TimingStats(operation_name)

            self.timings[operation_name].update(elapsed_ms)

            logger.debug(
                "profiling.operation",
                extra={
                    "operation": operation_name,
                    "elapsed_ms": round(elapsed_ms, 2),
                },
            )

        except Exception as e:
            logger.error("profiling.record_failed", extra={"error": str(e)})

    def start_session(self) -> None:
        """Start profiling session."""
        self.session_start_time = time.perf_counter()
        self.timings.clear()
        logger.debug("profiling.session_started")

    def end_session(self) -> ProfilingReport:
        """End profiling session and generate report.

        Returns:
            ProfilingReport with all timings and bottlenecks
        """
        try:
            if self.session_start_time is None:
                logger.warning("profiling.no_active_session")
                return ProfilingReport(total_time_ms=0.0)

            total_ms = (time.perf_counter() - self.session_start_time) * 1000

            report = ProfilingReport(total_time_ms=total_ms)
            for name, stats in self.timings.items():
                report.operations[name] = stats

            bottlenecks = report.identify_bottlenecks(threshold_pct=20.0)

            logger.info(
                "profiling.session_ended",
                extra={
                    "total_ms": round(total_ms, 2),
                    "operations": len(self.timings),
                    "bottleneck_count": len(bottlenecks),
                },
            )

            return report

        except Exception as e:
            logger.error("profiling.end_session_failed", extra={"error": str(e)})
            return ProfilingReport(total_time_ms=0.0)

    def get_summary(self) -> dict[str, dict]:
        """Get summary of all timings.

        Returns:
            Dictionary mapping operation names to summary dicts
        """
        try:
            return {
                name: stats.get_summary()
                for name, stats in self.timings.items()
            }

        except Exception as e:
            logger.error("profiling.summary_failed", extra={"error": str(e)})
            return {}

    def reset(self) -> None:
        """Reset all timings."""
        self.timings.clear()
        self.session_start_time = None
        logger.debug("profiling.reset")

    def get_slowest_operations(self, count: int = 5) -> list[dict]:
        """Get slowest operations.

        Args:
            count: Number of operations to return

        Returns:
            List of operation summaries sorted by total time
        """
        try:
            sorted_ops = sorted(
                self.timings.items(),
                key=lambda x: x[1].total_time_ms,
                reverse=True,
            )

            return [
                stats.get_summary()
                for name, stats in sorted_ops[:count]
            ]

        except Exception as e:
            logger.error("profiling.slowest_failed", extra={"error": str(e)})
            return []

