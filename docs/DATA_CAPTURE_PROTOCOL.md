   # Data Capture Protocol (SOP)
## Gait Analysis Module — Operator Procedure

| Field | Value |
|---|---|
| Document | Data Capture Protocol |
| Version | 1.0 |
| Audience | Capture operators, clinicians |
| Related | [ARCHITECTURE.md §Capture Layer](./ARCHITECTURE.md), [DATA_FLOW.md](./DATA_FLOW.md), [PRIVACY_COMPLIANCE.md](./PRIVACY_COMPLIANCE.md) |

This is the step-by-step procedure for recording a subject. Following it precisely is what makes the downstream analysis accurate and repeatable. **When in doubt, re-record — bad capture cannot be fixed in software.**

---

## 1. Room & rig prerequisites (verify before any subject arrives)

| Item | Requirement |
|---|---|
| Walkway length | ≥ 6 m (allows acceleration + 3–4 steady cycles + deceleration) |
| Walkway width | ~1 m, plain **matte** surface (no reflective floor) |
| Lighting | Diffuse, ≥ 500 lux, no harsh shadows on the feet |
| Sagittal camera | Side of walkway, lens ≈ **knee height**, 3–4 m away |
| Posterior camera | Behind walkway, lens ≈ **mid-calf height**, 3–4 m back |
| Plantar camera (if used) | Below transparent treadmill, looking up |
| Frame rate | 60 fps min; **120 fps recommended** for heel-strike timing |
| Resolution | 1080p minimum |
| Shutter | Global shutter preferred (esp. posterior view) |
| Sync | Hardware trigger, or PTP/NTP software sync (≤ ~10 ms drift) |
| Scale reference | Known-length object visible on the walkway |

---

## 2. Calibration (per session day, or whenever a camera moves)

1. **Intrinsic calibration** (one-time per camera unless lens/zoom changes): capture the checkerboard/ChArUco board at multiple angles and distances; store intrinsics under `configs/cameras/`.
2. **Extrinsic calibration:** capture the shared wand or board visible in two views simultaneously; compute relative camera poses.
3. **Scale check:** confirm the known-length reference reads correctly in the calibrated space.
4. Verify undistortion looks correct on a test frame (straight lines stay straight).

> If any camera is bumped or repositioned during the day, **re-run extrinsic calibration** before continuing.

---

## 3. Subject preparation

1. **Consent first.** Record informed consent before any capture (see [PRIVACY_COMPLIANCE.md](./PRIVACY_COMPLIANCE.md)). No consent → no capture.
2. **Clothing:** snug shorts or rolled-up trousers. **Ankles and lower shins must be visible** — this is non-negotiable; long trousers destroy rearfoot-angle accuracy.
3. **Register subject metadata:**
   - Subject ID (pseudonymous)
   - Age, height, weight (mass)
   - Foot length and width (L & R)
   - Dominant side
4. Plan **two conditions:** a **barefoot** trial and a trial in the subject's **current shoes** (shod). The comparison reveals what the existing shoe is doing right/wrong.

---

## 4. Capture sequence

### 4.1 Static calibration trial
- Subject stands still in a neutral anatomical posture for **3 seconds**.
- This is the personal reference used for joint-angle offsets.

### 4.2 Dynamic trials
- **At least 6 walking passes** at the subject's **self-selected** speed.
- The subject walks the full length each pass; turn off-camera and return.
- The system automatically **discards the first and last cycle** of each pass (acceleration/deceleration).
- **Target: ≥ 8 clean gait cycles per foot** across all passes.

### 4.3 Repeat for both conditions
- Run the full set **barefoot**, then **shod** (or vice versa). Keep the conditions clearly labeled in the session.

---

## 5. Live quality checks (during/after capture)

The system reports per-session:
- Number of **clean cycles per foot** that survived confidence gating.
- Any frames where critical keypoints dropped below the confidence threshold.

**Decision rule:**

| Clean cycles per foot | Action |
|---|---|
| ≥ 8 | Good — proceed |
| 4–7 | Acceptable — proceed, but flagged as lower reliability |
| < 4 | **Re-record** — the system will not emit a profile |

For repeatability validation, you may **re-scan the same subject within 30 minutes** (see [VALIDATION_QA.md](./VALIDATION_QA.md)).

---

## 6. Common problems & fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| Rearfoot angle noisy/missing | Trousers covering ankles | Roll up / change to shorts; re-record |
| Subject lost by tracker | Multiple people in frame | Clear the walkway; re-run |
| Background subtraction unstable | Reflective floor / harsh shadows | Matte surface, diffuse lighting |
| Heel-strike timing jittery | Frame rate too low | Use 120 fps |
| Posterior view smearing | Rolling shutter motion artifact | Use global-shutter camera |
| Distances wrong in output | Missing/incorrect scale reference or stale calibration | Re-check scale object; re-run extrinsic calibration |
| Too few clean cycles | Walkway too short / too few passes | Lengthen run-up; add passes |

---

## 7. Pre-flight checklist (print and tick)

**Room & rig**
- [ ] Walkway ≥ 6 m, matte, ~1 m wide
- [ ] Lighting ≥ 500 lux, diffuse, no foot shadows
- [ ] Sagittal cam at knee height, 3–4 m
- [ ] Posterior cam at mid-calf height, 3–4 m
- [ ] Cameras synced; frame rate ≥ 60 (ideally 120) fps
- [ ] Scale reference in view
- [ ] Calibration current (intrinsic + extrinsic verified today)

**Subject**
- [ ] Informed consent recorded
- [ ] Ankles & lower shins visible
- [ ] Metadata entered (ID, age, height, weight, foot L/W, dominant side)

**Capture**
- [ ] 3 s static calibration trial done
- [ ] ≥ 6 dynamic passes, self-selected speed
- [ ] Barefoot condition captured
- [ ] Shod condition captured
- [ ] ≥ 8 clean cycles/foot (or re-record if < 4)

**Wrap-up**
- [ ] Session labeled & uploaded
- [ ] Processing triggered
- [ ] Faces will be blurred post-pipeline (verify privacy step)

---

## 8. What happens next
Once uploaded and processed, the pipeline produces a `profile.json` (see [API_AND_SCHEMA.md](./API_AND_SCHEMA.md)). The clinician reviews curves and classifications in the UI and, if needed, adjusts the recommendation. The faces in stored video are blurred unless explicit retention consent was given.
