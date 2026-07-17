# Validation, Calibration & QA
## Gait Analysis Module — Quality Plan

| Field | Value |
|---|---|
| Document | Validation & QA |
| Version | 1.0 |
| Related | [PRD.md §Success metrics](./PRD.md), [ARCHITECTURE.md](./ARCHITECTURE.md), [DATA_CAPTURE_PROTOCOL.md](./DATA_CAPTURE_PROTOCOL.md) |

This document covers two kinds of quality: **clinical validation** (is the measurement true?) and **software QA** (does the code behave?). Both must pass before a profile is trusted.

---

## 1. Clinical validation

### 1.1 Ground truth
Validate the CV pipeline against trusted references wherever possible:
- **Pressure mat** (Tekscan / RSScan) — gold standard for event timing and foot strike.
- **Clinician manual rearfoot-angle measurement** — goniometer or careful video review.
- **IMU on shank** (optional) — to cross-check rearfoot-angle calculation.

### 1.2 Agreement target
- Inter-method agreement: **ICC > 0.85** between the pipeline and ground truth for the headline metrics (event timing, foot-strike pattern, rearfoot angle).
- Report Bland–Altman plots (bias + limits of agreement) for continuous metrics like rearfoot angle and stance time.

### 1.3 Repeatability
- Re-scan the same subject **twice within 30 minutes**.
- Parameter SD must stay below clinically meaningful thresholds:
  - **Rearfoot angle SD < 2°**
  - **Stance-time SD < 5%**
- If repeatability fails, investigate calibration, lighting, and keypoint stability before trusting output.

### 1.4 Validation study (Phase 3)
- Recruit **n ≈ 30 subjects** spanning arch types, pronation classes, skin tones, and foot morphologies.
- Run barefoot + shod, with simultaneous pressure-mat capture.
- Use results to **re-tune thresholds** in `configs/thresholds.yaml` and finalize recommendation rules in `configs/rules.yaml`.

---

## 2. Confidence gating (runtime QA)

The pipeline must refuse to fabricate results from poor data.

| Gate | Rule | On failure |
|---|---|---|
| Keypoint confidence | Per-frame critical-keypoint confidence ≥ threshold | Drop the affected cycle |
| Clean-cycle floor | ≥ 4 clean cycles per foot | Request re-record; emit **no** profile |
| Clean-cycle target | ≥ 8 clean cycles per foot | Below target → proceed but flag lower reliability |
| Pathological gait | Detected abnormal pattern | Set `needs_human_review`; do not auto-finalize recommendations |

All gates are configured in `configs/thresholds.yaml` (see [API_AND_SCHEMA.md](./API_AND_SCHEMA.md)).

---

## 3. Calibration QA

- Verify intrinsic calibration: straight physical lines remain straight after undistortion.
- Verify extrinsic calibration: triangulated 3D points of a known object match its real geometry within tolerance.
- Verify scale: the known-length reference reads correctly in calibrated space.
- Re-run extrinsic calibration whenever a camera is moved.

---

## 4. Software test strategy

A test pyramid keeps the pipeline trustworthy as it evolves.

```
        ▲  E2E (few)        session_dir → profile.json on golden samples
       ▲▲▲ Integration      stage → stage with fixture keypoints/cycles
      ▲▲▲▲ Unit (many)      geometry, angle math, classifiers, schema
```

### 4.1 Unit tests (`tests/unit/`)
- **Geometry/math:** rearfoot-angle computation, FSA, symmetry index formula — assert exact values on hand-computed inputs.
- **Classifiers:** feed synthetic angles straddling each threshold boundary; assert the correct class on both sides of every cutoff.
- **Schema:** every emitted profile validates against `profile/v1`.
- **Smoothing/signal:** filters do not shift event-frame timing beyond tolerance.

### 4.2 Integration tests (`tests/integration/`)
- Pose output → event detection: known keypoint series yields expected HS/TO frames.
- Event output → analysis: known segmented cycles yield expected spatiotemporal values.
- Analysis → profile: known parameter vectors yield the expected recommendation block under a fixed `rules.yaml`.

### 4.3 End-to-end tests (`tests/e2e/`)
- A small set of **golden sample sessions** (short recorded clips with known expected output) run through the full pipeline.
- Assert: profile is schema-valid, classifications match expected, processing completes within the time budget on the reference machine.

### 4.4 Regression guard
- Golden-sample outputs are snapshotted. A code or model change that shifts a classification or a key numeric beyond tolerance fails CI and requires explicit sign-off.

### 4.5 Rearfoot alignment & foot progression angle fixes (July 2026)

