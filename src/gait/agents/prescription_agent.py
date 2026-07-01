"""PrescriptionAgent â€” Claude-powered orthotist specification refinement.

Takes the rule-based PrescriptionSpec and asks Claude Opus 4.8 (streaming +
adaptive thinking) to refine it given the full biomechanical picture.
On any failure the original rule-based spec is returned unchanged.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

import anthropic

from gait.common.logging_utils import get_logger

logger = get_logger(__name__)

_MODEL = "claude-opus-4-8"

# Fields Claude may override (all scalar; nested dicts handled separately)
_OVERRIDE_FIELDS = {
    "last_spec",
    "arch_support",
    "midsole",
    "outsole",
    "upper",
    "foot_lift",
    "primary_condition_addressed",
    "clinician_referral_notes",
}

_PRESCRIPTION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "last_spec": {
            "type": "object",
            "properties": {
                "shape": {"type": "string", "enum": ["straight", "semi_curved", "curved"]},
                "toe_box": {"type": "string", "enum": ["standard", "wide", "extra_wide", "deep"]},
                "heel_counter": {"type": "string", "enum": ["rigid", "semi_rigid", "flexible"]},
            },
            "required": ["shape", "toe_box", "heel_counter"],
            "additionalProperties": False,
        },
        "arch_support": {
            "type": "object",
            "properties": {
                "height_mm": {"type": "number"},
                "type": {"type": "string", "enum": ["contoured", "flat", "accommodative"]},
                "medial_post": {"type": "boolean"},
                "medial_post_shore_c": {"type": ["number", "null"]},
            },
            "required": ["height_mm", "type", "medial_post", "medial_post_shore_c"],
            "additionalProperties": False,
        },
        "midsole": {
            "type": "object",
            "properties": {
                "medial_shore_c": {"type": "number"},
                "lateral_shore_c": {"type": "number"},
                "heel_drop_mm": {"type": "number"},
                "cushioning_priority": {
                    "type": "string",
                    "enum": ["heel", "forefoot", "full_length", "lateral"],
                },
            },
            "required": ["medial_shore_c", "lateral_shore_c", "heel_drop_mm", "cushioning_priority"],
            "additionalProperties": False,
        },
        "outsole": {
            "type": "object",
            "properties": {
                "base": {"type": "string", "enum": ["standard", "flared", "rocker"]},
                "rocker_apex_position": {"type": ["string", "null"]},
                "lateral_reinforcement": {"type": "boolean"},
            },
            "required": ["base", "rocker_apex_position", "lateral_reinforcement"],
            "additionalProperties": False,
        },
        "upper": {
            "type": "object",
            "properties": {
                "construction": {"type": "string", "enum": ["standard", "seamless", "minimal_seam"]},
                "material": {"type": "string", "enum": ["leather", "neoprene", "mesh"]},
                "closure": {"type": "string", "enum": ["lace", "velcro", "slip_on"]},
                "extra_depth": {"type": "boolean"},
            },
            "required": ["construction", "material", "closure", "extra_depth"],
            "additionalProperties": False,
        },
        "foot_lift": {
            "type": "object",
            "properties": {
                "heel_lift_left_mm": {"type": "number"},
                "heel_lift_right_mm": {"type": "number"},
            },
            "required": ["heel_lift_left_mm", "heel_lift_right_mm"],
            "additionalProperties": False,
        },
        "primary_condition_addressed": {"type": "string"},
        "clinician_referral_notes": {"type": "array", "items": {"type": "string"}},
        "rationale": {"type": "string"},
    },
    "required": [
        "last_spec", "arch_support", "midsole", "outsole", "upper", "foot_lift",
        "primary_condition_addressed", "clinician_referral_notes", "rationale",
    ],
    "additionalProperties": False,
}


class PrescriptionAgent:
    """Refines a rule-based prescription dict with Claude Opus 4.8."""

    def __init__(self, client: Optional[anthropic.Anthropic] = None) -> None:
        self._client: anthropic.Anthropic = client or anthropic.Anthropic()

    def refine(
        self,
        rule_based_spec: Dict[str, Any],
        rule_params: Dict[str, Any],
        anthropometrics: Dict[str, Any],
    ) -> tuple[Dict[str, Any], str]:
        """Refine a rule-based prescription with Claude.

        Args:
            rule_based_spec:  model_dump() of a PrescriptionSpec (rule-based output).
            rule_params:      Flat condition dict used by the rules engine (pronation_type, etc.).
            anthropometrics:  Patient measurements (height_cm, mass_kg, foot_length_mm, â€¦).

        Returns:
            (refined_spec_dict, rationale_str)
            On any error, returns (rule_based_spec, "fallback: <reason>").
        """
        try:
            prompt = self._build_prompt(rule_based_spec, rule_params, anthropometrics)

            with self._client.messages.stream(
                model=_MODEL,
                max_tokens=2048,
                thinking={"type": "adaptive"},
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                response = stream.get_final_message()

            response_text = next(
                (b.text for b in response.content if b.type == "text"), ""
            )

            # Strip markdown code fences if present
            text = response_text.strip()
            if text.startswith("```"):
                text = text.split("```", 2)[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.rsplit("```", 1)[0].strip()

            data = json.loads(text)
            rationale = data.pop("rationale", "agent_override")

            # Merge: start from rule-based spec, override only the fields Claude returned
            refined = dict(rule_based_spec)
            for field in _OVERRIDE_FIELDS:
                if field in data:
                    refined[field] = data[field]

            refined["confidence"] = "agent_override"

            logger.info(
                "prescription_agent.success",
                extra={"rationale": rationale[:120]},
            )
            return refined, rationale

        except Exception as exc:
            reason = f"fallback: {type(exc).__name__}: {exc}"
            logger.warning("prescription_agent.failed", extra={"reason": reason})
            return rule_based_spec, reason

    def _build_prompt(
        self,
        spec: Dict[str, Any],
        rule_params: Dict[str, Any],
        anthropometrics: Dict[str, Any],
    ) -> str:
        foot_len = anthropometrics.get("foot_length_mm", {})
        if isinstance(foot_len, dict):
            foot_len_str = f"L: {foot_len.get('L', '?')} mm, R: {foot_len.get('R', '?')} mm"
        else:
            foot_len_str = str(foot_len)

        return f"""You are an orthopedic footwear specialist reviewing a rule-based shoe prescription.
Refine it based on the complete clinical picture. Only change values that the data clearly justifies.

PATIENT:
- Height: {anthropometrics.get('height_cm', '?')} cm
- Mass: {anthropometrics.get('mass_kg', '?')} kg
- Foot length: {foot_len_str}

BIOMECHANICAL FINDINGS:
- Pronation: {rule_params.get('pronation_type', 'neutral')}
- Arch: {rule_params.get('arch_type', 'normal')}
- Foot strike: {rule_params.get('foot_strike_type', 'rearfoot')}
- Active flags: {rule_params.get('flags', [])}

CURRENT RULE-BASED PRESCRIPTION:
{json.dumps(spec, indent=2)}

Return a JSON object with the full refined prescription. Include every field shown above.
Add a "rationale" field (string) explaining any changes made.
Return ONLY valid JSON â€” no markdown fences, no other text.

Required JSON structure:
{json.dumps(_PRESCRIPTION_JSON_SCHEMA, indent=2)}"""

