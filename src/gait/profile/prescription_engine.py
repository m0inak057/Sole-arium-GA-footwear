"""PrescriptionEngine â€” rule-based orthotist/shoe-designer specification generator.

Reads the ``prescription_rules`` section from ``rules.yaml`` and applies them
in ascending priority order to the same ``rule_params`` dict that drives the
health recommendation engine.  Later (higher-priority) rules override scalar
fields; ``clinician_notes`` accumulates across all matching rules.

Body-mass Shore-C modifiers are applied on top of all rule-derived values:
  < 60 kg  â†’ subtract 5 from all Shore C values
  80â€“100 kg â†’ add 10
  > 100 kg  â†’ add 15 (+ PU midsole note)

Heel lift for step-length asymmetry > 10 % is computed directly from the
supplied ``step_length_left_m`` / ``step_length_right_m`` values.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# â”€â”€ Sensible defaults â€” produced when no rule matches at all â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_PRESCRIPTION_DEFAULTS: Dict[str, Any] = {
    "last_shape": "semi_curved",
    "toe_box": "standard",
    "heel_counter": "semi_rigid",
    "medial_post": False,
    "medial_post_shore_c": None,
    "medial_shore_c": 55.0,
    "lateral_shore_c": 55.0,
    "heel_drop_mm": 8.0,
    "arch_support_height_mm": 18.0,
    "arch_support_type": "contoured",
    "cushioning_priority": "heel",
    "outsole_base": "standard",
    "rocker_apex": None,
    "lateral_reinforcement": False,
    "upper_construction": "standard",
    "upper_material": "leather",
    "extra_depth": False,
}


# â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _match_condition(when: Dict[str, Any], params: Dict[str, Any]) -> bool:
    """Return True iff *all* conditions in ``when`` match the given params.

    Replicates the same semantics as ``rules_engine._match_condition``
    (AND logic) so the two engines are consistent.
    """
    for key, value in when.items():
        if key == "pronation":
            if params.get("pronation_type") != value:
                return False
        elif key == "arch":
            if params.get("arch_type") != value:
                return False
        elif key == "foot_strike":
            if params.get("foot_strike_type") != value:
                return False
        elif key == "flag":
            if value not in params.get("flags", []):
                return False
        elif key == "eversion_peak_early":
            if params.get("eversion_peak_early") != value:
                return False
        elif key == "age_years_below":
            age = params.get("age_years")
            if age is None or age >= value:
                return False
        else:
            if params.get(key) != value:
                return False
    return True


def _shore_c_modifier(body_mass_kg: float) -> float:
    """Return Shore-C delta to apply based on patient body mass."""
    if body_mass_kg < 60.0:
        return -5.0
    if body_mass_kg > 100.0:
        return 15.0
    if body_mass_kg >= 80.0:
        return 10.0
    return 0.0


def _clamp_shore_c(value: float) -> float:
    return max(25.0, min(95.0, value))


def _compute_heel_lift(
    rule_params: Dict[str, Any],
    step_length_left_m: float,
    step_length_right_m: float,
) -> tuple[float, float]:
    """Return (left_mm, right_mm) heel lift.

    3 mm is added to the *shorter* side when step asymmetry > 10 %.
    The asymmetric flag in rule_params is also respected so that tests
    can inject the flag directly without supplying numeric lengths.
    """
    flags: List[str] = rule_params.get("flags", [])
    flag_set = any("step_length_asymmetric" in f for f in flags)

    numeric_asymmetric = False
    if step_length_left_m > 0 and step_length_right_m > 0:
        mean = (step_length_left_m + step_length_right_m) / 2.0
        if mean > 0:
            pct = abs(step_length_left_m - step_length_right_m) / mean * 100.0
            numeric_asymmetric = pct > 10.0

    if not (flag_set or numeric_asymmetric):
        return 0.0, 0.0

    # Apply lift to the shorter side
    if step_length_left_m < step_length_right_m:
        return 3.0, 0.0
    if step_length_right_m < step_length_left_m:
        return 0.0, 3.0
    # Equal lengths but flag set â€” default to left
    return 3.0, 0.0


def _derive_primary_condition(rule_params: Dict[str, Any]) -> str:
    """Build a plain-English summary of the dominant biomechanical condition."""
    pronation = rule_params.get("pronation_type", "neutral")
    arch = rule_params.get("arch_type", "normal")
    foot_strike = rule_params.get("foot_strike_type", "rearfoot")
    flags: List[str] = rule_params.get("flags", [])

    parts: List[str] = []

    if pronation == "overpronation":
        if arch == "low":
            parts.append("severe bilateral overpronation with flat arch")
        else:
            parts.append("severe bilateral overpronation")
    elif pronation == "mild_pronation":
        parts.append("mild pronation")
    elif pronation == "oversupination":
        parts.append("oversupination")
    elif pronation == "mild_supination":
        parts.append("mild supination")
    elif arch == "low":
        parts.append("flat arch (rigid)")
    elif arch == "high":
        parts.append("high arch (pes cavus)")

    if arch == "high":
        parts = [p for p in parts if "flat arch" not in p]
        if "high arch (pes cavus)" not in parts:
            parts.append("high arch (pes cavus)")

    if foot_strike == "forefoot":
        parts.append("forefoot strike pattern")

    if any("step_length_asymmetric" in f for f in flags):
        parts.append("step length asymmetry")

    if not parts:
        return "Normal biomechanical profile"
    return ", ".join(parts).capitalize()


# â”€â”€ Engine â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class PrescriptionEngine:
    """Generate a :class:`~src.gait.profile.schema.PrescriptionSpec` from rules.

    Args:
        prescription_rules: Parsed prescription rules from ``rules.yaml``.
            Each rule is a dict with ``when``, ``then``, and ``priority`` keys.
    """

    def __init__(self, prescription_rules: List[Dict[str, Any]]) -> None:
        self._rules = sorted(prescription_rules, key=lambda r: r.get("priority", 0))

    def generate_prescription(
        self,
        rule_params: Dict[str, Any],
        body_mass_kg: float,
        step_length_left_m: float = 0.0,
        step_length_right_m: float = 0.0,
        patient_id: Optional[str] = None,
    ) -> "PrescriptionSpec":  # noqa: F821 â€” forward ref resolved at call time
        """Apply prescription rules and return a fully populated PrescriptionSpec.

        Args:
            rule_params:          Same flat dict used by the health rules engine
                                  (pronation_type, arch_type, foot_strike_type,
                                  flags, ...).
            body_mass_kg:         Patient body mass â€” used for Shore-C modifiers.
            step_length_left_m:   Mean left step length in metres.
            step_length_right_m:  Mean right step length in metres.
            patient_id:           Optional, for logging only.

        Returns:
            PrescriptionSpec populated from the best-matching rules cascade.
        """
        # Start from defaults; each matching rule (in priority order) overrides
        spec: Dict[str, Any] = dict(_PRESCRIPTION_DEFAULTS)
        clinician_notes: List[str] = []

        for rule in self._rules:
            when = rule.get("when", {})
            then = rule.get("then", {})
            if _match_condition(when, rule_params):
                for key, value in then.items():
                    if key == "clinician_notes":
                        if isinstance(value, list):
                            clinician_notes.extend(value)
                    else:
                        spec[key] = value

        # â”€â”€ Body-mass Shore-C modifier â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        modifier = _shore_c_modifier(body_mass_kg)
        if modifier != 0:
            spec["medial_shore_c"] = _clamp_shore_c(spec["medial_shore_c"] + modifier)
            spec["lateral_shore_c"] = _clamp_shore_c(spec["lateral_shore_c"] + modifier)
            if spec.get("medial_post") and spec.get("medial_post_shore_c") is not None:
                spec["medial_post_shore_c"] = _clamp_shore_c(
                    spec["medial_post_shore_c"] + modifier
                )
            if body_mass_kg > 100.0:
                note = "Consider PU midsole for durability at this body mass"
                if note not in clinician_notes:
                    clinician_notes.append(note)

        # â”€â”€ Heel lift from step asymmetry â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        heel_lift_l, heel_lift_r = _compute_heel_lift(
            rule_params, step_length_left_m, step_length_right_m
        )

        # â”€â”€ Assemble Pydantic models â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        from gait.profile.schema import (  # local import avoids circular dep
            ArchSupportSpec,
            FootLiftSpec,
            LastSpec,
            MidsoleSpec,
            OutsoleSpec,
            PrescriptionSpec,
            UpperSpec,
        )

        return PrescriptionSpec(
            last_spec=LastSpec(
                shape=spec["last_shape"],
                toe_box=spec["toe_box"],
                heel_counter=spec["heel_counter"],
            ),
            arch_support=ArchSupportSpec(
                height_mm=spec["arch_support_height_mm"],
                type=spec["arch_support_type"],
                medial_post=spec["medial_post"],
                medial_post_shore_c=(
                    spec["medial_post_shore_c"] if spec["medial_post"] else None
                ),
            ),
            midsole=MidsoleSpec(
                medial_shore_c=spec["medial_shore_c"],
                lateral_shore_c=spec["lateral_shore_c"],
                heel_drop_mm=spec["heel_drop_mm"],
                cushioning_priority=spec["cushioning_priority"],
            ),
            outsole=OutsoleSpec(
                base=spec["outsole_base"],
                rocker_apex_position=spec.get("rocker_apex"),
                lateral_reinforcement=spec["lateral_reinforcement"],
            ),
            upper=UpperSpec(
                construction=spec["upper_construction"],
                material=spec["upper_material"],
                closure="lace",
                extra_depth=spec["extra_depth"],
            ),
            foot_lift=FootLiftSpec(
                heel_lift_left_mm=heel_lift_l,
                heel_lift_right_mm=heel_lift_r,
            ),
            primary_condition_addressed=_derive_primary_condition(rule_params),
            clinician_referral_notes=clinician_notes,
            confidence="rule_based",
        )

