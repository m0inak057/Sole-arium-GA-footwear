# API & Schema Contract
## Gait Analysis Module — Interfaces

| Field | Value |
|---|---|
| Document | API & Schema |
| Version | 2.0 |
| Schema version | profile/v1 |
| Related | [ARCHITECTURE.md](./ARCHITECTURE.md), [PROJECT_STRUCTURE.md](./PROJECT_STRUCTURE.md) |

This document defines the two contracts that matter most:
1. The **REST API** that clinicians, patients, and integrators use to submit gait videos and receive personalized health assessments.
2. The **patient-profile JSON** — the canonical output that contains biomechanical analysis results and a personalized health improvement plan for the patient.

**Important:** The primary end-user of this system is the **patient receiving health feedback**, not a shoe designer. The health assessment block provides patient-facing language explaining what was found in their gait and what exercises they should do to improve. Clinical staff and researchers may extract additional data for shoe design or further analysis, but the default output is designed for patient comprehension and engagement.

> **Stability rule:** the patient-profile schema is versioned (`profile/v1`). Breaking changes require a new version and a migration note. Additive, optional fields are allowed within a version.

---

## 1. REST API (FastAPI)

Base path: `/api/v1`. All endpoints require authentication; access is role-scoped (patient, clinician, researcher, admin) — see [PRIVACY_COMPLIANCE.md](./PRIVACY_COMPLIANCE.md).

**Endpoint audience:** Patients interact with `/sessions/{session_id}/profile` to download their health assessment. Clinicians manage sessions and upload videos. Researchers and shoe designers can request the full biomechanical dataset if authorized.

### Sessions

| Method | Path | Description |
|---|---|---|
| `POST` | `/sessions` | Create a session; register subject metadata. Returns `session_id`. |
| `POST` | `/sessions/{session_id}/uploads` | Upload synchronized video (multipart or signed-URL handshake). |
| `POST` | `/sessions/{session_id}/process` | Enqueue the pipeline for this session. |
| `GET` | `/sessions/{session_id}` | Session status: `created` → `uploaded` → `processing` → `complete` / `needs_rerecord` / `failed`. |
| `GET` | `/sessions` | List sessions (paginated, filterable by subject). |

### Profiles

| Method | Path | Description |
|---|---|---|
| `GET` | `/sessions/{session_id}/profile` | Fetch the `profile.json` for a completed session — **patient-facing health assessment with biomechanical analysis and personalized exercises**. |
| `GET` | `/sessions/{session_id}/timeseries` | Fetch per-cycle time-series (Parquet/JSON) for advanced analysis and visualization (researcher/clinician only). |
| `PATCH` | `/sessions/{session_id}/profile/health-assessment` | Clinician update to the health assessment block (add context notes, update exercises). |
| `GET` | `/profiles/schema` | Return the current JSON Schema for `profile/v1`. |

### Rules & admin

| Method | Path | Description |
|---|---|---|
| `GET` | `/rules` | Get the active recommendation rules (`rules.yaml`). |
| `PUT` | `/rules` | Update recommendation rules (orthotist/admin only; versioned). |
| `GET` | `/health` | Liveness/readiness. |

### AI agents (Phase 3+)

| Method | Path | Description |
|---|---|---|
| `GET` | `/agents/status` | Return status and model version of each agent (enabled/disabled, model_path, confidence_threshold). |
| `GET` | `/agents/{name}/metrics` | Per-agent metrics: predictions_made, mean_confidence, override_rate, accuracy_vs_baseline. |

### Status semantics

| Status | Meaning | Next action |
|---|---|---|
| `created` | Session exists, no video yet | Upload video |
| `uploaded` | Video stored | Trigger processing |
| `processing` | Pipeline running | Poll |
| `complete` | `profile.json` ready | Review / hand off |
| `needs_rerecord` | < 4 clean cycles/foot survived | Re-record subject |
| `failed` | Pipeline error | Inspect logs |

---

## 2. Patient profile JSON — reference example

This is the canonical output. It provides biomechanical analysis and a personalized health assessment for the patient.

