"""Synthetic data generators for testing without hardware.

Generates realistic synthetic gait data:
- Keypoint trajectories
- Video frames
- Complete profiles
- Gait cycles with known parameters
"""

from datetime import datetime
from typing import Dict, List

import numpy as np

from gait.common.interfaces import Frame, Keypoint, KeypointFrame, GaitCycle, GaitEvent
from gait.profile.schema import (
    GaitPatientProfile,
    Anthropometrics,
    Spatiotemporal,
    FootStrike,
    Pronation,
    Arch,
    HealthAssessment,
    DefectDetail,
    ImprovementAction,
    FootStrikePattern,
    PronationClassification,
    ArchType,
    LRPair,
)


class SyntheticGaitGenerator:
    """Generate realistic synthetic gait data for testing."""

    @staticmethod
    def generate_keypoint_trajectory(
        num_frames: int = 120,
        frequency_hz: float = 1.0,
        noise_std: float = 0.01,
    ) -> Dict[int, float]:
        """Generate synthetic 1D keypoint trajectory (e.g., heel height over time).

        Args:
            num_frames: Number of frames to generate.
            frequency_hz: Oscillation frequency (gait cycles per second).
            noise_std: Gaussian noise standard deviation.

        Returns:
            Dict mapping frame_index â†’ keypoint_value.
        """
        trajectory = {}
        t = np.linspace(0, num_frames / 120.0, num_frames)  # Assume 120 fps

        # Sinusoidal motion (mimics cyclic gait)
        signal = np.sin(2 * np.pi * frequency_hz * t) + np.cos(4 * np.pi * frequency_hz * t)

        # Add noise
        signal += np.random.normal(0, noise_std, num_frames)

        # Normalize to ~[0, 100] for pixel coordinates
        signal = (signal - signal.min()) / (signal.max() - signal.min()) * 100 + 50

        for i, val in enumerate(signal):
            trajectory[i] = float(val)

        return trajectory

    @staticmethod
    def generate_keypoint_frame(
        frame_idx: int,
        timestamp_ms: int,
        camera_view: str = "sagittal",
        confidence: float = 0.95,
    ) -> KeypointFrame:
        """Generate a frame with synthetic keypoints.

        Args:
            frame_idx: Frame index.
            timestamp_ms: Timestamp in milliseconds.
            camera_view: Camera view name.
            confidence: Keypoint confidence score.

        Returns:
            KeypointFrame with synthetic keypoints.
        """
        # Common keypoint names (subset of MediaPipe 33 landmarks)
        keypoint_names = [
            "nose", "left_eye", "right_eye",
            "left_shoulder", "right_shoulder",
            "left_hip", "right_hip",
            "left_knee", "right_knee",
            "left_ankle", "right_ankle",
            "left_heel", "right_heel",
            "left_foot_index", "right_foot_index",
        ]

        keypoints = {}
        for name in keypoint_names:
            # Generate random but realistic coordinates
            x = np.random.normal(250, 50)  # ~250px, Â±50px variance
            y = np.random.normal(200 + frame_idx % 50, 30)  # Motion over time
            z = np.random.normal(0, 10) if camera_view == "sagittal" else None

            keypoints[name] = Keypoint(
                x=float(max(0, x)),
                y=float(max(0, y)),
                z=float(z) if z is not None else None,
                confidence=float(np.random.normal(confidence, 0.05)),
                name=name,
            )

        return KeypointFrame(
            timestamp_ms=timestamp_ms,
            frame_index=frame_idx,
            camera_view=camera_view,
            keypoints=keypoints,
            confidence=float(confidence),
        )

    @staticmethod
    def generate_keypoint_frames(
        num_frames: int = 240,
        fps: int = 120,
        num_cameras: int = 2,
    ) -> List[KeypointFrame]:
        """Generate multiple frames with keypoints.

        Args:
            num_frames: Total frames to generate.
            fps: Frames per second.
            num_cameras: Number of camera views.

        Returns:
            List of KeypointFrame objects.
        """
        frames = []
        camera_views = ["sagittal", "posterior"][:num_cameras]

        for i in range(num_frames):
            timestamp_ms = int((i / fps) * 1000)
            for camera_view in camera_views:
                frame = SyntheticGaitGenerator.generate_keypoint_frame(
                    frame_idx=i,
                    timestamp_ms=timestamp_ms,
                    camera_view=camera_view,
                )
                frames.append(frame)

        return frames

    @staticmethod
    def generate_gait_cycle(
        cycle_id: int,
        foot: str,
        num_frames_in_cycle: int = 120,
        pronation_type: str = "neutral",
    ) -> GaitCycle:
        """Generate a synthetic gait cycle.

        Args:
            cycle_id: Cycle identifier.
            foot: 'L' or 'R'.
            num_frames_in_cycle: Frames in this cycle.
            pronation_type: 'neutral', 'overpronation', 'oversupination'.

        Returns:
            GaitCycle object.
        """
        frame_start = cycle_id * num_frames_in_cycle
        frame_end = frame_start + num_frames_in_cycle

        # Stance ~60%, swing ~40%
        stance_frames = list(range(frame_start, frame_start + int(num_frames_in_cycle * 0.6)))
        swing_frames = list(range(frame_start + int(num_frames_in_cycle * 0.6), frame_end))

        # Generate keypoints for each frame
        keypoints = {}
        for frame_idx in range(frame_start, frame_end):
            keypoints[frame_idx] = {
                name: Keypoint(
                    x=100 + np.sin(2 * np.pi * (frame_idx - frame_start) / num_frames_in_cycle) * 50,
                    y=200 + np.cos(2 * np.pi * (frame_idx - frame_start) / num_frames_in_cycle) * 30,
                    confidence=0.9,
                    name=name,
                )
                for name in ["heel", "ankle", "hip", "knee"]
            }

        return GaitCycle(
            cycle_id=cycle_id,
            foot=foot,
            frame_start=frame_start,
            frame_end=frame_end,
            stance_frames=stance_frames,
            swing_frames=swing_frames,
            keypoints=keypoints,
            confidence=0.85,
            stance_duration_ms=(int(num_frames_in_cycle * 0.6) / 120.0) * 1000,
            swing_duration_ms=(int(num_frames_in_cycle * 0.4) / 120.0) * 1000,
        )

    @staticmethod
    def generate_synthetic_profile(
        patient_id: str = "P_TEST_001",
        pronation_type: str = "neutral",
        foot_strike: str = "rearfoot",
        arch_type: str = "normal",
    ) -> GaitPatientProfile:
        """Generate a complete synthetic patient profile.

        Args:
            patient_id: Patient identifier.
            pronation_type: 'neutral', 'overpronation', 'oversupination'.
            foot_strike: 'rearfoot', 'midfoot', 'forefoot'.
            arch_type: 'high', 'normal', 'low'.

        Returns:
            GaitPatientProfile object.
        """
        # Synthesize parameters based on type
        if pronation_type == "overpronation":
            rearfoot_angle = 10.5
            pronation_class = PronationClassification.OVERPRONATION
        elif pronation_type == "neutral":
            rearfoot_angle = 2.5
            pronation_class = PronationClassification.NEUTRAL
        else:  # oversupination
            rearfoot_angle = -6.0
            pronation_class = PronationClassification.OVERSUPINATION

        if foot_strike == "rearfoot":
            fsa = 12.0
            strike_class = FootStrikePattern.REARFOOT
        elif foot_strike == "midfoot":
            fsa = 0.0
            strike_class = FootStrikePattern.MIDFOOT
        else:  # forefoot
            fsa = -8.0
            strike_class = FootStrikePattern.FOREFOOT

        if arch_type == "high":
            ahi = 0.32
            arch_class = ArchType.HIGH
        elif arch_type == "normal":
            ahi = 0.25
            arch_class = ArchType.NORMAL
        else:  # low
            ahi = 0.18
            arch_class = ArchType.LOW

        return GaitPatientProfile(
            schema_version="profile/v1",
            patient_id=patient_id,
            session_timestamp=datetime.utcnow(),
            anthropometrics=Anthropometrics(
                height_cm=172.0,
                mass_kg=72.0,
                foot_length_mm={"L": 258.0, "R": 260.0},
                foot_width_mm={"L": 98.0, "R": 99.0},
            ),
            spatiotemporal=Spatiotemporal(
                cadence_spm=112.0,
                speed_mps=1.28,
                stride_length_m=1.37,
                step_width_m=0.09,
                stance_pct={"L": 61.2, "R": 60.4},
                double_support_pct=22.1,
            ),
            foot_strike=FootStrike(
                pattern={"L": strike_class, "R": strike_class},
                foot_strike_angle_deg={"L": fsa, "R": fsa},
            ),
            pronation=Pronation(
                rearfoot_angle_at_midstance_deg={"L": rearfoot_angle, "R": rearfoot_angle},
                classification={"L": pronation_class, "R": pronation_class},
                time_to_peak_eversion_pct_stance={"L": 38.0, "R": 42.0},
            ),
            arch=Arch(
                type={"L": arch_class, "R": arch_class},
                arch_height_index=LRPair(L=ahi, R=ahi),
            ),
            symmetry_flags=[],
            health_assessment=HealthAssessment(
                what_went_right=["Gait cycle detected successfully"] if pronation_type == "neutral" else [],
                defects_found=[
                    DefectDetail(
                        name="Overpronation" if pronation_type == "overpronation" else "Supination",
                        severity="moderate",
                        affected_side="bilateral",
                        biomechanical_cause="Rearfoot eversion pattern detected",
                        gait_cycle_phase="Loading Response to Mid-Stance",
                    )
                ] if pronation_type in ("overpronation", "oversupination") else [],
                improvement_plan=[],
            ),
            confidence_scores={
                "pronation_classification": 0.91,
                "foot_strike_classification": 0.95,
                "arch_classification": 0.88,
            },
            needs_human_review=False,
        )


# Convenience fixtures for common test cases
def synthetic_frames_normal_gait():
    """Generate frames for normal/neutral gait."""
    return SyntheticGaitGenerator.generate_keypoint_frames(num_frames=240)


def synthetic_profile_neutral():
    """Generate profile for neutral gait."""
    return SyntheticGaitGenerator.generate_synthetic_profile(
        pronation_type="neutral",
        foot_strike="rearfoot",
        arch_type="normal",
    )


def synthetic_profile_overpronation():
    """Generate profile for overpronation."""
    return SyntheticGaitGenerator.generate_synthetic_profile(
        pronation_type="overpronation",
        foot_strike="rearfoot",
        arch_type="low",
    )

