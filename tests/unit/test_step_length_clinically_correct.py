"""Test clinically correct step length computation with interleaved L/R heel strikes."""
from __future__ import annotations

import pytest

from gait.analysis.parameters import compute_step_lengths_lr


@pytest.mark.unit
class TestClinicalStepLengthComputation:
    """Verify step length computed correctly: from one foot's strike to NEXT opposite foot's strike."""

    def test_step_lengths_with_interleaved_asymmetric_sequence(self):
        """
        Test with realistic interleaved heel-strike sequence where left and right
        feet take different step lengths.

        Sequence (in time order):
        R1 (100px) â†’ L1 (250px) â†’ R2 (480px) â†’ L2 (600px) â†’ R3 (880px) â†’ L3 (950px)

        Clinical step lengths:
        - step_length_left = distances from R strikes to next L strikes
          = [|R1â†’L1| = 150, |R2â†’L2| = 120, |R3â†’L3| = 70]
          = mean(150, 120, 70) = 113.33 px

        - step_length_right = distances from L strikes to next R strikes
          = [|L1â†’R2| = 230, |L2â†’R3| = 280]
          = mean(230, 280) = 255 px

        With scale_m_per_px = 0.01:
        - step_length_left_m = 113.33 * 0.01 = 1.1333 m
        - step_length_right_m = 255 * 0.01 = 2.55 m
        """
        # Interleaved heel strikes in time/position order
        heel_strikes_l_px = [250.0, 600.0, 950.0]  # Left foot strikes at these x-positions
        heel_strikes_r_px = [100.0, 480.0, 880.0]  # Right foot strikes at these x-positions
        scale_m_per_px = 0.01

        step_length_left_m, step_length_right_m = compute_step_lengths_lr(
            heel_strikes_l_px, heel_strikes_r_px, scale_m_per_px
        )

        # Manual calculation verification:
        # step_length_left: Râ†’L distances
        # R1(100) â†’ L1(250) = 150px
        # R2(480) â†’ L2(600) = 120px
        # R3(880) â†’ L3(950) = 70px
        # mean = (150 + 120 + 70) / 3 = 340 / 3 = 113.33px
        # result = 113.33 * 0.01 = 1.1333m

        # step_length_right: Lâ†’R distances
        # L1(250) â†’ R2(480) = 230px
        # L2(600) â†’ R3(880) = 280px
        # mean = (230 + 280) / 2 = 510 / 2 = 255px
        # result = 255 * 0.01 = 2.55m

        expected_step_left_m = (150.0 + 120.0 + 70.0) / 3 * scale_m_per_px
        expected_step_right_m = (230.0 + 280.0) / 2 * scale_m_per_px

        assert abs(step_length_left_m - expected_step_left_m) < 0.001, \
            f"Step left: expected {expected_step_left_m:.4f}m, got {step_length_left_m:.4f}m"
        assert abs(step_length_right_m - expected_step_right_m) < 0.001, \
            f"Step right: expected {expected_step_right_m:.4f}m, got {step_length_right_m:.4f}m"

        # CRITICAL: Verify asymmetry
        assert step_length_left_m != step_length_right_m, \
            f"Step lengths should be asymmetric: left={step_length_left_m:.4f}m, right={step_length_right_m:.4f}m"
        assert step_length_right_m > step_length_left_m, \
            f"Right step should be longer (2.55 > 1.13): left={step_length_left_m:.4f}m, right={step_length_right_m:.4f}m"

        # Verify absolute values match manual arithmetic
        assert abs(step_length_left_m - 1.1333) < 0.001, \
            f"Expected ~1.13m (113.33px Ã— 0.01), got {step_length_left_m:.4f}m"
        assert abs(step_length_right_m - 2.55) < 0.001, \
            f"Expected 2.55m (255px Ã— 0.01), got {step_length_right_m:.4f}m"

    def test_step_length_left_dominant_gait(self):
        """Test where left foot dominates (takes longer steps)."""
        # Left foot takes longer steps
        heel_strikes_l_px = [300.0, 700.0, 1100.0]  # L advances by 400px each step
        heel_strikes_r_px = [100.0, 450.0, 800.0]   # R advances by 350px each step
        scale_m_per_px = 0.01

        step_length_left_m, step_length_right_m = compute_step_lengths_lr(
            heel_strikes_l_px, heel_strikes_r_px, scale_m_per_px
        )

        # step_length_left: Râ†’L
        # R1(100) â†’ L1(300) = 200px
        # R2(450) â†’ L2(700) = 250px
        # R3(800) â†’ L3(1100) = 300px
        # mean = (200 + 250 + 300) / 3 = 250px â†’ 2.5m

        # step_length_right: Lâ†’R
        # L1(300) â†’ R2(450) = 150px
        # L2(700) â†’ R3(800) = 100px
        # mean = (150 + 100) / 2 = 125px â†’ 1.25m

        expected_left = (200.0 + 250.0 + 300.0) / 3 * scale_m_per_px
        expected_right = (150.0 + 100.0) / 2 * scale_m_per_px

        assert abs(step_length_left_m - expected_left) < 0.001
        assert abs(step_length_right_m - expected_right) < 0.001
        assert step_length_left_m > step_length_right_m, "Left-dominant gait: left should be > right"

    def test_symmetric_gait_produces_equal_steps(self):
        """Test that truly symmetric heel-strike pattern produces equal step lengths."""
        # Perfect alternating pattern with equal spacing
        heel_strikes_l_px = [200.0, 600.0, 1000.0]  # L every 400px
        heel_strikes_r_px = [0.0, 400.0, 800.0]     # R every 400px, offset by 200px
        scale_m_per_px = 0.01

        step_length_left_m, step_length_right_m = compute_step_lengths_lr(
            heel_strikes_l_px, heel_strikes_r_px, scale_m_per_px
        )

        # step_length_left: Râ†’L
        # R1(0) â†’ L1(200) = 200px
        # R2(400) â†’ L2(600) = 200px
        # R3(800) â†’ L3(1000) = 200px
        # mean = 200px

        # step_length_right: Lâ†’R
        # L1(200) â†’ R2(400) = 200px
        # L2(600) â†’ R3(800) = 200px
        # mean = 200px

        expected = 200.0 * scale_m_per_px

        assert abs(step_length_left_m - expected) < 0.001
        assert abs(step_length_right_m - expected) < 0.001
        assert abs(step_length_left_m - step_length_right_m) < 0.001, \
            "Symmetric pattern should produce equal step lengths"

