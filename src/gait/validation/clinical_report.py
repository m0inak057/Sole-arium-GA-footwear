"""Clinical validation report generation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from datetime import datetime

from gait.common.logging_utils import get_logger
from gait.validation.metrics import ValidationMetrics, ErrorMetrics
from gait.validation.anomaly_detector import AnomalyReport
from gait.validation.gold_standard import GoldStandardReport

logger = get_logger(__name__)


@dataclass
class ClinicalValidationReport:
    """Complete clinical validation report."""
    report_id: str
    timestamp: str
    data_quality_score: float  # 0-100
    validation_status: str  # "pass", "pass_with_warnings", "fail"
    accuracy: Optional[float]
    sensitivity: Optional[float]
    specificity: Optional[float]
    mean_absolute_error: Optional[float]
    anomaly_rate: float
    gold_standard_pass_rate: float
    recommendations: list[str]
    certification_level: str  # "research", "clinical", "failed"


class ClinicalValidator:
    """Orchestrates clinical validation of gait analysis system."""

    def __init__(self):
        """Initialize clinical validator."""
        self.min_data_quality_score = 70.0
        self.min_accuracy = 0.85
        self.max_anomaly_rate = 0.05  # 5%
        self.min_gold_standard_pass_rate = 0.90  # 90%

    def generate_report(
        self,
        report_id: str,
        validation_metrics: Optional[ValidationMetrics] = None,
        error_metrics: Optional[ErrorMetrics] = None,
        anomaly_report: Optional[AnomalyReport] = None,
        gold_standard_report: Optional[GoldStandardReport] = None,
    ) -> ClinicalValidationReport:
        """Generate comprehensive clinical validation report.

        Args:
            report_id: Unique report identifier
            validation_metrics: Performance metrics from validation
            error_metrics: Error analysis metrics
            anomaly_report: Anomaly detection report
            gold_standard_report: Gold standard comparison report

        Returns:
            ClinicalValidationReport with findings and recommendations
        """
        try:
            recommendations = []
            status_flags = []

            # Extract metrics
            accuracy = validation_metrics.accuracy if validation_metrics else 0.0
            sensitivity = validation_metrics.sensitivity if validation_metrics else 0.0
            specificity = validation_metrics.specificity if validation_metrics else 0.0
            mae = error_metrics.mae if error_metrics else 0.0
            data_quality = anomaly_report.data_quality_score if anomaly_report else 0.0
            anomaly_rate = anomaly_report.anomaly_rate if anomaly_report else 0.0
            gold_standard_rate = gold_standard_report.validation_pass_rate if gold_standard_report else 0.0

            # Check accuracy threshold
            if accuracy < self.min_accuracy:
                status_flags.append("low_accuracy")
                recommendations.append(f"System accuracy ({accuracy:.1%}) below clinical threshold ({self.min_accuracy:.1%})")

            # Check data quality
            if data_quality < self.min_data_quality_score:
                status_flags.append("low_quality")
                recommendations.append(f"Data quality ({data_quality:.1f}/100) below acceptable level")

            # Check anomaly rate
            if anomaly_rate > self.max_anomaly_rate:
                status_flags.append("high_anomalies")
                recommendations.append(f"Anomaly rate ({anomaly_rate:.1%}) exceeds threshold ({self.max_anomaly_rate:.1%})")

            # Check gold standard
            if gold_standard_rate < self.min_gold_standard_pass_rate:
                status_flags.append("gold_standard_fail")
                recommendations.append(f"Gold standard pass rate ({gold_standard_rate:.1%}) below requirement ({self.min_gold_standard_pass_rate:.1%})")

            # Determine certification level
            if not status_flags:
                certification_level = "clinical"
                validation_status = "pass"
            elif len(status_flags) == 1 and status_flags[0] not in ["low_accuracy", "gold_standard_fail"]:
                certification_level = "research"
                validation_status = "pass_with_warnings"
            else:
                certification_level = "failed"
                validation_status = "fail"

            # Add specific recommendations based on findings
            if sensitivity and sensitivity < 0.80:
                recommendations.append(f"Low sensitivity ({sensitivity:.1%}): may miss true positives")

            if specificity and specificity < 0.80:
                recommendations.append(f"Low specificity ({specificity:.1%}): may have false positives")

            logger.info(
                "validation.clinical_report_generated",
                extra={
                    "report_id": report_id,
                    "status": validation_status,
                    "certification": certification_level,
                    "accuracy": round(accuracy, 3),
                    "data_quality": round(data_quality, 1),
                },
            )

            return ClinicalValidationReport(
                report_id=report_id,
                timestamp=datetime.now().isoformat(),
                data_quality_score=data_quality,
                validation_status=validation_status,
                accuracy=accuracy if validation_metrics else None,
                sensitivity=sensitivity if validation_metrics else None,
                specificity=specificity if validation_metrics else None,
                mean_absolute_error=mae if error_metrics else None,
                anomaly_rate=anomaly_rate,
                gold_standard_pass_rate=gold_standard_rate,
                recommendations=recommendations,
                certification_level=certification_level,
            )

        except Exception as e:
            logger.error("validation.report_generation_failed", extra={"error": str(e)})
            return ClinicalValidationReport(
                report_id=report_id,
                timestamp=datetime.now().isoformat(),
                data_quality_score=0.0,
                validation_status="fail",
                accuracy=None,
                sensitivity=None,
                specificity=None,
                mean_absolute_error=None,
                anomaly_rate=0.0,
                gold_standard_pass_rate=0.0,
                recommendations=["Report generation failed"],
                certification_level="failed",
            )

    def print_report(self, report: ClinicalValidationReport) -> str:
        """Generate human-readable report text.

        Args:
            report: ClinicalValidationReport to format

        Returns:
            Formatted report string
        """
        try:
            lines = [
                "=" * 70,
                "CLINICAL VALIDATION REPORT",
                "=" * 70,
                f"Report ID: {report.report_id}",
                f"Timestamp: {report.timestamp}",
                f"Status: {report.validation_status.upper()}",
                f"Certification Level: {report.certification_level.upper()}",
                "",
                "PERFORMANCE METRICS:",
                f"  Data Quality Score: {report.data_quality_score:.1f}/100",
                f"  Accuracy: {report.accuracy:.1%}" if report.accuracy is not None else "  Accuracy: N/A",
                f"  Sensitivity: {report.sensitivity:.1%}" if report.sensitivity is not None else "  Sensitivity: N/A",
                f"  Specificity: {report.specificity:.1%}" if report.specificity is not None else "  Specificity: N/A",
                f"  Mean Absolute Error: {report.mean_absolute_error:.3f}" if report.mean_absolute_error is not None else "  Mean Absolute Error: N/A",
                "",
                "QUALITY METRICS:",
                f"  Anomaly Rate: {report.anomaly_rate:.1%}",
                f"  Gold Standard Pass Rate: {report.gold_standard_pass_rate:.1%}",
                "",
            ]

            if report.recommendations:
                lines.append("RECOMMENDATIONS:")
                for i, rec in enumerate(report.recommendations, 1):
                    lines.append(f"  {i}. {rec}")
                lines.append("")

            lines.extend([
                "=" * 70,
                "END OF REPORT",
                "=" * 70,
            ])

            return "\n".join(lines)

        except Exception as e:
            logger.error("validation.report_printing_failed", extra={"error": str(e)})
            return f"Error formatting report: {str(e)}"

