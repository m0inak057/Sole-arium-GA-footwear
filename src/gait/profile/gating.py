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
    biomechanical averages. Passes with fewer than three cycles would
    previously be dropped entirely (every cycle in such a pass is a boundary
    cycle) — but for short/low-quality recordings that is the *only* data
    available. Such passes are now kept in full, with their cycles marked
    down to a low confidence, rather than discarded — a best-effort result
    beats no result.

    Args:
        cycles: GaitCycle objects with ``pass_id`` already assigned by
                ``assign_pass_ids()``.

    Returns:
        The subset of cycles that are not boundary cycles (plus any
        low-confidence short passes kept in full), sorted by frame_start
        within each pass.
    """
    if not cycles:
        return cycles

    pass_groups: Dict[int, List[GaitCycle]] = defaultdict(list)
    for cycle in cycles:
        pass_groups[cycle.pass_id].append(cycle)

    kept: List[GaitCycle] = []
    discarded = 0
    short_passes_kept = 0
    for pass_id in sorted(pass_groups):
        pass_cycles = sorted(pass_groups[pass_id], key=lambda c: c.frame_start)
        if len(pass_cycles) <= 2:
            # Too few cycles to safely discard boundaries. Keep them all,
            # capping confidence since none of them are steady-state cycles.
            for c in pass_cycles:
                c.confidence = min(c.confidence, 0.4)
            kept.extend(pass_cycles)
            short_passes_kept += len(pass_cycles)
            continue
        inner = pass_cycles[1:-1]
        kept.extend(inner)
        discarded += len(pass_cycles) - len(inner)

    logger.info(
        "boundary_cycles.discarded",
        extra={
            "n_passes": len(pass_groups),
            "cycles_kept": len(kept),
            "cycles_discarded": discarded,
            "short_passes_kept_low_confidence": short_passes_kept,
        },
    )
    return kept

