"""StandardGatingEngine â€” quality gating based on clean gait cycle count."""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

from gait.common.interfaces import GaitCycle, GatingEngine
from gait.common.logging_utils import get_logger
from gait.pipeline.config import AnalysisConfig

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


def discard_boundary_cycles(cycles: List[GaitCycle]) -> List[GaitCycle]:
    """Remove the first and last cycle of every walking pass.

    Boundary cycles are contaminated by gait initiation/termination and
    direction-change artefacts; discarding them produces cleaner steady-state
    biomechanical averages.  Passes with fewer than three cycles are dropped
    entirely because every cycle in such a pass is a boundary cycle.

    Args:
        cycles: GaitCycle objects with ``pass_id`` already assigned by
                ``assign_pass_ids()``.

    Returns:
        The subset of cycles that are not boundary cycles, sorted by
        frame_start within each pass.
    """
    if not cycles:
        return cycles

    pass_groups: Dict[int, List[GaitCycle]] = defaultdict(list)
    for cycle in cycles:
        pass_groups[cycle.pass_id].append(cycle)

    kept: List[GaitCycle] = []
    discarded = 0
    for pass_id in sorted(pass_groups):
        pass_cycles = sorted(pass_groups[pass_id], key=lambda c: c.frame_start)
        inner = pass_cycles[1:-1]  # empty when len <= 2
        kept.extend(inner)
        discarded += len(pass_cycles) - len(inner)

    logger.info(
        "boundary_cycles.discarded",
        extra={
            "n_passes": len(pass_groups),
            "cycles_kept": len(kept),
            "cycles_discarded": discarded,
        },
    )
    return kept

