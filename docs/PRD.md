# Product Requirements Document (PRD)
## Gait Analysis Module for Customized Orthopedic Footwear

| Field | Value |
|---|---|
| Document | PRD |
| Version | 1.0 |
| Status | Draft for build |
| Related | [ARCHITECTURE.md](./ARCHITECTURE.md), [API_AND_SCHEMA.md](./API_AND_SCHEMA.md), [ROADMAP.md](./ROADMAP.md) |

---

## 1. Overview

### 1.1 Vision
Make clinically-grounded, customized orthopedic footwear accessible and affordable by replacing expensive, marker-based motion-capture labs with a **markerless, camera-only gait analysis system** that produces a structured, machine-readable patient profile.

### 1.2 Problem statement
Customized orthopedic footwear today depends on either (a) subjective clinician observation, which is inconsistent and operator-dependent, or (b) marker-based gait labs and pressure plates, which are expensive, slow, and inaccessible outside large hospitals. There is no affordable, repeatable, automated bridge between *capturing how a person walks* and *designing a shoe for them*.

### 1.3 Solution summary
A computer-vision pipeline that:
1. Records a subject walking using ordinary cameras (no body markers).
2. Extracts biomechanical parameters automatically.
3. Classifies foot-strike and pronation/supination behavior.
4. Emits a structured **patient profile JSON** that the shoe-design module consumes directly — so the shoe designer never has to re-examine the video.

### 1.4 Where this module sits
This is **Stage 1** of a larger pipeline. Its single deliverable — `profile.json` — is the contract handed to the downstream **Shoe Design Module** (last design, midsole geometry, medial post, arch support). Everything in this PRD stops at the boundary of that JSON.

---

## 2. Goals & non-goals

### 2.1 Goals (v1 prototype)
- **G1** — Capture a walking subject with an affordable multi-camera rig.
- **G2** — Produce all standard spatiotemporal gait parameters automatically.
- **G3** — Classify pronation/supination per foot, with a confidence score. *(headline metric)*
- **G4** — Classify foot-strike pattern (rearfoot / midfoot / forefoot) per foot.
- **G5** — Estimate arch type per foot.
- **G6** — Compute bilateral symmetry indices and flag clinically meaningful asymmetry.
- **G7** — Emit a validated `profile.json` conforming to a fixed schema.
- **G8** — Generate a first-pass, rule-based shoe-design recommendation block.
- **G9** — Return results within ~60 seconds of capture completion.
- **G10** — Comply with India's DPDP Act 2023 for handling sensitive health video.

### 2.2 Non-goals (explicitly out of scope for v1)
- **NG1** — Plantar pressure mapping (deferred to v2; possible pressure-mat fusion).
- **NG2** — Running gait analysis (focus is walking only).
- **NG3** — Pathological / neurological gait *diagnosis*. The system **refers**, it does not diagnose.
- **NG4** — Manufacturing the shoe (handled downstream).
- **NG5** — Real-time / live overlay during walking (batch processing is acceptable for v1).
- **NG6** — Mobile / phone-only capture (controlled-room capture first; ruggedization later).

---

## 3. Target users & personas

| Persona | Role | What they need from the module |
|---|---|---|
| **Orthotist / Clinician** | Assesses the patient, reviews output, tunes rules | Trustworthy parameters, clear visualizations, ability to override and adjust recommendation rules |
| **Capture Operator** | Runs the recording sessions | A simple, reliable capture protocol and clear "re-record" prompts when data is bad |
| **Shoe Designer** | Consumes `profile.json` downstream | A stable, well-documented schema; never wants to touch raw video |
| **System Admin / Engineer** | Deploys & maintains the system | Reproducible deployment, monitoring, model-retraining workflow |
| **Patient / Subject** | The person being analyzed | Privacy, consent, a quick and non-invasive session |

---

## 4. User stories

### Capture & analysis
- As an **operator**, I can register a subject (ID, age, height, weight, foot dimensions, dominant side) before capture.
- As an **operator**, I can run a static calibration trial and at least 6 dynamic walking passes.
- As an **operator**, I am told immediately if too few clean gait cycles survived and I need to re-record.
- As the **system**, I automatically discard acceleration/deceleration cycles from each pass.

