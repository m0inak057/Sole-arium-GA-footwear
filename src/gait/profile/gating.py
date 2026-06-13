"""StandardGatingEngine — quality gating based on clean gait cycle count."""
from __future__ import annotations

from typing import List, Tuple

from src.gait.common.interfaces import GaitCycle, GatingEngine
from src.gait.common.logging_utils import get_logger
from src.gait.pipeline.config import AnalysisConfig

logger = get_logger(__name__)


class StandardGatingEngine(GatingEngine):
    """Quality gate based on number of clean gait cycles.

    Returns (True, 'PROCEED_OK') when cycles >= target.
    Returns (True, 'PROCEED_WITH_WARNING') when cycles >= min.
    Returns (False, 'RERECORD') when cycles < min.
    """

    def __init__(self, config: AnalysisConfig) -> None:
        self._cfg = config

    def check_gait_quality(self, cycles: List[GaitCycle]) -> Tuple[bool, str]:
        n = len(cycles)
        if n >= self._cfg.target_clean_cycles_per_foot:
            logger.info("gating.result", extra={"result": "PROCEED_OK", "n_cycles": n})
            return True, "PROCEED_OK"
        if n >= self._cfg.min_clean_cycles_per_foot:
            logger.warning(
                "gating.result", extra={"result": "PROCEED_WITH_WARNING", "n_cycles": n}
            )
            return True, "PROCEED_WITH_WARNING"
        logger.warning("gating.result", extra={"result": "RERECORD", "n_cycles": n})
        return False, "RERECORD"


def create_gating_engine(config: AnalysisConfig) -> StandardGatingEngine:
    """Factory: return a StandardGatingEngine."""
    return StandardGatingEngine(config)
