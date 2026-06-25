"""GaitAgent abstract base class — interface for all gait analysis agents."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class GaitAgent(ABC):
    """Abstract base for gait analysis agents.

    All agents follow the pattern: input → LLM/model → structured output → fallback.
    Subclasses must implement predict() which accepts domain-specific parameters
    and returns a tuple of (result, confidence_score, reasoning).
    """

    @abstractmethod
    def predict(self, params: Dict[str, Any]) -> tuple[Any, float, str]:
        """Run the agent on the given parameters.

        Returns:
            (result, confidence_score, reasoning_str)

        Confidence score: 0.0 = no confidence, 1.0 = perfect confidence.
        Reasoning: human-readable explanation of the decision.
        """
        pass

    @abstractmethod
    def validate(self, result: Any, params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate agent output against input parameters.

        Returns:
            (is_valid, error_message)

        If is_valid is False, error_message explains what's wrong (will be logged).
        """
        pass