```json
{
  "schema_version": "profile/v1",
  "patient_id": "P0042",
  "session_timestamp": "2026-05-15T11:23:00Z",
  "trial_condition": "barefoot",
  "anthropometrics": {
    "height_cm": 172, "mass_kg": 68,
    "foot_length_mm": {"L": 258, "R": 260},
    "foot_width_mm": {"L": 98, "R": 99}
  },
  "spatiotemporal": {
    "cadence_spm": 112,
    "speed_mps": 1.28,
    "stride_length_m": 1.37,
    "step_width_m": 0.09,
    "stance_pct": {"L": 61.2, "R": 60.4},
    "double_support_pct": 22.1,
    "step_length_left_m": 0.68,
    "step_length_right_m": 0.67,
    "foot_progression_angle_left_deg": 7.2,
    "foot_progression_angle_right_deg": 6.8,
    "foot_progression_classification_left": "toe_out",
    "foot_progression_classification_right": "toe_out"
  },
  "foot_strike": {
    "pattern": {"L": "rearfoot", "R": "rearfoot"},
    "foot_strike_angle_deg": {"L": 18.2, "R": 16.7}
  },
  "pronation": {
    "rearfoot_angle_at_midstance_deg": {"L": 11.4, "R": 9.8},
    "classification": {"L": "overpronation", "R": "overpronation"},
    "time_to_peak_eversion_pct_stance": {"L": 38, "R": 42},
    "frontal_plane_excursion_left_deg": 12.3,
    "frontal_plane_excursion_right_deg": 11.8
  },
  "arch": {
    "type": {"L": "low", "R": "low"},
    "arch_height_index": {"L": 0.21, "R": 0.22}
  },
  "kinematics_peaks": {
    "knee_flexion_stance_deg": {"L": 17, "R": 18},
    "hip_adduction_stance_deg": {"L": 9, "R": 7}
  },
  "symmetry_flags": ["step_length_asymmetric_12pct"],
  "health_assessment": {
    "what_went_right": [
      "Good symmetry in cadence (112 steps/min on both sides)",
      "Healthy foot progression angle (neutral, 6-7°)"
    ],
    "defects_found": [
      {
        "name": "Severe Overpronation - Left Foot",
        "severity": "severe",
        "affected_side": "left",
        "biomechanical_cause": "Rearfoot eversion angle of 11.4° at midstance exceeds normal range (0-4°), indicating excessive inward rolling of the heel and stress on medial foot structures",
        "gait_cycle_phase": "Loading Response to Mid-Stance"
      }
    ],
    "improvement_plan": [
      {
        "exercise_name": "Short Foot Exercise",
        "target_area": "Intrinsic foot muscles",
        "frequency": "3 sets of 12 reps, daily",
        "instructions": "Sit or stand with feet flat on the ground. Without curling your toes, shorten the foot by drawing the ball of the foot toward the heel, creating a dome under the arch. Hold for 5 seconds.",
        "addresses_defect": "Severe Overpronation - Left Foot"
      }
    ]
  },
  "confidence_scores": {
    "pronation_classification": 0.91,
    "foot_strike_classification": 0.95
  },
  "needs_human_review": false
}
```

---

## 3. Field reference

| Field | Type | Notes |
|---|---|---|
| `patient_id` | string | Pseudonymous subject identifier |
| `session_timestamp` | string (ISO 8601) | Capture time, UTC |
| `anthropometrics.height_cm` | number | |
| `anthropometrics.mass_kg` | number | |
| `anthropometrics.foot_length_mm` | `{L, R}` numbers | Per foot |
| `anthropometrics.foot_width_mm` | `{L, R}` numbers | Per foot |
| `spatiotemporal.cadence_spm` | number | Steps per minute |
| `spatiotemporal.speed_mps` | number | Walking speed |
| `spatiotemporal.stride_length_m` | number | |
| `spatiotemporal.step_width_m` | number | |
| `spatiotemporal.stance_pct` | `{L, R}` numbers | % of cycle in stance |
| `spatiotemporal.double_support_pct` | number | |
| `spatiotemporal.step_length_left_m` | number | Step length for left foot (m) |
| `spatiotemporal.step_length_right_m` | number | Step length for right foot (m) |
| `spatiotemporal.foot_progression_angle_left_deg` | number | Left FPA (degrees; positive = toe-out) |
| `spatiotemporal.foot_progression_angle_right_deg` | number | Right FPA (degrees; positive = toe-out) |
| `spatiotemporal.foot_progression_classification_left` | enum | `toe_in` / `neutral` / `toe_out` |
| `spatiotemporal.foot_progression_classification_right` | enum | `toe_in` / `neutral` / `toe_out` |
| `foot_strike.pattern` | `{L, R}` enum | `rearfoot` / `midfoot` / `forefoot` |
| `foot_strike.foot_strike_angle_deg` | `{L, R}` numbers | FSA at heel-strike |
| `pronation.rearfoot_angle_at_midstance_deg` | `{L, R}` numbers | Headline metric |
| `pronation.classification` | `{L, R}` enum | `overpronation` / `mild_pronation` / `neutral` / `mild_supination` / `oversupination` |
| `pronation.time_to_peak_eversion_pct_stance` | `{L, R}` numbers | Early peak = poor shock absorption |
| `pronation.frontal_plane_excursion_left_deg` | number | Total eversion range during stance (left) |
| `pronation.frontal_plane_excursion_right_deg` | number | Total eversion range during stance (right) |
| `arch.type` | `{L, R}` enum | `high` / `normal` / `low` |
| `arch.arch_height_index` | `{L, R}` numbers | |
| `kinematics_peaks.*` | `{L, R}` numbers | Peak joint angles during stance |
| `symmetry_flags` | string[] | e.g. `step_length_asymmetric_12pct` |
| `health_assessment` | object | **Patient-facing health assessment** with findings and improvement exercises |
| `health_assessment.what_went_right` | string[] | Positive gait findings (patient-friendly) |
| `health_assessment.defects_found` | object[] | List of biomechanical issues with severity and cause (plain language) |
| `health_assessment.improvement_plan` | object[] | Targeted exercises addressing each defect |
| `confidence_scores.*` | number 0–1 | Per classification |
| `needs_human_review` | boolean (optional) | Set when pathological gait detected |

