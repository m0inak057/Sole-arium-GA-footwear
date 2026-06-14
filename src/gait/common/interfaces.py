"""Abstract interfaces for pipeline components.

Defines the contracts that each stage of the pipeline must implement.
Allows flexible implementations (mock, real hardware, different models).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Generator, Optional, Tuple

import numpy as np


@dataclass
class Frame:
    """Represents a single video frame."""

    image: np.ndarray  # Shape: (H, W, 3) for RGB or (H, W, 1) for grayscale
    timestamp_ms: int  # Frame timestamp in milliseconds
    camera_view: str  # 'sagittal', 'posterior', 'plantar', etc.
    frame_index: int = 0  # Frame number in sequence
    confidence: Optional[float] = None  # Optional: frame quality confidence


@dataclass
class Keypoint:
    """A single 2D or 3D keypoint."""

    x: float
    y: float
    z: Optional[float] = None  # 3D coordinate (optional)
    confidence: float = 1.0  # 0-1 confidence score
    name: Optional[str] = None  # Keypoint name (e.g., 'ankle', 'heel')


@dataclass
class KeypointFrame:
    """Frame with detected keypoints."""

    timestamp_ms: int
    frame_index: int
    camera_view: str
    keypoints: Dict[str, Keypoint]  # name → Keypoint
    confidence: float  # Minimum confidence of all keypoints in frame


@dataclass
class GaitEvent:
    """Represents a gait event (heel-strike, toe-off, etc.)."""

    event_type: str  # 'heel_strike', 'toe_off', etc.
    frame_index: int
    timestamp_ms: int
    foot: str  # 'L' or 'R'
    confidence: float = 1.0


@dataclass
class GaitCycle:
    """A complete gait cycle (HS to next HS on same foot)."""

    cycle_id: int
    foot: str  # 'L' or 'R'
    frame_start: int
    frame_end: int
    stance_frames: list[int]
    swing_frames: list[int]
    keypoints: Dict[int, Dict[str, Keypoint]]  # frame_idx → keypoints
    confidence: float  # Minimum confidence in cycle
    stance_duration_ms: Optional[float] = None
    swing_duration_ms: Optional[float] = None
    pass_id: int = 0  # Walking-pass index assigned by assign_pass_ids()


class VideoSource(ABC):
    """Abstract interface for video input.

    Implementations can be:
    - File-based: MP4, AVI, etc.
    - Hardware: Live camera feed
    - Stream: Network stream
    - Synthetic: Generated for testing
    """

    @abstractmethod
    def open(self) -> None:
        """Open/connect to video source."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close/disconnect from video source."""
        pass

    @abstractmethod
    def get_frames(self) -> Generator[Frame, None, None]:
        """Yield frames from source.

        Yields:
            Frame objects with image, timestamp, camera_view.
        """
        pass

    @abstractmethod
    def get_frame_count(self) -> int:
        """Get total frame count (-1 if unknown)."""
        pass

    @abstractmethod
    def get_fps(self) -> float:
        """Get frames per second."""
        pass

    @abstractmethod
    def get_resolution(self) -> Tuple[int, int]:
        """Get (width, height) resolution."""
        pass


class PoseDetector(ABC):
    """Abstract interface for pose detection.

    Implementations: MediaPipe, OpenPose, custom fine-tuned models, etc.
    """

    @abstractmethod
    def detect(self, frame: Frame) -> KeypointFrame:
        """Detect pose keypoints in frame.

        Args:
            frame: Input frame.

        Returns:
            KeypointFrame with detected keypoints and confidence.
        """
        pass

    @abstractmethod
    def batch_detect(self, frames: list[Frame]) -> list[KeypointFrame]:
        """Detect pose in multiple frames (for efficiency).

        Args:
            frames: List of frames.

        Returns:
            List of KeypointFrame objects.
        """
        pass


class KeypointSmoother(ABC):
    """Abstract interface for keypoint smoothing/filtering."""

    @abstractmethod
    def smooth(self, trajectory: Dict[int, float]) -> Dict[int, float]:
        """Smooth a keypoint trajectory.

        Args:
            trajectory: Dict mapping frame_index → value.

        Returns:
            Smoothed trajectory (same keys, smoothed values).
        """
        pass

    @abstractmethod
    def smooth_frame(
        self, keypoint_frames: list[KeypointFrame]
    ) -> list[KeypointFrame]:
        """Smooth keypoints across a sequence of frames.

        Args:
            keypoint_frames: List of KeypointFrame objects.

        Returns:
            List of KeypointFrame with smoothed keypoint coordinates.
        """
        pass


