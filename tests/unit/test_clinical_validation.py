"""Unit tests for Phase E clinical validation."""
from __future__ import annotations

import numpy as np
import pytest

from src.gait.validation.metrics import (
    ICC_THRESHOLD,
    ValidationMetrics,
    ErrorMetrics,
    PerformanceValidator,
    intraclass_correlation,
)
from src.gait.validation.anomaly_detector import (
    AnomalyFlag,
    AnomalyReport,
    AnomalyDetector,
)
from src.gait.validation.gold_standard import (
    ValidationResult,
    GoldStandardReport,
    GoldStandardComparator,
)
from src.gait.validation.clinical_report import (
    ClinicalValidationReport,
    ClinicalValidator,
)


class TestPerformanceValidator:
    """Tests for performance validation metrics."""

    @pytest.fixture
    def validator(self):
        """Create validator."""
        return PerformanceValidator()

    def test_compute_metrics_perfect_classification(self, validator):
        """Test metrics with perfect classification."""
        predicted = np.array([0.1, 0.2, 0.8, 0.9])
        actual = np.array([0, 0, 1, 1])

        metrics = validator.compute_metrics(predicted, actual, threshold=0.5)

        assert metrics.accuracy == 1.0
        assert metrics.sensitivity == 1.0
        assert metrics.specificity == 1.0
        assert metrics.precision == 1.0
        assert metrics.f1_score == 1.0

    def test_compute_metrics_partial_classification(self, validator):
        """Test metrics with partial classification."""
        predicted = np.array([0.1, 0.6, 0.8, 0.3])
        actual = np.array([0, 0, 1, 1])

        metrics = validator.compute_metrics(predicted, actual, threshold=0.5)

        assert 0 < metrics.accuracy < 1
        assert 0 <= metrics.sensitivity <= 1
        assert 0 <= metrics.specificity <= 1

    def test_compute_error_metrics_regression(self, validator):
        """Test error metrics for regression."""
        predicted = np.array([1.0, 2.0, 3.0, 4.0])
        actual = np.array([1.1, 1.9, 3.2, 3.8])

        errors = validator.compute_error_metrics(predicted, actual)

        assert errors.mae > 0
        assert errors.rmse > errors.mae  # RMSE >= MAE
        assert errors.bias < 0.2  # Small bias
        assert -1 <= errors.correlation <= 1

    def test_compute_error_metrics_perfect_prediction(self, validator):
        """Test error metrics with perfect prediction."""
        predicted = np.array([1.0, 2.0, 3.0, 4.0])
        actual = np.array([1.0, 2.0, 3.0, 4.0])

        errors = validator.compute_error_metrics(predicted, actual)

        assert errors.mae == 0.0
        assert errors.rmse == 0.0
        assert errors.bias == 0.0
        assert errors.correlation == 1.0

    def test_confidence_interval(self, validator):
        """Test confidence interval computation."""
        predicted = np.array([0, 1, 1, 1, 0, 1])
        actual = np.array([0, 1, 1, 1, 0, 1])

        metrics = validator.compute_metrics(predicted, actual)

        # Confidence interval should contain accuracy (with floating point tolerance)
        assert metrics.confidence_interval_95[0] <= metrics.accuracy + 1e-10
        assert metrics.accuracy <= metrics.confidence_interval_95[1] + 1e-10
        assert metrics.confidence_interval_95[0] >= 0
        assert metrics.confidence_interval_95[1] <= 1