---

## 4. JSON Schema (`profile/v1`)

> Source of truth lives in `src/gait/profile/schema.py` (pydantic). This JSON Schema is generated from it.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.org/schemas/gait/profile/v1.json",
  "title": "GaitPatientProfile",
  "type": "object",
  "required": [
    "patient_id", "session_timestamp", "anthropometrics",
    "spatiotemporal", "foot_strike", "pronation", "arch",
    "symmetry_flags", "health_assessment", "confidence_scores"
  ],
  "additionalProperties": false,
  "$defs": {
    "lr_number": {
      "type": "object",
      "required": ["L", "R"],
      "additionalProperties": false,
      "properties": { "L": { "type": "number" }, "R": { "type": "number" } }
    }
  },
  "properties": {
    "patient_id": { "type": "string" },
    "session_timestamp": { "type": "string", "format": "date-time" },
    "schema_version": { "type": "string", "const": "profile/v1" },
    "anthropometrics": {
      "type": "object",
      "required": ["height_cm", "mass_kg", "foot_length_mm", "foot_width_mm"],
      "additionalProperties": false,
      "properties": {
        "height_cm": { "type": "number" },
        "mass_kg": { "type": "number" },
        "foot_length_mm": { "$ref": "#/$defs/lr_number" },
        "foot_width_mm": { "$ref": "#/$defs/lr_number" }
      }
    },
    "spatiotemporal": {
      "type": "object",
      "required": ["cadence_spm", "speed_mps", "stride_length_m", "step_width_m", "stance_pct", "double_support_pct"],
      "additionalProperties": false,
      "properties": {
        "cadence_spm": { "type": "number" },
        "speed_mps": { "type": "number" },
        "stride_length_m": { "type": "number" },
        "step_width_m": { "type": "number" },
        "stance_pct": { "$ref": "#/$defs/lr_number" },
        "double_support_pct": { "type": "number" }
      }
    },
    "foot_strike": {
      "type": "object",
      "required": ["pattern", "foot_strike_angle_deg"],
      "additionalProperties": false,
      "properties": {
        "pattern": {
          "type": "object",
          "required": ["L", "R"],
          "additionalProperties": false,
          "properties": {
            "L": { "enum": ["rearfoot", "midfoot", "forefoot"] },
            "R": { "enum": ["rearfoot", "midfoot", "forefoot"] }
          }
        },
        "foot_strike_angle_deg": { "$ref": "#/$defs/lr_number" }
      }
    },
    "pronation": {
      "type": "object",
      "required": ["rearfoot_angle_at_midstance_deg", "classification", "time_to_peak_eversion_pct_stance"],
      "additionalProperties": false,
      "properties": {
        "rearfoot_angle_at_midstance_deg": { "$ref": "#/$defs/lr_number" },
        "classification": {
          "type": "object",
          "required": ["L", "R"],
          "additionalProperties": false,
          "properties": {
            "L": { "enum": ["overpronation", "mild_pronation", "neutral", "mild_supination", "oversupination"] },
            "R": { "enum": ["overpronation", "mild_pronation", "neutral", "mild_supination", "oversupination"] }
          }
        },
        "time_to_peak_eversion_pct_stance": { "$ref": "#/$defs/lr_number" }
      }
    },
    "arch": {
      "type": "object",
      "required": ["type", "arch_height_index"],
      "additionalProperties": false,
      "properties": {
        "type": {
          "type": "object",
          "required": ["L", "R"],
          "additionalProperties": false,
          "properties": {
            "L": { "enum": ["high", "normal", "low"] },
            "R": { "enum": ["high", "normal", "low"] }
          }
        },
        "arch_height_index": { "$ref": "#/$defs/lr_number" }
      }
    },
    "kinematics_peaks": {
      "type": "object",
      "additionalProperties": { "$ref": "#/$defs/lr_number" }
    },
    "symmetry_flags": {
      "type": "array",
      "items": { "type": "string" }
    },
    "health_assessment": {
      "type": "object",
      "required": ["what_went_right", "defects_found", "improvement_plan"],
      "additionalProperties": false,
      "properties": {
        "what_went_right": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Positive findings in the patient's gait"
        },
        "defects_found": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["name", "severity", "affected_side", "biomechanical_cause", "gait_cycle_phase"],
            "properties": {
              "name": { "type": "string", "description": "Name of the defect (e.g., 'Severe Overpronation - Left Foot')" },
              "severity": { "enum": ["mild", "moderate", "severe"], "description": "Severity level" },
              "affected_side": { "enum": ["left", "right", "bilateral"], "description": "Which side(s) affected" },
              "biomechanical_cause": { "type": "string", "description": "Plain-English explanation of the data" },
              "gait_cycle_phase": { "type": "string", "description": "Phase where defect occurs (e.g., 'Loading Response')" }
            }
          },
          "description": "List of biomechanical defects found"
        },
        "improvement_plan": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["exercise_name", "target_area", "frequency", "instructions", "addresses_defect"],
            "properties": {
              "exercise_name": { "type": "string" },
              "target_area": { "type": "string", "description": "Body area targeted" },
              "frequency": { "type": "string", "description": "Recommended frequency" },
              "instructions": { "type": "string", "description": "Step-by-step instructions" },
              "addresses_defect": { "type": "string", "description": "Links to DefectDetail.name" }
            }
          },
          "description": "Targeted exercises to address defects"
        }
      }
    },
    "confidence_scores": {
      "type": "object",
      "additionalProperties": { "type": "number", "minimum": 0, "maximum": 1 }
    },
    "needs_human_review": { "type": "boolean" }
  }
}
```

---

## 5. Thresholds config (`configs/thresholds.yaml`)

These drive the classifiers. They are **defaults based on common clinical heuristics** and must be re-tuned with the validation dataset.

```yaml
foot_strike:
  rearfoot_min_deg: 5.0      # FSA > +5° → rearfoot
  forefoot_max_deg: -5.0     # FSA < -5° → forefoot
                             # between → midfoot

