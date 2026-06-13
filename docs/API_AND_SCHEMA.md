# API & Schema Contract
## Gait Analysis Module — Interfaces

| Field | Value |
|---|---|
| Document | API & Schema |
| Version | 1.0 |
| Schema version | profile/v1 |
| Related | [ARCHITECTURE.md](./ARCHITECTURE.md), [PROJECT_STRUCTURE.md](./PROJECT_STRUCTURE.md) |

This document defines the two contracts that matter most:
1. The **REST API** the clinician UI and integrators talk to.
2. The **patient-profile JSON** — the single artifact the downstream shoe-design module consumes.

> **Stability rule:** the patient-profile schema is versioned (`profile/v1`). Breaking changes require a new version and a migration note. Additive, optional fields are allowed within a version.

---

## 1. REST API (FastAPI)

Base path: `/api/v1`. All endpoints require authentication; access is role-scoped (clinician vs. shoe designer vs. admin) — see [PRIVACY_COMPLIANCE.md](./PRIVACY_COMPLIANCE.md).

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
| `GET` | `/sessions/{session_id}/profile` | Fetch the `profile.json` for a completed session. |
| `GET` | `/sessions/{session_id}/timeseries` | Fetch per-cycle time-series (Parquet/JSON) for plotting. |
| `PATCH` | `/sessions/{session_id}/profile/recommendations` | Clinician override of the recommendation block. |
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

This is the canonical output. The shoe-design module reads only this.

```json
{
  "patient_id": "P0042",
  "session_timestamp": "2026-05-15T11:23:00Z",
  "anthropometrics": {
    "height_cm": 172, "mass_kg": 68,
    "foot_length_mm": {"L": 258, "R": 260},
    "foot_width_mm": {"L": 98, "R": 99}
  },
  "spatiotemporal": {
    "cadence_spm": 112, "speed_mps": 1.28,
    "stride_length_m": 1.37,
    "step_width_m": 0.09,
    "stance_pct": {"L": 61.2, "R": 60.4},
    "double_support_pct": 22.1
  },
  "foot_strike": {
    "pattern": {"L": "rearfoot", "R": "rearfoot"},
    "foot_strike_angle_deg": {"L": 18.2, "R": 16.7}
  },
  "pronation": {
    "rearfoot_angle_at_midstance_deg": {"L": 11.4, "R": 9.8},
    "classification": {"L": "overpronation", "R": "overpronation"},
    "time_to_peak_eversion_pct_stance": {"L": 38, "R": 42}
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
  "shoe_design_recommendations": {
    "medial_post": "required",
    "post_density": "firm",
    "arch_support": "high",
    "heel_counter": "rigid",
    "heel_drop_mm": 10,
    "cushioning_zone_priority": ["heel", "medial_forefoot"],
    "last_shape": "straight"
  },
  "confidence_scores": {
    "pronation_classification": 0.91,
    "foot_strike_classification": 0.95
  },
  "agent_decisions": {
    "quality_assessment": {"source": "agent", "confidence": 0.88, "quality_score": 0.92},
    "pronation_classification": {"source": "static_baseline", "confidence": null}
  }
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
| `foot_strike.pattern` | `{L, R}` enum | `rearfoot` / `midfoot` / `forefoot` |
| `foot_strike.foot_strike_angle_deg` | `{L, R}` numbers | FSA at heel-strike |
| `pronation.rearfoot_angle_at_midstance_deg` | `{L, R}` numbers | Headline metric |
| `pronation.classification` | `{L, R}` enum | `overpronation` / `mild_pronation` / `neutral` / `mild_supination` / `oversupination` |
| `pronation.time_to_peak_eversion_pct_stance` | `{L, R}` numbers | Early peak = poor shock absorption |
| `arch.type` | `{L, R}` enum | `high` / `normal` / `low` |
| `arch.arch_height_index` | `{L, R}` numbers | |
| `kinematics_peaks.*` | `{L, R}` numbers | Peak joint angles during stance |
| `symmetry_flags` | string[] | e.g. `step_length_asymmetric_12pct` |
| `shoe_design_recommendations` | object | Rule-derived; see below |
| `confidence_scores.*` | number 0–1 | Per classification |
| `needs_human_review` | boolean (optional) | Set when pathological gait detected (by rule or Anomaly Detector agent) |
| `agent_decisions` | object (optional) | Per-decision record: `source` = `"agent"` or `"static_baseline"`; `confidence` = agent confidence when agent was used, `null` otherwise (Phase 2+) |

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
    "symmetry_flags", "shoe_design_recommendations", "confidence_scores"
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
    "shoe_design_recommendations": {
      "type": "object",
      "required": ["medial_post", "arch_support", "heel_counter", "heel_drop_mm", "last_shape"],
      "additionalProperties": true,
      "properties": {
        "medial_post": { "enum": ["required", "optional", "none"] },
        "post_density": { "enum": ["soft", "medium", "firm"] },
        "arch_support": { "enum": ["low", "medium", "high"] },
        "heel_counter": { "enum": ["flexible", "semi_rigid", "rigid"] },
        "heel_drop_mm": { "type": "number" },
        "cushioning_zone_priority": { "type": "array", "items": { "type": "string" } },
        "last_shape": { "enum": ["straight", "semi_curved", "curved"] }
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

## 7. Versioning policy

- **Additive change** (new optional field) → same version (`profile/v1`).
- **Breaking change** (rename, type change, removed field, changed enum) → new version (`profile/v2`) + a migration note in this doc.
- The downstream shoe-design module pins the schema version it supports.
- `GET /profiles/schema` always returns the schema for the currently deployed version.
