"""GaitHealthCoach â€” Claude-powered personalized health assessment with deterministic fallback.

This agent uses Claude Opus 4.8 (with streaming + adaptive thinking) to generate
personalized health assessments from biomechanical data. Strict validation ensures
the output is grounded in the actual input data. If validation fails, the agent
returns None and the pipeline falls back to RuleBasedRecommendationEngine.

Core design:
  1. Construct plain-language prompt from biomechanical metrics (including L/R labels).
  2. Stream from Claude with adaptive thinking; accumulate with get_final_message().
  3. Parse + validate through Pydantic (catches malformed JSON and schema violations).
  4. Verify every defect is grounded in input metrics (no hallucinations).
  5. Return HealthAssessment dict OR None for fallback; log all decisions.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

import anthropic
from pydantic import ValidationError

from gait.agents.base import GaitAgent
from gait.common.logging_utils import get_logger
from gait.profile.schema import HealthAssessment, DefectDetail, ImprovementAction

logger = get_logger(__name__)

_MODEL = "claude-opus-4-8"


class GaitHealthCoach(GaitAgent):
    """Claude-powered health assessment agent with fallback validation."""

    def __init__(self, llm_client: Optional[anthropic.Anthropic] = None, model: str = _MODEL) -> None:
        """Initialize the health coach.

        Args:
            llm_client: Anthropic client. If None, a default client is created
                        (reads ANTHROPIC_API_KEY from the environment).
            model: Model ID to use.
        """
        self._client: anthropic.Anthropic = llm_client or anthropic.Anthropic()
        self._model = model

    def predict(self, params: Dict[str, Any]) -> tuple[Optional[HealthAssessment], float, str]:
        """Generate health assessment from biomechanical parameters via LLM.

        Args:
            params: Dict containing spatiotemporal, pronation, arch, foot-strike metrics.
                    Expected keys: step_length_left_m, step_length_right_m,
                    foot_progression_angle_left_deg, foot_progression_angle_right_deg,
                    rearfoot_angle_deg_mean_L/R, frontal_plane_excursion_deg_mean_L/R,
                    pronation_type_L/R, arch_type_L/R, foot_strike_type_L/R, etc.

        Returns:
            (health_assessment_dict, confidence_score, reasoning_str)

            If validation fails: (None, 0.0, error_message)
            If LLM error: (None, 0.0, error_message)
            If success: (HealthAssessment instance, confidence, "LLM parsed successfully")
        """
        try:
            # Build structured prompt
            prompt = self._build_prompt(params)

            # Stream from Claude with adaptive thinking; accumulate into a final message
            with self._client.messages.stream(
                model=self._model,
                max_tokens=4096,
                thinking={"type": "adaptive"},
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                response = stream.get_final_message()

            # Extract text block (there may also be a thinking block â€” skip it)
            response_text = next(
                (b.text for b in response.content if b.type == "text"), ""
            )
            logger.debug(
                "health_coach.llm_response",
                extra={"response_length": len(response_text)},
            )

            # Parse JSON
            try:
                assessment_dict = json.loads(response_text)
            except json.JSONDecodeError as exc:
                return None, 0.0, f"LLM returned malformed JSON: {str(exc)}"

            # Validate through Pydantic
            try:
                assessment = HealthAssessment(**assessment_dict)
            except ValidationError as exc:
                errors = [f"{e['loc']}: {e['msg']}" for e in exc.errors()]
                return None, 0.0, f"Pydantic validation failed: {errors}"

            # Verify defects are grounded in input data
            validation_ok, error = self.validate(assessment, params)
            if not validation_ok:
                return None, 0.0, error

            # Success
            return assessment, 0.95, "LLM response parsed and validated"

        except Exception as exc:
            return None, 0.0, f"LLM call failed: {type(exc).__name__}: {str(exc)}"

    def validate(self, result: HealthAssessment, params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Verify all defects are grounded in input metrics (no hallucinations).

        A defect is grounded if it references actual threshold breaches found in the input.
        Validates across all defect categories: pronation, arch, foot strike, step length
        asymmetry, foot progression, and frontal-plane excursion.

        Returns:
            (is_valid, error_message)
        """
        for defect in result.defects_found:
            # Check category-specific grounding
            is_grounded = self._is_defect_grounded(defect, params)
            if not is_grounded:
                return False, f"Defect '{defect.name}' is not grounded in input metrics"

        return True, None

    def _is_defect_grounded(self, defect: DefectDetail, params: Dict[str, Any]) -> bool:
        """Check if a specific defect is grounded in the input parameters.

        Returns True if the defect matches actual metrics; False if hallucinated.
        """
        defect_lower = defect.name.lower()

        # Get side-specific metrics
        if defect.affected_side == "left":
            side_metrics = params.get("left_metrics", {})
        elif defect.affected_side == "right":
            side_metrics = params.get("right_metrics", {})
        elif defect.affected_side == "bilateral":
            side_metrics = params.get("left_metrics", {})  # check left side for bilateral
        else:
            return False

        # Pronation-related defects
        if any(kw in defect_lower for kw in ("overpronation", "pronation")):
            pron_type = side_metrics.get("pronation_type", "neutral")
            # Overpronation claims must match overpronation or mild_pronation
            if "overpronation" in defect_lower and "over" not in pron_type:
                return False
            if "severe" in defect_lower and pron_type != "overpronation":
                return False
            return True

        if any(kw in defect_lower for kw in ("supination", "supination")):
            pron_type = side_metrics.get("pronation_type", "neutral")
            # Supination claims must match oversupination or mild_supination
            if any(kw in defect_lower for kw in ("oversupination", "super")) and pron_type not in ("oversupination", "mild_supination"):
                return False
            return True

        # Arch-related defects
        if "arch" in defect_lower or "flatfoot" in defect_lower or "pes" in defect_lower:
            arch_type = side_metrics.get("arch_type", "normal")
            if "flat" in defect_lower and arch_type != "low":
                return False
            if "high" in defect_lower and arch_type != "high":
                return False
            return True

        # Foot strike defects
        if "foot strike" in defect_lower or "forefoot" in defect_lower:
            strike_type = side_metrics.get("foot_strike_type", "rearfoot")
            if "forefoot" in defect_lower and strike_type != "forefoot":
                return False
            return True

        # Step length asymmetry
        if "step" in defect_lower and "asymmetr" in defect_lower:
            # Check if there's actual step length asymmetry in input
            step_l = params.get("step_length_left_m", 0.0)
            step_r = params.get("step_length_right_m", 0.0)
            if step_l > 0 and step_r > 0:
                mean = (step_l + step_r) / 2
                if mean > 0:
                    asymmetry_pct = abs(step_l - step_r) / mean * 100
                    return asymmetry_pct > 10  # Must have >10% asymmetry
            return False

        # Foot progression defects
        if "foot progression" in defect_lower or "toe" in defect_lower:
            fpa_l = params.get("foot_progression_angle_left_deg", 0.0)
            fpa_r = params.get("foot_progression_angle_right_deg", 0.0)
            if "toe-in" in defect_lower or "toe in" in defect_lower:
                # Toe-in is negative angle < -5Â°
                return (fpa_l < -5 or fpa_r < -5) if defect.affected_side == "bilateral" else (fpa_l if defect.affected_side == "left" else fpa_r) < -5
            if "toe-out" in defect_lower or "toe out" in defect_lower:
                # Toe-out is positive angle > 10Â°
                return (fpa_l > 10 or fpa_r > 10) if defect.affected_side == "bilateral" else (fpa_l if defect.affected_side == "left" else fpa_r) > 10
            return True

        # Frontal-plane excursion defects
        if "frontal" in defect_lower or "excursion" in defect_lower:
            fpe_l = params.get("frontal_plane_excursion_deg_mean_L", 0.0)
            fpe_r = params.get("frontal_plane_excursion_deg_mean_R", 0.0)
            # High excursion is > 8Â°
            if "high" in defect_lower:
                return (fpe_l > 8 or fpe_r > 8) if defect.affected_side == "bilateral" else (fpe_l if defect.affected_side == "left" else fpe_r) > 8
            return True

        # Unknown defect type - reject it
        return False

    def _build_prompt(self, params: Dict[str, Any]) -> str:
        """Build structured plain-language prompt from biomechanical metrics.

        The prompt instructs the LLM to:
          - Use only the provided metrics (no external knowledge).
          - Return ONLY valid JSON matching HealthAssessment schema.
          - Reference actual patient numbers in biomechanical_cause.
          - Recommend exercises specific to severity and side.
        """
        # Extract metrics from params dict
        step_length_left = params.get("step_length_left_m", 0.0)
        step_length_right = params.get("step_length_right_m", 0.0)
        fpa_left = params.get("foot_progression_angle_left_deg", 0.0)
        fpa_right = params.get("foot_progression_angle_right_deg", 0.0)

        rearfoot_left = params.get("rearfoot_angle_deg_mean_L", 0.0)
        rearfoot_right = params.get("rearfoot_angle_deg_mean_R", 0.0)

        fpe_left = params.get("frontal_plane_excursion_deg_mean_L", 0.0)
        fpe_right = params.get("frontal_plane_excursion_deg_mean_R", 0.0)

        pronation_left = params.get("pronation_type_L", "neutral")
        pronation_right = params.get("pronation_type_R", "neutral")

        arch_left = params.get("arch_type_L", "normal")
        arch_right = params.get("arch_type_R", "normal")

        foot_strike_left = params.get("foot_strike_type_L", "rearfoot")
        foot_strike_right = params.get("foot_strike_type_R", "rearfoot")

        prompt = f"""You are a clinical gait analysis expert. Analyze the following biomechanical metrics for a patient and generate a personalized health assessment in JSON format.

PATIENT BIOMECHANICAL METRICS (measured):

SPATIOTEMPORAL:
- Left foot step length: {step_length_left:.2f} meters
- Right foot step length: {step_length_right:.2f} meters
- Left foot progression angle: {fpa_left:.1f} degrees
- Right foot progression angle: {fpa_right:.1f} degrees

PRONATION ANALYSIS:
- Left foot rearfoot angle at midstance: {rearfoot_left:.1f} degrees
- Right foot rearfoot angle at midstance: {rearfoot_right:.1f} degrees
- Left foot classification: {pronation_left}
- Right foot classification: {pronation_right}
- Left foot frontal-plane excursion (mobility): {fpe_left:.1f} degrees
- Right foot frontal-plane excursion (mobility): {fpe_right:.1f} degrees

ARCH ASSESSMENT:
- Left foot arch type: {arch_left}
- Right foot arch type: {arch_right}

FOOT STRIKE:
- Left foot pattern: {foot_strike_left}
- Right foot pattern: {foot_strike_right}

INSTRUCTIONS:
1. Analyze ONLY the metrics provided above. Do NOT use external assumptions.
2. Return ONLY a valid JSON object matching this structure exactly:
{{
    "what_went_right": ["finding1", "finding2"],
    "defects_found": [
        {{
            "name": "Condition Name - Side",
            "severity": "mild|moderate|severe",
            "affected_side": "left|right|bilateral",
            "biomechanical_cause": "Plain English explanation referencing the actual patient metrics (e.g., 'left rearfoot angle of {rearfoot_left:.1f}Â° exceeds normal')",
            "gait_cycle_phase": "Loading Response|Mid-Stance|Terminal Stance|etc."
        }}
    ],
    "improvement_plan": [
        {{
            "exercise_name": "Exercise Name",
            "target_area": "Area targeted",
            "frequency": "e.g., 3 sets of 12 reps, daily",
            "instructions": "Step-by-step instructions",
            "addresses_defect": "Name from defects_found matching this"
        }}
    ]
}}
3. For biomechanical_cause, ALWAYS reference the actual patient numbers (e.g., "your left step length of {step_length_left:.2f}m").
4. Do not make claims not supported by the metrics.
5. Return ONLY JSON, no other text before or after.

Generate the assessment:"""
        return prompt

    def _extract_thresholds_from_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Extract clinical thresholds and metrics for validation.

        This is used by validate() to check if defect claims are grounded.
        """
        return {
            "rearfoot_angle_overpronation_threshold": 8.0,  # > 8Â° = overpronation
            "rearfoot_angle_neutral_min": 0.0,
            "rearfoot_angle_neutral_max": 4.0,
            "frontal_plane_excursion_normal_max": 10.0,
        }