pronation:                   # peak rearfoot eversion at mid-stance
  overpronation_min_deg: 8.0
  mild_pronation_min_deg: 4.0
  neutral_min_deg: 0.0
  mild_supination_min_deg: -4.0
                             # below -4° → oversupination

symmetry:
  flag_threshold_pct: 10.0

quality_gating:
  min_keypoint_confidence: 0.5
  min_clean_cycles_per_foot: 4
  target_clean_cycles_per_foot: 8
```

---

## 6. Recommendation rules (`configs/rules.yaml`)

Editable by the orthotist; applied by `profile/recommend.py`. Each rule has a `when` condition and a `then` recommendation patch. Rules are evaluated in order; later rules can refine earlier ones.

```yaml
version: 1
rules:
  - id: overpronation_low_arch
    when:
      pronation: overpronation
      arch: low
    then:
      medial_post: required
      post_density: firm
      arch_support: high
      heel_counter: rigid
      last_shape: straight

  - id: oversupination_high_arch
    when:
      pronation: oversupination
      arch: high
    then:
      medial_post: none
      arch_support: medium
      last_shape: curved
      cushioning_zone_priority: ["lateral_midsole", "heel"]

  - id: forefoot_striker
    when:
      foot_strike: forefoot
    then:
      heel_drop_mm: 6
      cushioning_zone_priority: ["forefoot", "midfoot"]

  - id: pathological_review
    when:
      flag: pathological_gait
    then:
      needs_human_review: true