class TestAnomalyDetector:
    """Tests for anomaly detection."""

    @pytest.fixture
    def detector(self):
        """Create detector."""
        return AnomalyDetector()

    def test_anomaly_detection_normal_values(self, detector):
        """Test detection with normal values."""
        cadence = np.array([100.0, 105.0, 110.0])
        speed = np.array([1.2, 1.3, 1.1])
        stride = np.array([0.6, 0.65, 0.62])
        stability = np.array([80.0, 85.0, 82.0])
        symmetry = np.array([5.0, 8.0, 6.0])

        report = detector.detect_anomalies(cadence, speed, stride, stability, symmetry)

        assert report.anomaly_rate == 0.0
        assert len(report.flags) == 0
        assert report.data_quality_score == 100.0

    def test_anomaly_detection_outliers(self, detector):
        """Test detection with outliers."""
        cadence = np.array([100.0, 200.0, 110.0])  # One outlier
        speed = np.array([1.2, 1.3, 1.1])
        stride = np.array([0.6, 0.65, 0.62])
        stability = np.array([80.0, 85.0, 82.0])
        symmetry = np.array([5.0, 8.0, 6.0])

        report = detector.detect_anomalies(cadence, speed, stride, stability, symmetry)

        assert report.anomalies_detected > 0
        assert report.anomaly_rate > 0.0
        assert report.data_quality_score < 100.0

    def test_pattern_anomalies(self, detector):
        """Test pattern anomaly detection."""
        # Normal movement
        heel_pos = np.array([0.1, 0.15, 0.12, 0.11])
        ankle_pos = np.array([0.2, 0.25, 0.22, 0.21])

        flags = detector.detect_pattern_anomalies(heel_pos, ankle_pos)

        assert len(flags) == 0

    def test_pattern_anomalies_jumps(self, detector):
        """Test detection of sudden jumps."""
        # Jump in position
        heel_pos = np.array([0.1, 0.15, 0.5, 0.11])  # Sudden jump
        ankle_pos = np.array([0.2, 0.25, 0.22, 0.21])

        flags = detector.detect_pattern_anomalies(heel_pos, ankle_pos)

        assert len(flags) > 0
        assert any(f.anomaly_type == "impossible" for f in flags)

    def test_anomaly_flag_creation(self):
        """Test AnomalyFlag dataclass."""
        flag = AnomalyFlag(
            severity="warning",
            anomaly_type="outlier",
            description="Value out of range",
            affected_parameter="cadence",
            value=200.0,
            expected_range=(60.0, 140.0),
        )
        assert flag.severity == "warning"
        assert flag.value > flag.expected_range[1]


class TestGoldStandardComparator:
    """Tests for gold standard comparison."""

    @pytest.fixture
    def comparator(self):
        """Create comparator."""
        return GoldStandardComparator()

    def test_compare_cadence_perfect_match(self, comparator):
        """Test cadence comparison with perfect match."""
        predicted = np.array([100.0, 110.0, 105.0])
        reference = np.array([100.0, 110.0, 105.0])

        result = comparator.compare_cadence(predicted, reference)

        assert result.passes_validation
        assert result.mean_absolute_error == 0.0
        assert result.correlation == 1.0

    def test_compare_cadence_within_tolerance(self, comparator):
        """Test cadence comparison within acceptable error."""
        predicted = np.array([100.0, 110.0, 105.0])
        reference = np.array([101.0, 109.0, 105.0])

        result = comparator.compare_cadence(predicted, reference)

        assert result.passes_validation
        assert result.mean_absolute_error <= 5.0

    def test_compare_cadence_exceeds_tolerance(self, comparator):
        """Test cadence comparison exceeding tolerance."""
        predicted = np.array([100.0, 110.0, 105.0])
        reference = np.array([115.0, 120.0, 125.0])

        result = comparator.compare_cadence(predicted, reference)

        assert not result.passes_validation
        assert result.mean_absolute_error > 5.0

    def test_compare_all_parameters(self, comparator):
        """Test comprehensive parameter comparison."""
        predicted = {
            "cadence_spm": np.array([100.0, 105.0]),
            "speed_ms": np.array([1.2, 1.3]),
            "stride_length_m": np.array([0.6, 0.65]),
        }
        reference = {
            "cadence_spm": np.array([101.0, 104.0]),
            "speed_ms": np.array([1.21, 1.29]),
            "stride_length_m": np.array([0.59, 0.66]),
        }

        report = comparator.compare_all_parameters(predicted, reference)

        assert report.total_parameters == 3
        assert report.parameters_validated == 3
        assert 0 <= report.validation_pass_rate <= 1