### Results & review
- As a **clinician**, I can view spatiotemporal parameters with mean ± SD across cycles.
- As a **clinician**, I can see the pronation/supination classification per foot with its confidence score.
- As a **clinician**, I can view gait curves and side-by-side left/right cycle plots.
- As a **clinician**, I can compare barefoot vs. shod trials.
- As a **clinician**, I can override a recommendation and adjust the underlying rules.

### Output & integration
- As the **system**, I emit a `profile.json` validated against the published schema.
- As a **shoe designer**, I receive a recommendation block (medial post, arch support, heel counter, heel drop, cushioning zones, last shape) derived from the analysis.
- As an **integrator**, I can rely on the schema being versioned and backward-compatible.

### Privacy
- As a **patient**, I give informed consent before capture and can request deletion.
- As the **system**, I blur faces in stored video once the pipeline has run.

---

## 5. Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-1 | Ingest synchronized multi-camera video and timestamp-align frames | Must |
| FR-2 | Undistort and calibrate frames using stored intrinsics/extrinsics | Must |
| FR-3 | Isolate and track the subject (background subtraction + person tracking) | Must |
| FR-4 | Estimate whole-body 2D pose keypoints | Must |
| FR-5 | Estimate dedicated foot keypoints (calcaneus, malleoli, MTP heads, hallux, mid-Achilles) | Must |
| FR-6 | Reconstruct 3D keypoints (multi-view triangulation) or lift monocular 2D→3D | Should |
| FR-7 | Smooth keypoint trajectories without destroying event signals | Must |
| FR-8 | Detect heel-strike and toe-off events robustly | Must |
| FR-9 | Segment gait cycles into stance/swing and sub-phases | Must |
| FR-10 | Compute spatiotemporal parameters per cycle and aggregate (mean ± SD) | Must |
| FR-11 | Compute joint-angle kinematics across the cycle | Should |
| FR-12 | Classify foot-strike pattern from foot-strike angle at HS | Must |
| FR-13 | Compute rearfoot angle and classify pronation/supination at mid-stance | Must |
| FR-14 | Estimate arch type (arch height index and/or wet-footprint method) | Must |
| FR-15 | Compute bilateral symmetry indices and flag asymmetry > 10% | Must |
| FR-16 | Generate confidence scores for key classifications | Must |
| FR-17 | Apply editable, rule-based shoe-design recommendation mapping (YAML) | Must |
| FR-18 | Emit schema-valid `profile.json` | Must |
| FR-19 | Provide a clinician-facing viewer (curves, cycle plots, playback) | Should |
| FR-20 | Support barefoot vs. shod comparison | Should |
| FR-21 | Drop low-confidence cycles and require re-record below a cycle threshold | Must |
| FR-22 | Log every pipeline decision with a `confidence` score and `reasoning` dict (enables agent training data from day 1) | Must |
| FR-23 | Support optional AI agent overrides at threshold classification and recommendation stages; static YAML baseline always computed first and used as fallback when agent is disabled or low-confidence (Phase 2+) | Should |
| FR-24 | Provide an agent management endpoint (`GET /agents/status`) to inspect which agents are enabled and which model versions are active (Phase 3+) | Could |

---

## 6. Non-functional requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-1 | **Performance** | End-to-end processing ≤ ~60 s for a standard 6-pass session on the reference machine |
| NFR-2 | **Accuracy** | Inter-method agreement ICC > 0.85 vs. ground truth (pressure mat / goniometer) |
| NFR-3 | **Repeatability** | Same-subject re-scan within 30 min: rearfoot-angle SD < 2°, stance-time SD < 5% |
| NFR-4 | **Reliability** | If < 4 clean cycles per foot survive, fail loudly and request re-record |
| NFR-5 | **Privacy** | Treat all captures as sensitive personal health data; DPDP 2023 compliant |
| NFR-6 | **Security** | Encrypt video at rest; signed URLs for retrieval; role-based access; audit logging |
| NFR-7 | **Fairness** | Custom foot model trained on diverse skin tones and Indian foot morphology |
| NFR-8 | **Reproducibility** | Containerized; deterministic given same input + model versions |
| NFR-9 | **Maintainability** | Recommendation rules editable without code changes (YAML); agents deployable by updating `pipeline.yaml` model version only |
| NFR-10 | **Observability** | Log per-stage timings, confidence distributions, and dropped-cycle counts |
| NFR-11 | **Portability** | Runs on a single workstation for the prototype; container-orchestratable later |
| NFR-12 | **Usability** | Operator can run a full session with minimal training and clear prompts |

