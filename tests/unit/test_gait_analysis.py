"""Unit tests for gait analysis (Phase B)."""
from __future__ import annotations

import numpy as np
import pytest

from gait.events.gait_event_detector import GaitEvent, GaitEventDetector
from gait.analysis.biomechanics import BiomechanicsAnalyzer


class TestGaitEventDetector:
    """Tests for gait event detection."""

    @pytest.fixture
    def detector(self):
        """Create gait event detector."""
        return GaitEventDetector(fps=120.0)

    def test_detector_initialization(self, detector):
        """Test detector creation."""
        assert detector.fps == 120.0
        assert detector.filter_order == 4

    def test_detect_heel_strikes_synthetic(self, detector):
        """Test heel strike detection on synthetic data."""
        # Synthetic heel trajectory: sinusoidal with clear minima
        t = np.linspace(0, 2, 240)  # 2 seconds at 120 fps
        heel_y = 0.5 + 0.3 * np.sin(2 * np.pi * t)  # ~1 Hz oscillation
        timestamps = t * 1000  # Convert to ms

        events = detector.detect_heel_strikes(heel_y, timestamps)

        # Should detect ~2 heel strikes in 2 seconds at 1 Hz
        assert len(events) >= 1
        assert all(e.event_type == "heel_strike" for e in events)
        assert all(0 <= e.confidence <= 1.0 for e in events)

    def test_detect_heel_strikes_insufficient_frames(self, detector):
        """Test detection with too few frames."""
        heel_y = np.array([0.5, 0.6])
        timestamps = np.array([0, 8.3])  # 2 frames

        events = detector.detect_heel_strikes(heel_y, timestamps)
        assert len(events) == 0

    def test_detect_toe_offs_synthetic(self, detector):
        """Test toe-off detection on synthetic data."""
        t = np.linspace(0, 2, 240)
        toe_y = 0.5 + 0.2 * np.sin(2 * np.pi * t + np.pi / 2)
        heel_y = 0.5 + 0.3 * np.sin(2 * np.pi * t)
        timestamps = t * 1000

        events = detector.detect_toe_offs(toe_y, heel_y, timestamps)

        # Should detect toe-offs
        assert isinstance(events, list)
        assert all(e.event_type == "toe_off" for e in events)

    def test_gait_event_dataclass(self):
        """Test GaitEvent dataclass."""
        event = GaitEvent(
            frame_index=100,
            timestamp_ms=833.3,
            event_type="heel_strike",
            confidence=0.85,
        )
        assert event.frame_index == 100
        assert event.event_type == "heel_strike"
        assert 0 <= event.confidence <= 1.0


class TestBiomechanicsAnalyzer:
    """Tests for biomechanical analysis."""

    @pytest.fixture
    def analyzer(self):
        """Create biomechanics analyzer."""
        return BiomechanicsAnalyzer(fps=120.0, height_m=1.75)

    def test_analyzer_initialization(self, analyzer):
        """Test analyzer creation."""
        assert analyzer.fps == 120.0
        assert analyzer.height_m == 1.75

    def test_compute_spatiotemporal_basic(self, analyzer):
        """Test spatiotemporal parameter computation."""
        # Simulate heel strikes at 1 Hz (120 frames apart)
        heel_strikes = [100, 220, 340]  # ~1 step per second
        cycle_duration = 240  # 2 seconds at 120 fps

        params = analyzer.compute_spatiotemporal(
            heel_strikes=heel_strikes,
            cycle_duration_frames=cycle_duration,
            frame_width=640,
        )

        assert params.cadence_spm > 0
        assert params.speed_ms >= 0
        assert params.stride_length_m > 0
        assert params.stance_time_pct > 0

    def test_compute_spatiotemporal_single_strike(self, analyzer):
        """Test with single heel strike."""
        heel_strikes = [100]

        params = analyzer.compute_spatiotemporal(
            heel_strikes=heel_strikes,
            cycle_duration_frames=240,
            frame_width=640,
        )

        # Should return valid but default values
        assert params.cadence_spm == 0.0
        assert params.stride_length_m > 0  # Based on height

    def test_compute_pronation_synthetic(self, analyzer):
        """Test pronation angle computation."""
        # Synthetic ankle and heel positions
        n_frames = 100
        ankle_pos = np.column_stack([
            np.linspace(100, 110, n_frames),  # x changes slightly
            np.linspace(200, 220, n_frames),  # y changes
        ])
        heel_pos = np.column_stack([
            np.linspace(90, 100, n_frames),
            np.linspace(250, 270, n_frames),
        ])
        achilles_pos = np.linspace(150, 160, n_frames)

        angle = analyzer.compute_pronation(ankle_pos, heel_pos, achilles_pos)

        # Should be in valid range
        assert -10 <= angle <= 10

    def test_compute_pronation_empty(self, analyzer):
        """Test pronation with empty data."""
        ankle_pos = np.array([]).reshape(0, 2)
        heel_pos = np.array([]).reshape(0, 2)
        achilles_pos = np.array([])

        angle = analyzer.compute_pronation(ankle_pos, heel_pos, achilles_pos)
        assert angle == 0.0


class TestGaitAnalysisIntegration:
    """Integration tests for gait analysis pipeline."""

    def test_event_detection_to_analysis(self):
        """Test full pipeline: event detection â†’ analysis."""
        detector = GaitEventDetector(fps=120.0)
        analyzer = BiomechanicsAnalyzer(fps=120.0, height_m=1.75)

        # Synthetic gait data: 60 seconds at 120 fps = 7200 frames
        t = np.linspace(0, 60, 7200)
        heel_y = 0.5 + 0.3 * np.sin(2 * np.pi * t)  # ~1 Hz
        timestamps = t * 1000

        # Detect events
        events = detector.detect_heel_strikes(heel_y, timestamps)

        # Extract heel strike frames
        heel_strikes = [int(e.frame_index) for e in events]

        # Compute parameters
        if len(heel_strikes) >= 2:
            cycle_frames = heel_strikes[1] - heel_strikes[0]
            params = analyzer.compute_spatiotemporal(
                heel_strikes=heel_strikes,
                cycle_duration_frames=cycle_frames,
                frame_width=640,
            )

            # Validate output
            assert params.cadence_spm > 0
            assert params.stride_length_m > 0

    def test_multiple_gait_cycles(self):
        """Test analysis over multiple gait cycles."""
        detector = GaitEventDetector(fps=120.0)
        analyzer = BiomechanicsAnalyzer(fps=120.0, height_m=1.70)

        # 3 gait cycles (3 seconds at ~1 Hz)
        t = np.linspace(0, 3, 360)
        heel_y = 0.5 + 0.25 * np.cos(2 * np.pi * t)
        timestamps = t * 1000

        events = detector.detect_heel_strikes(heel_y, timestamps)
        assert len(events) >= 2  # At least 2-3 cycles