class TestClinicalValidator:
    """Tests for clinical validation report generation."""

    @pytest.fixture
    def clinical_validator(self):
        """Create clinical validator."""
        return ClinicalValidator()

    def test_generate_report_passing(self, clinical_validator):
        """Test report generation for passing validation."""
        from src.gait.validation.metrics import ValidationMetrics
        from src.gait.validation.anomaly_detector import AnomalyReport
        from src.gait.validation.gold_standard import GoldStandardReport

        metrics = ValidationMetrics(
            accuracy=0.95,
            sensitivity=0.92,
            specificity=0.97,
            precision=0.94,
            f1_score=0.93,
            auc_roc=0.96,
            mcc=0.90,
            confidence_interval_95=(0.92, 0.98),
        )
        anomaly_report = AnomalyReport(
            total_samples=100,
            anomalies_detected=2,
            anomaly_rate=0.02,
            flags=[],
            data_quality_score=98.0,
        )
        gold_standard = GoldStandardReport(
            total_parameters=3,
            parameters_validated=3,
            validation_pass_rate=0.95,  # 95% pass rate
            results=[],
            overall_confidence=0.95,
        )

        report = clinical_validator.generate_report(
            "test_001",
            validation_metrics=metrics,
            anomaly_report=anomaly_report,
            gold_standard_report=gold_standard,
        )

        assert report.validation_status == "pass"
        assert report.certification_level == "clinical"
        assert len(report.recommendations) == 0

    def test_generate_report_failing(self, clinical_validator):
        """Test report generation for failing validation."""
        from src.gait.validation.metrics import ValidationMetrics
        from src.gait.validation.anomaly_detector import AnomalyReport

        metrics = ValidationMetrics(
            accuracy=0.70,
            sensitivity=0.65,
            specificity=0.75,
            precision=0.72,
            f1_score=0.68,
            auc_roc=0.72,
            mcc=0.40,
            confidence_interval_95=(0.65, 0.75),
        )
        anomaly_report = AnomalyReport(
            total_samples=100,
            anomalies_detected=15,
            anomaly_rate=0.15,
            flags=[],
            data_quality_score=60.0,
        )

        report = clinical_validator.generate_report(
            "test_002",
            validation_metrics=metrics,
            anomaly_report=anomaly_report,
        )

        assert report.validation_status == "fail"
        assert report.certification_level == "failed"
        assert len(report.recommendations) > 0

    def test_report_printing(self, clinical_validator):
        """Test human-readable report generation."""
        from src.gait.validation.metrics import ValidationMetrics

        metrics = ValidationMetrics(
            accuracy=0.90,
            sensitivity=0.88,
            specificity=0.92,
            precision=0.91,
            f1_score=0.89,
            auc_roc=0.91,
            mcc=0.80,
            confidence_interval_95=(0.87, 0.93),
        )

        report = clinical_validator.generate_report(
            "test_003",
            validation_metrics=metrics,
        )

        report_text = clinical_validator.print_report(report)

        assert "CLINICAL VALIDATION REPORT" in report_text
        assert report.report_id in report_text
        assert "Accuracy" in report_text