---

## 7. Scope boundaries

### In scope (v1)
Markerless 2D/3D pose & foot-keypoint estimation · gait cycle segmentation · spatiotemporal parameters · foot-strike classification · pronation/supination quantification · bilateral symmetry · arch type estimation · JSON patient profile · rule-based recommendation block.

### Out of scope (v1)
Plantar pressure mapping · running gait · pathological diagnosis · shoe manufacturing · live real-time overlay · phone-only capture.

---

## 8. Success metrics

| Metric | Target |
|---|---|
| Processing time per session | ≤ ~60 s |
| Pronation classification agreement with clinician | ICC > 0.85 |
| Rearfoot-angle repeatability (SD) | < 2° |
| Stance-time repeatability (SD) | < 5% |
| Clean-cycle yield per session | ≥ 8 cycles per foot target; ≥ 4 minimum |
| Schema validation pass rate of emitted profiles | 100% |
| Operator re-record rate (after training) | Low and trending down |
| Clinician trust / override rate | Tracked; recommendation rules tuned to reduce avoidable overrides; Phase 3 Recommendation Agent learns from override history |
| Agent confidence (Phase 2+) | Mean agent confidence ≥ 0.75 across production sessions |
| Agent override rate by clinician (Phase 2+) | Tracked per agent; target < 20% (signals high clinician agreement) |

---

## 9. Assumptions

- Capture happens in a **controlled room** with stable lighting for v1.
- Subjects can walk unaided at a self-selected speed.
- The protocol mandating **ankle/lower-shin visibility** is followed (no long trousers).
- A reference workstation with a capable GPU is available for the prototype.
- A clinician/orthotist is available to validate output and tune rules.

---

## 10. Dependencies

| Dependency | Used for | Notes |
|---|---|---|
| Multi-camera hardware + sync rig | Capture | See [DATA_CAPTURE_PROTOCOL.md](./DATA_CAPTURE_PROTOCOL.md) |
| Pose-estimation models (MediaPipe / RTMPose / HRNet) | Keypoints | Off-the-shelf for MVP; custom foot model later |
| Annotated foot-keypoint dataset (~2–5k images) | Custom model | Key prototype investment; diversity required |
| Pressure mat / goniometer | Validation ground truth | See [VALIDATION_QA.md](./VALIDATION_QA.md) |
| Downstream Shoe Design Module | Consumes `profile.json` | Schema is the contract |

---

## 11. Risks (summary)

See [ARCHITECTURE.md §Known Limitations](./ARCHITECTURE.md) for detail. Headline risks:
- Clothing occlusion destroying rearfoot accuracy → protocol mandates ankle visibility.
- Skin-tone bias in off-the-shelf models → diverse custom dataset.
- Treadmill vs. overground gait differences → validate if a treadmill plantar view is adopted.
- Too few cycles per session → multi-pass protocol + re-record gating.
- Pathological gait → human review required; never auto-finalize.

---

## 12. Release definition — "Done" for the prototype

A deployable module that, given 6 walking passes, returns within ~60 s a `profile.json` containing:
1. All standard spatiotemporal gait parameters.
2. A clinically interpretable pronation/supination classification per foot, with confidence.
3. A foot-strike pattern classification per foot.
4. An arch type estimate per foot.
5. A symmetry assessment.
6. A first-pass shoe-design recommendation block.

That JSON is the contract with the rest of the orthopedic footwear system.