```

> **Guardrail:** if any rule sets `needs_human_review: true`, the recommendation block must **not** be auto-finalized — it is surfaced to the clinician first. See [VALIDATION_QA.md](./VALIDATION_QA.md).

---

## 7. Prescription spec (`prescription_spec`)

This block is **orthotist/shoe-designer-facing only**. It is populated for every session that has a valid `health_assessment` and must **never** be surfaced directly to the patient.

### Field reference

| Field | Type | Notes |
|---|---|---|
| `prescription_spec.last_spec.shape` | enum | `straight` / `semi_curved` / `curved` |
| `prescription_spec.last_spec.toe_box` | enum | `standard` / `wide` / `extra_wide` / `deep` |
| `prescription_spec.last_spec.heel_counter` | enum | `rigid` / `semi_rigid` / `flexible` |
| `prescription_spec.arch_support.height_mm` | number | Peak arch support height in mm (15–35) |
| `prescription_spec.arch_support.type` | enum | `contoured` / `flat` / `accommodative` |
| `prescription_spec.arch_support.medial_post` | boolean | Whether medial density post is required |
| `prescription_spec.arch_support.medial_post_shore_c` | number\|null | Shore C of medial post (null when `medial_post` is false) |
| `prescription_spec.midsole.medial_shore_c` | number | Medial midsole firmness (Shore C, 45–75) |
| `prescription_spec.midsole.lateral_shore_c` | number | Lateral midsole firmness (Shore C, 45–65) |
| `prescription_spec.midsole.heel_drop_mm` | number | Heel-to-forefoot height difference (0–12 mm) |
| `prescription_spec.midsole.cushioning_priority` | enum | `heel` / `forefoot` / `full_length` / `lateral` |
| `prescription_spec.outsole.base` | enum | `standard` / `flared` / `rocker` |
| `prescription_spec.outsole.rocker_apex_position` | string\|null | `metatarsal` / `midfoot` — only when base is `rocker` |
| `prescription_spec.outsole.lateral_reinforcement` | boolean | Extra rubber on lateral wear zone |
| `prescription_spec.upper.construction` | enum | `standard` / `seamless` / `minimal_seam` |
| `prescription_spec.upper.material` | enum | `leather` / `neoprene` / `mesh` |
| `prescription_spec.upper.closure` | enum | `lace` / `velcro` / `slip_on` |
| `prescription_spec.upper.extra_depth` | boolean | Extra vertical depth for orthotic accommodation |
| `prescription_spec.foot_lift.heel_lift_left_mm` | number | mm of heel raise for left shoe (0 = symmetric) |
| `prescription_spec.foot_lift.heel_lift_right_mm` | number | mm of heel raise for right shoe (0 = symmetric) |
| `prescription_spec.primary_condition_addressed` | string | Plain-English dominant condition summary |
| `prescription_spec.clinician_referral_notes` | string[] | Flags for specialist review before fabrication |
| `prescription_spec.confidence` | string | `rule_based` / `agent_override` |

### Shore-C body-mass modifiers (applied automatically)

| Body mass | Shore-C delta |
|---|---|
| < 60 kg | −5 (softer midsole, lighter load) |
| 60–80 kg | 0 (no change) |
| 80–100 kg | +10 (firmer for higher impact) |
| > 100 kg | +15 + PU midsole note |

### Heel lift from step asymmetry

When `step_length_asymmetric` is flagged (>10% asymmetry), 3 mm of heel lift is automatically added to the **shorter-stepping** shoe. The orthotist must confirm leg-length discrepancy before fabrication.

### Worked example — severe overpronator (68 kg, rearfoot striker, left and right rearfoot eversion > 8°)

```json
"prescription_spec": {
  "last_spec": {
    "shape": "straight",
    "toe_box": "standard",
    "heel_counter": "rigid"
  },
  "arch_support": {
    "height_mm": 30.0,
    "type": "contoured",
    "medial_post": true,
    "medial_post_shore_c": 75.0
  },
  "midsole": {
    "medial_shore_c": 75.0,
    "lateral_shore_c": 45.0,
    "heel_drop_mm": 10.0,
    "cushioning_priority": "heel"
  },
  "outsole": {
    "base": "standard",
    "rocker_apex_position": null,
    "lateral_reinforcement": false
  },
  "upper": {
    "construction": "standard",
    "material": "leather",
    "closure": "lace",
    "extra_depth": false
  },
  "foot_lift": {
    "heel_lift_left_mm": 0.0,
    "heel_lift_right_mm": 0.0
  },
  "primary_condition_addressed": "Severe bilateral overpronation",
  "clinician_referral_notes": [],
  "confidence": "rule_based"
}
```

---

## 8. Versioning policy

- **Additive change** (new optional field) → same version (`profile/v1`).
- **Breaking change** (rename, type change, removed field, changed enum) → new version (`profile/v2`) + a migration note in this doc.
- The downstream shoe-design module pins the schema version it supports.
- `GET /profiles/schema` always returns the schema for the currently deployed version.
