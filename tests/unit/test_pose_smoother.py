"""Unit tests for OneEuroSmoother (src.gait.pose.smoother)."""
from __future__ import annotations

import math
from typing import Dict

import numpy as np
import pytest

from gait.common.interfaces import Keypoint, KeypointFrame
from gait.pose.smoother import OneEuroSmoother, _OneEuroFilter

# â”€â”€ helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

FPS = 120.0


def make_kf(idx: int, keypoints: dict, cam: str = "sagittal") -> KeypointFrame:
    confs = [kp.confidence for kp in keypoints.values()]
    return KeypointFrame(
        timestamp_ms=idx * 8,
        frame_index=idx,
        camera_view=cam,
        keypoints=keypoints,
        confidence=min(confs) if confs else 0.0,
    )


def make_kp(x: float, y: float, z: float | None = None, name: str = "left_ankle") -> Keypoint:
    return Keypoint(x=x, y=y, z=z, confidence=0.9, name=name)


def constant_traj(value: float, n: int = 30) -> Dict[int, float]:
    return {i: value for i in range(n)}


def noisy_traj(base: float, amplitude: float = 10.0, n: int = 60) -> Dict[int, float]:
    rng = np.random.default_rng(42)
    noise = rng.normal(0, amplitude, n)
    return {i: base + noise[i] for i in range(n)}


# â”€â”€ _OneEuroFilter (private, tested for correctness) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestOneEuroFilterInternal:
    def test_first_sample_returned_unchanged(self):
        f = _OneEuroFilter(FPS)
        assert f(100.0) == pytest.approx(100.0)

    def test_constant_signal_passes_through(self):
        f = _OneEuroFilter(FPS)
        for _ in range(100):
            out = f(5.0)
        # After many identical samples the filter converges to the true value
        assert out == pytest.approx(5.0, abs=0.01)

    def test_output_stays_within_input_range(self):
        f = _OneEuroFilter(FPS, min_cutoff=1.0, beta=0.0)
        samples = list(range(50))
        outputs = [f(float(s)) for s in samples]
        assert all(0.0 <= o <= 50.0 for o in outputs)

    def test_high_cutoff_approximates_passthrough(self):
        # min_cutoff=1000 Hz â†’ alpha â‰ˆ 0.98; after ~10 identical samples it converges.
        f = _OneEuroFilter(FPS, min_cutoff=1000.0)
        x = 42.0
        for _ in range(10):
            out = f(x)
        assert abs(out - x) < 0.01


# â”€â”€ OneEuroSmoother.smooth â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestSmoothMethod:
    def test_empty_trajectory_returns_empty(self):
        s = OneEuroSmoother(fps=FPS)
        assert s.smooth({}) == {}

    def test_same_keys_preserved(self):
        s = OneEuroSmoother(fps=FPS)
        traj = {0: 1.0, 5: 2.0, 10: 3.0}
        result = s.smooth(traj)
        assert set(result.keys()) == {0, 5, 10}

    def test_single_sample_returned_unchanged(self):
        s = OneEuroSmoother(fps=FPS)
        result = s.smooth({7: 42.0})
        assert result[7] == pytest.approx(42.0)

    def test_constant_trajectory_preserved(self):
        s = OneEuroSmoother(fps=FPS, smoothing_window=5)
        traj = constant_traj(100.0, n=50)
        result = s.smooth(traj)
        # After convergence the output should match the constant
        last_idx = max(traj)
        assert result[last_idx] == pytest.approx(100.0, abs=0.5)

    def test_noisy_trajectory_variance_reduced(self):
        s = OneEuroSmoother(fps=FPS, smoothing_window=5)
        traj = noisy_traj(base=50.0, amplitude=15.0, n=120)
        result = s.smooth(traj)
        raw_var = np.var(list(traj.values()))
        smoothed_var = np.var(list(result.values()))
        assert smoothed_var < raw_var

    def test_output_values_are_floats(self):
        s = OneEuroSmoother(fps=FPS)
        result = s.smooth({i: float(i) for i in range(10)})
        assert all(isinstance(v, float) for v in result.values())

    def test_larger_window_more_smoothing(self):
        traj = noisy_traj(base=0.0, amplitude=20.0, n=120)
        s_tight = OneEuroSmoother(fps=FPS, smoothing_window=1)
        s_smooth = OneEuroSmoother(fps=FPS, smoothing_window=20)
        var_tight = np.var(list(s_tight.smooth(traj).values()))
        var_smooth = np.var(list(s_smooth.smooth(traj).values()))
        assert var_smooth < var_tight


