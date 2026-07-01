"""Session-level gait analysis reporting and recommendations."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from gait.common.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class ClinicalFinding:
    """Single clinical finding or concern."""
    severity: str  # "info", "warning", "critical"
    category: str  # "symmetry", "efficiency", "stability", "injury_risk"
    description: str
    recommendation: str


@dataclass
class SessionReport:
    """Comprehensive report for a gait analysis session."""
    session_id: str
    duration_seconds: float
    frames_analyzed: int
    avg_cadence_spm: float
    avg_speed_ms: float
    avg_stability_score: float
    symmetry_metrics: dict  # From AdvancedMetricsAnalyzer
    efficiency_metrics: dict  # From AdvancedMetricsAnalyzer
    findings: list[ClinicalFinding]
    overall_quality_score: float  # 0-100


class SessionReporter:
    """Generates comprehensive session reports."""

    def __init__(self):
        """Initialize session reporter."""
        self.cadence_normal_range = (100, 130)  # steps per minute
        self.speed_normal_range = (1.0, 1.5)  # m/s
        self.stability_normal_threshold = 70.0  # stability score
        self.symmetry_normal_threshold = 10.0  # percent asymmetry

    def generate_report(
        self,
        session_id: str,
        frames: list[dict],
        cadence_values: list[float],
        speed_values: list[float],
        stability_scores: list[float],
        symmetry_metrics: dict,
        efficiency_metrics: dict,
    ) -> SessionReport:
        """Generate comprehensive session report.

        Args:
            session_id: Session identifier
            frames: List of frame data
            cadence_values: Cadence samples (SPM)
            speed_values: Speed samples (m/s)
            stability_scores: Stability scores (0-100)
            symmetry_metrics: From AdvancedMetricsAnalyzer
            efficiency_metrics: From AdvancedMetricsAnalyzer

        Returns:
            SessionReport with findings and quality score
        """
        try:
            duration = self._compute_duration(frames)
            findings = self._identify_findings(
                cadence_values,
                speed_values,
                stability_scores,
                symmetry_metrics,
                efficiency_metrics,
            )
            quality_score = self._compute_quality_score(
                stability_scores,
                cadence_values,
                symmetry_metrics,
            )

            report = SessionReport(
                session_id=session_id,
                duration_seconds=duration,
                frames_analyzed=len(frames),
                avg_cadence_spm=float(np.mean(cadence_values)) if cadence_values else 0.0,
                avg_speed_ms=float(np.mean(speed_values)) if speed_values else 0.0,
                avg_stability_score=float(np.mean(stability_scores)) if stability_scores else 0.0,
                symmetry_metrics=symmetry_metrics,
                efficiency_metrics=efficiency_metrics,
                findings=findings,
                overall_quality_score=quality_score,
            )

            logger.info(
                "session_report.generated",
                extra={
                    "session_id": session_id,
                    "duration_sec": duration,
                    "findings": len(findings),
                    "quality_score": quality_score,
                },
            )

            return report

        except Exception as e:
            logger.error("session_report.failed", extra={"error": str(e)})
            return SessionReport(
                session_id=session_id,
                duration_seconds=0.0,
                frames_analyzed=0,
                avg_cadence_spm=0.0,
                avg_speed_ms=0.0,
                avg_stability_score=0.0,
                symmetry_metrics={},
                efficiency_metrics={},
                findings=[],
                overall_quality_score=0.0,
            )

    def _identify_findings(
        self,
        cadence_values: list[float],
        speed_values: list[float],
        stability_scores: list[float],
        symmetry_metrics: dict,
        efficiency_metrics: dict,
    ) -> list[ClinicalFinding]:
        """Identify clinical findings from metrics."""
        findings = []

        try:
            # Cadence findings
            if cadence_values:
                avg_cadence = np.mean(cadence_values)
                if avg_cadence < self.cadence_normal_range[0]:
                    findings.append(ClinicalFinding(
                        severity="warning",
                        category="efficiency",
                        description=f"Low cadence: {avg_cadence:.1f} SPM (normal: {self.cadence_normal_range[0]}-{self.cadence_normal_range[1]})",
                        recommendation="Try increasing walking pace or shortening stride length",
                    ))
                elif avg_cadence > self.cadence_normal_range[1]:
                    findings.append(ClinicalFinding(
                        severity="info",
                        category="efficiency",
                        description=f"High cadence: {avg_cadence:.1f} SPM (normal: {self.cadence_normal_range[0]}-{self.cadence_normal_range[1]})",
                        recommendation="Natural variation; monitor for fatigue",
                    ))

            # Stability findings
            if stability_scores:
                avg_stability = np.mean(stability_scores)
                if avg_stability < self.stability_normal_threshold:
                    findings.append(ClinicalFinding(
                        severity="warning",
                        category="stability",
                        description=f"Low gait stability: {avg_stability:.1f}/100 (threshold: {self.stability_normal_threshold})",
                        recommendation="Consider balance training or consultation with physical therapist",
                    ))

            # Symmetry findings
            asymmetry_flags = symmetry_metrics.get("asymmetry_flags", [])
            if asymmetry_flags:
                for flag in asymmetry_flags:
                    findings.append(ClinicalFinding(
                        severity="warning",
                        category="symmetry",
                        description=f"Detected {flag.replace('_', ' ')}",
                        recommendation="May indicate injury, weakness, or pain on one side",
                    ))

            # Efficiency findings
            efficiency = efficiency_metrics.get("walking_efficiency_score", 0.0)
            if efficiency < 50.0:
                findings.append(ClinicalFinding(
                    severity="warning",
                    category="efficiency",
                    description=f"Low walking efficiency: {efficiency:.1f}/100",
                    recommendation="Gait pattern may be compensatory or inefficient",
                ))

        except Exception as e:
            logger.error("findings.identification_failed", extra={"error": str(e)})

        return findings

    def _compute_quality_score(
        self,
        stability_scores: list[float],
        cadence_values: list[float],
        symmetry_metrics: dict,
    ) -> float:
        """Compute overall data quality score (0-100)."""
        try:
            components = []

            # Stability consistency
            if stability_scores:
                avg_stability = np.mean(stability_scores)
                components.append(avg_stability)

            # Cadence consistency
            if cadence_values:
                cadence_values_array = np.array(cadence_values)
                # Remove outliers and compute coefficient of variation
                valid_cadence = cadence_values_array[cadence_values_array > 0]
                if len(valid_cadence) > 0:
                    cv = np.std(valid_cadence) / np.mean(valid_cadence) if np.mean(valid_cadence) > 0 else 1.0
                    consistency = max(0.0, 100.0 - (cv * 100))
                    components.append(consistency)

            # Symmetry score (inverse of asymmetry)
            asymmetry_flags = symmetry_metrics.get("asymmetry_flags", [])
            symmetry_component = max(0.0, 100.0 - (len(asymmetry_flags) * 20))
            components.append(symmetry_component)

            quality_score = float(np.mean(components)) if components else 0.0
            return min(100.0, max(0.0, quality_score))

        except Exception:
            return 0.0

    def _compute_duration(self, frames: list[dict]) -> float:
        """Compute session duration from frames."""
        try:
            if not frames or len(frames) < 2:
                return 0.0

            first_timestamp = frames[0].get("timestamp_ms", 0)
            last_timestamp = frames[-1].get("timestamp_ms", 0)

            duration_ms = last_timestamp - first_timestamp
            duration_s = duration_ms / 1000.0

            return max(0.0, float(duration_s))

        except Exception:
            return 0.0