class EventDetector(ABC):
    """Abstract interface for gait event detection."""

    @abstractmethod
    def detect_heel_strikes(
        self, keypoint_frames: list[KeypointFrame], foot: str
    ) -> list[GaitEvent]:
        """Detect heel-strike events.

        Args:
            keypoint_frames: List of keypoint frames.
            foot: 'L' or 'R'.

        Returns:
            List of GaitEvent objects with event_type='heel_strike'.
        """
        pass

    @abstractmethod
    def detect_toe_offs(
        self, keypoint_frames: list[KeypointFrame], foot: str
    ) -> list[GaitEvent]:
        """Detect toe-off events.

        Args:
            keypoint_frames: List of keypoint frames.
            foot: 'L' or 'R'.

        Returns:
            List of GaitEvent objects with event_type='toe_off'.
        """
        pass

    @abstractmethod
    def segment_gait_cycles(
        self,
        keypoint_frames: list[KeypointFrame],
        heel_strikes: list[GaitEvent],
        toe_offs: list[GaitEvent],
        foot: str,
    ) -> list[GaitCycle]:
        """Segment gait cycles from detected events.

        Args:
            keypoint_frames: List of keypoint frames.
            heel_strikes: List of heel-strike events.
            toe_offs: List of toe-off events.
            foot: 'L' or 'R'.

        Returns:
            List of GaitCycle objects.
        """
        pass


class BiomechanicalAnalyzer(ABC):
    """Abstract interface for biomechanical analysis."""

    @abstractmethod
    def compute_parameters(self, cycle: GaitCycle) -> Dict[str, Any]:
        """Compute biomechanical parameters for a gait cycle.

        Args:
            cycle: GaitCycle object.

        Returns:
            Dict of computed parameters (cadence, speed, angles, etc.).
        """
        pass

    @abstractmethod
    def aggregate_parameters(
        self, cycles: list[GaitCycle], foot: str
    ) -> Dict[str, Any]:
        """Aggregate parameters across cycles (mean, SD, etc.).

        Args:
            cycles: List of GaitCycle objects.
            foot: 'L' or 'R'.

        Returns:
            Aggregated parameters dict.
        """
        pass


class ProfileBuilder(ABC):
    """Abstract interface for building patient profiles."""

    @abstractmethod
    def build(
        self,
        patient_id: str,
        session_timestamp: str,
        parameters: Dict[str, Any],
        anthropometrics: Dict[str, Any],
        confidence_scores: Dict[str, float],
    ) -> Dict[str, Any]:
        """Build a patient profile JSON.

        Args:
            patient_id: Patient identifier.
            session_timestamp: ISO 8601 timestamp.
            parameters: Computed biomechanical parameters.
            anthropometrics: Patient measurements.
            confidence_scores: Confidence scores for classifications.

        Returns:
            Patient profile dict (matches schema).
        """
        pass

    @abstractmethod
    def validate(self, profile: Dict[str, Any]) -> Tuple[bool, list[str]]:
        """Validate profile against schema.

        Args:
            profile: Profile dict.

        Returns:
            (is_valid, list_of_errors).
        """
        pass


class GatingEngine(ABC):
    """Abstract interface for quality gating logic."""

    @abstractmethod
    def check_gait_quality(self, cycles: list[GaitCycle]) -> Tuple[bool, str]:
        """Check whether gait quality is sufficient.

        Args:
            cycles: List of gait cycles.

        Returns:
            (is_acceptable, reason). reason in:
            - 'PROCEED_OK' (≥ 8 clean cycles)
            - 'PROCEED_WITH_WARNING' (4-7 clean cycles)
            - 'RERECORD' (< 4 clean cycles)
        """
        pass


class RecommendationEngine(ABC):
    """Abstract interface for shoe design recommendations."""

    @abstractmethod
    def generate_recommendations(
        self, parameters: Dict[str, Any], patient_id: str = None
    ) -> Dict[str, Any]:
        """Generate shoe design recommendations.

        Args:
            parameters: Biomechanical parameters dict.
            patient_id: Optional patient ID (for auditing).

        Returns:
            Recommendations dict (matches schema).
        """
        pass

    @abstractmethod
    def apply_rule(
        self,
        rule_id: str,
        condition: Dict[str, Any],
        action: Dict[str, Any],
        current_recommendations: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Apply a single recommendation rule.

        Args:
            rule_id: Rule identifier.
            condition: Rule condition dict.
            action: Rule action dict.
            current_recommendations: Recommendations before this rule.

        Returns:
            Updated recommendations dict.
        """
        pass