class TestIntraclassCorrelation:
    """Tests for ICC(2,1) implementation."""

    def test_icc_high_correlation_exceeds_threshold(self):
        """ICC > 0.85 on a synthetic dataset where predicted and reference
        values are highly correlated (r > 0.95)."""
        rng = np.random.default_rng(42)
        reference = rng.uniform(80.0, 140.0, size=30)   # cadence-range values
        noise = rng.normal(0.0, 1.5, size=30)            # small measurement noise
        predicted = reference + noise

        pearson_r = np.corrcoef(predicted, reference)[0, 1]
        assert pearson_r > 0.95, f"Synthetic dataset correlation too low: {pearson_r:.3f}"

        icc = intraclass_correlation(predicted, reference)
        assert icc > ICC_THRESHOLD, (
            f"Expected ICC > {ICC_THRESHOLD}, got {icc:.4f} "
            f"(Pearson r = {pearson_r:.4f})"
        )

    def test_icc_perfect_agreement_is_one(self):
        """Perfect agreement (identical arrays) must return ICC = 1.0."""
        values = np.array([100.0, 105.0, 110.0, 108.0, 103.0])
        icc = intraclass_correlation(values, values.copy())
        assert icc == pytest.approx(1.0, abs=1e-6)

    def test_icc_low_correlation_below_threshold(self):
        """Uncorrelated (random) raters should produce ICC well below threshold."""
        rng = np.random.default_rng(99)
        rater_a = rng.uniform(0.0, 100.0, size=50)
        rater_b = rng.uniform(0.0, 100.0, size=50)
        icc = intraclass_correlation(rater_a, rater_b)
        assert icc < ICC_THRESHOLD

    def test_icc_mismatched_lengths_raises(self):
        """Mismatched array lengths must raise ValueError."""
        with pytest.raises(ValueError, match="same length"):
            intraclass_correlation(np.array([1.0, 2.0]), np.array([1.0]))

    def test_icc_too_few_subjects_raises(self):
        """Fewer than 2 subjects must raise ValueError."""
        with pytest.raises(ValueError, match="at least 2"):
            intraclass_correlation(np.array([1.0]), np.array([1.0]))

    def test_icc_propagates_into_validation_result(self):
        """GoldStandardComparator._compare_parameter must populate icc and
        passes_icc_threshold on ValidationResult."""
        rng = np.random.default_rng(7)
        reference = rng.uniform(90.0, 130.0, size=20)
        predicted = reference + rng.normal(0.0, 0.5, size=20)

        comparator = GoldStandardComparator()
        result = comparator.compare_cadence(predicted, reference)

        assert result.icc > ICC_THRESHOLD
        assert result.passes_icc_threshold is True

    def test_icc_summary_fields_in_report(self):
        """GoldStandardReport must include parameters_passing_icc and icc_pass_rate."""
        rng = np.random.default_rng(13)
        reference = rng.uniform(90.0, 130.0, size=20)
        predicted = reference + rng.normal(0.0, 0.5, size=20)

        comparator = GoldStandardComparator()
        report = comparator.compare_all_parameters(
            {"cadence_spm": predicted, "speed_ms": predicted / 100.0},
            {"cadence_spm": reference, "speed_ms": reference / 100.0},
        )

        assert report.parameters_passing_icc >= 1
        assert 0.0 <= report.icc_pass_rate <= 1.0


class TestValidationIntegration:
    """Integration tests for clinical validation."""

    def test_full_validation_pipeline(self):
        """Test complete validation pipeline."""
        validator = PerformanceValidator()
        detector = AnomalyDetector()
        comparator = GoldStandardComparator()
        clinical = ClinicalValidator()

        # Simulate real data
        predicted_binary = np.array([0, 1, 1, 0, 1, 1])
        actual_binary = np.array([0, 1, 1, 0, 1, 0])

        # Step 1: Performance metrics
        metrics = validator.compute_metrics(predicted_binary, actual_binary)
        assert metrics.accuracy > 0

        # Step 2: Anomaly detection
        cadence = np.array([100.0, 105.0, 110.0, 108.0, 102.0, 106.0])
        speed = np.array([1.2, 1.25, 1.3, 1.28, 1.22, 1.26])
        stride = np.array([0.60, 0.62, 0.65, 0.64, 0.61, 0.63])
        stability = np.array([80.0, 82.0, 85.0, 84.0, 81.0, 83.0])
        symmetry = np.array([5.0, 6.0, 7.0, 6.5, 5.5, 6.0])

        anomaly_report = detector.detect_anomalies(cadence, speed, stride, stability, symmetry)
        assert anomaly_report.total_samples == 6

        # Step 3: Clinical report
        report = clinical.generate_report(
            "integration_test",
            validation_metrics=metrics,
            anomaly_report=anomaly_report,
        )

        assert report.report_id == "integration_test"
        assert report.data_quality_score > 0
        assert report.certification_level in ["clinical", "research", "failed"]