**New measurement modes & gates:**
- **Static posterior photo rearfoot alignment:** Validate against clinician manual goniometer measurement on standing photos; ICC ≥ 0.90 target.
- **Walking video fallback with outlier rejection:** Confirm median + rejection threshold (20°) produces tighter, more stable estimates than raw mean. Validate against pressure-mat rearfoot angle ICC; target ≥ 0.85.
- **Foot progression angle camera filtering:** Restrict to sagittal/anterior only; verify posterior-only frames are rejected in mixed-camera setups; confirm no FPA values outside ±45° pass the plausibility gate.

**Test additions:**
- Unit test: `compute_rearfoot_alignment_from_image()` on a synthetic full-body image with known ankle/heel positions; verify angle is bounded within ±30° and method is logged as `"static_image"`.
- Unit test: median + outlier rejection on a midstance angle series with simulated jitter; verify surviving frame count ≥ 5 and outliers are logged.
- Unit test: foot progression angle with sagittal camera frames; verify non-sagittal frames are excluded and `camera_used` is logged.
- Integration test: walking video + static photo session; verify static photo method is preferred; verify fallback to walking video when static photo yields no pose.

---

## 5. Acceptance criteria (gate to "trusted")

A build is acceptable only if **all** hold:

| Criterion | Target |
|---|---|
| Unit + integration + e2e tests | Green |
| Schema validation of all emitted profiles | 100% |
| ICC vs. ground truth (headline metrics) | > 0.85 |
| Rearfoot-angle repeatability SD | < 2° |
| Stance-time repeatability SD | < 5% |
| Processing time (reference machine, 6-pass session) | ≤ ~60 s |
| Re-record gating works | < 4 cycles/foot → no profile emitted |
| Fairness check | No systematic accuracy drop across skin-tone subgroups in the validation set |

---

## 6. Model quality & drift

- **Foot-keypoint model:** track keypoint localization error (e.g., PCK / mean pixel error) on a held-out, diverse test set.
- **Drift review:** schedule a **quarterly review** of the foot-keypoint model as annotated data accumulates; retrain when error or bias regresses.
- **Model cards:** each model ships a `MODEL_CARD.md` (training data summary, known limitations, fairness notes) under `models/`.

---

## 7. Observability (continuous QA in production)

Log and monitor:
- Per-stage timings (catch performance regressions).
- Confidence-score distributions (detect capture-quality drift).
- Dropped-cycle and re-record rates (detect protocol or hardware issues).
- Clinician override rate on recommendations (signals rules needing tuning).

---

## 8. Sign-off

A session profile is considered clinically usable when:
1. It passed all runtime gates (no re-record condition).
2. The relevant build met the acceptance criteria above.
3. If `needs_human_review` is set, a clinician has reviewed and confirmed/adjusted it.

---

## 9. AI agent validation (Phase 2+)

Before any AI agent is promoted to production, it must clear a dedicated validation gate separate from the software QA pipeline.

### 9.1 Baseline comparison (required for all agents)

| Step | Requirement |
|---|---|
| Hold-out evaluation | Agent tested on a held-out set **not** used for training |
| Accuracy vs. static | Agent accuracy ≥ static YAML baseline; if not, do not deploy |
| Confidence calibration | Agent confidence scores must be well-calibrated (high confidence ↔ high accuracy) |
| Fairness check | No systematic accuracy drop across skin-tone, arch-type, or demographic subgroups |

### 9.2 Agent-specific validation targets

| Agent | Ground truth | Target |
|---|---|---|
| Quality Assessment Agent | Manual session quality labels | Accuracy ≥ static binary gate on held-out sessions |
| Threshold Tuning Agent | Pressure-mat classification labels (Phase 3 study) | ICC with pressure mat ≥ static threshold ICC |
| Recommendation Agent | Clinician override history | Agreement with orthotist ≥ static rules.yaml agreement |
| Anomaly Detector | Manually labeled anomalous sessions | Recall ≥ 0.90, false positive rate ≤ 0.10 |

### 9.3 Agent governance workflow

1. **Train** agent on approved dataset.
2. **Evaluate** vs. static baseline on held-out data.
3. **Fairness check** — disaggregated metrics per subgroup.
4. **PR review** includes model card + evaluation report.
5. **Deploy** by updating `pipeline.yaml` model version + model file.
6. **Monitor** override rate and confidence distribution in production.
7. **Rollback** if override rate spikes (indicates clinician distrust) — revert `pipeline.yaml`.

### 9.4 Continuous agent monitoring

Log and alert on:
- Per-agent confidence distribution (detect model degradation).
- Per-agent override rate by clinicians (detect trust issues).
- Accuracy drift vs. held-out set (quarterly recalculation).
- Fairness drift across subgroups (re-run disaggregated evaluation quarterly).