# â”€â”€ OneEuroSmoother.smooth_frame â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestSmoothFrameMethod:
    def test_empty_list_returns_empty(self):
        s = OneEuroSmoother(fps=FPS)
        assert s.smooth_frame([]) == []

    def test_output_length_matches_input(self):
        s = OneEuroSmoother(fps=FPS)
        frames = [
            make_kf(i, {"left_ankle": make_kp(float(i), float(i))})
            for i in range(10)
        ]
        result = s.smooth_frame(frames)
        assert len(result) == 10

    def test_all_outputs_are_keypoint_frames(self):
        s = OneEuroSmoother(fps=FPS)
        frames = [make_kf(i, {"left_ankle": make_kp(1.0, 2.0)}) for i in range(5)]
        result = s.smooth_frame(frames)
        assert all(isinstance(kf, KeypointFrame) for kf in result)

    def test_metadata_preserved(self):
        s = OneEuroSmoother(fps=FPS)
        frames = [make_kf(i, {"left_ankle": make_kp(1.0, 2.0)}, cam="posterior") for i in range(3)]
        result = s.smooth_frame(frames)
        for orig, out in zip(frames, result):
            assert out.frame_index == orig.frame_index
            assert out.timestamp_ms == orig.timestamp_ms
            assert out.camera_view == orig.camera_view

    def test_keypoint_names_preserved(self):
        s = OneEuroSmoother(fps=FPS)
        kps = {
            "left_ankle": make_kp(1.0, 2.0, name="left_ankle"),
            "right_ankle": make_kp(3.0, 4.0, name="right_ankle"),
        }
        frames = [make_kf(i, kps) for i in range(5)]
        result = s.smooth_frame(frames)
        assert set(result[0].keypoints.keys()) == {"left_ankle", "right_ankle"}

    def test_confidence_preserved(self):
        s = OneEuroSmoother(fps=FPS)
        kp = Keypoint(x=1.0, y=2.0, confidence=0.75, name="left_ankle")
        frames = [make_kf(i, {"left_ankle": kp}) for i in range(5)]
        result = s.smooth_frame(frames)
        assert all(kf.keypoints["left_ankle"].confidence == pytest.approx(0.75) for kf in result)

    def test_z_none_preserved(self):
        s = OneEuroSmoother(fps=FPS)
        kp = make_kp(1.0, 2.0, z=None)
        frames = [make_kf(i, {"left_ankle": kp}) for i in range(5)]
        result = s.smooth_frame(frames)
        assert all(kf.keypoints["left_ankle"].z is None for kf in result)

    def test_z_smoothed_when_present(self):
        s = OneEuroSmoother(fps=FPS, smoothing_window=5)
        # Noisy z values
        frames = [
            make_kf(i, {"left_ankle": make_kp(1.0, 2.0, z=float(i) + (i % 2) * 20.0)})
            for i in range(20)
        ]
        result = s.smooth_frame(frames)
        raw_z = [frames[i].keypoints["left_ankle"].z for i in range(20)]
        out_z = [result[i].keypoints["left_ankle"].z for i in range(20)]
        assert np.var(out_z) < np.var(raw_z)

    def test_absent_keypoints_stay_absent(self):
        """Keypoint present in frame 0 but not frame 1 must stay absent in smoothed frame 1."""
        s = OneEuroSmoother(fps=FPS)
        frames = [
            make_kf(0, {"left_ankle": make_kp(1.0, 2.0), "right_ankle": make_kp(3.0, 4.0)}),
            make_kf(1, {"left_ankle": make_kp(1.1, 2.1)}),  # right_ankle absent
        ]
        result = s.smooth_frame(frames)
        assert "right_ankle" not in result[1].keypoints

    def test_xy_smoothed_not_identical_to_noisy_input(self):
        s = OneEuroSmoother(fps=FPS, smoothing_window=10)
        rng = np.random.default_rng(0)
        frames = [
            make_kf(i, {"left_ankle": make_kp(
                x=50.0 + rng.normal(0, 10.0),
                y=100.0 + rng.normal(0, 10.0),
            )})
            for i in range(60)
        ]
        result = s.smooth_frame(frames)
        in_x = [f.keypoints["left_ankle"].x for f in frames]
        out_x = [f.keypoints["left_ankle"].x for f in result]
        assert not np.allclose(in_x, out_x)  # smoothing changed the values
        assert np.var(out_x) < np.var(in_x)  # variance reduced

