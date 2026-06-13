"""Gait event detection modules."""
from src.gait.events.velocity_detector import (
    VelocityBasedEventDetector,
    create_event_detector,
)

__all__ = [
    "VelocityBasedEventDetector",
    "create_event_detector",
]
