# Gait Analysis Module — Build Flow & Dependencies

**This document maps the project flow, task dependencies, and critical decisions.**

---

## 1. High-Level Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                         OPERATOR / PATIENT                           │
│                        (Capture Session)                             │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ↓
            [Subject Registration + Consent]
                         │
                         ↓
    ┌─────────────────────────────────────────────┐
    │   CAPTURE LAYER (Hardware - Phase 0)        │
    │   Sagittal | Posterior | Plantar cameras    │
    │   3-camera synchronized rig                 │
    │   6 m+ matte walkway, ≥ 500 lux diffuse     │
    └────────────┬────────────────────────────────┘
                 │ raw multi-camera video streams
                 ↓
    ┌─────────────────────────────────────────────────────────┐
    │   INGESTION & PREPROCESSING (Phase 1, Week 1-2)        │
    │   Decode → Timestamp align → Undistort → Calibrate     │
    │   Background subtract → Track → ROI crop                │
    └────────────┬────────────────────────────────────────────┘
                 │ clean, undistorted, cropped frames
                 ↓
    ┌────────────────────────────────────────────────────────┐
    │   POSE & FOOT KEYPOINTS (Phase 1, Week 2-3)           │
    │   Tier A: MediaPipe whole-body 2D pose                 │
    │   Tier B: Custom foot keypoints (Phase 2)              │
    │   3D lifting | Temporal smoothing (1-Euro)             │
    └────────────┬───────────────────────────────────────────┘
                 │ time-series of 2D/3D keypoints
                 ↓
    ┌────────────────────────────────────────────────────────┐
    │   GAIT EVENT DETECTION (Phase 1, Week 3-4)            │
    │   HS/TO detection → Cycle segmentation                 │
    │   Stance/swing/sub-phases                              │
    │   Quality gate: drop low-confidence cycles             │
    └────────────┬───────────────────────────────────────────┘
                 │ segmented gait cycles
                 ↓
    ┌────────────────────────────────────────────────────────┐
    │   BIOMECHANICAL ANALYSIS (Phase 1, Week 4-5)          │
    │   Spatiotemporal | Kinematics | Foot-strike            │
    │   Pronation/supination (headline) | Arch type          │
    │   Symmetry indices | Confidence scoring                │
    └────────────┬───────────────────────────────────────────┘
                 │ parameters + classifications
                 ↓
    ┌────────────────────────────────────────────────────────┐
    │   PATIENT PROFILE GENERATOR (Phase 1, Week 5-6)       │
    │   Aggregate cycles → Confidence gating                 │
    │   Apply rules.yaml → Shoe recommendations              │
    │   Emit profile.json (schema-valid)                     │
    └────────────┬───────────────────────────────────────────┘
                 │ profile.json
                 ↓
    ┌────────────────────────────────────────────────────────┐
    │   DOWNSTREAM: SHOE DESIGN MODULE                      │
    │   (Out of scope for this project)                      │
    └─────────────────────────────────────────────────────────┘
```

---

## 2. Phase Delivery Timeline

```
Phase 0 (Setup)              [2 weeks]
├─ Hardware procurement
├─ Walkway construction
├─ Calibration scripts
├─ Repo scaffolding
└─ AI agent infrastructure: src/gait/agents/ + pipeline.yaml agents: section (all disabled)

        ↓

Phase 1 (MVP)                [6-8 weeks]
├─ Ingestion & preprocessing
├─ Pose estimation (MediaPipe)
├─ Event detection
├─ Biomechanical analysis
├─ Profile generator (YAML-driven; all decisions log confidence + reasoning)
├─ API & simple viewer
└─ Full e2e ≤ 60 s

        ↓

Phase 2 (Custom Foot Model + Quality Agent)  [6 weeks]
├─ Dataset curation (3k images)
├─ Annotation pipeline
├─ Model fine-tuning
├─ Fairness validation
└─ Quality Assessment Agent (v1): trained on Phase 1 data; replaces binary cycle gate

        ↓

Phase 3 (3D & Validation + Learning Agents)  [6-8 weeks]
├─ Multi-view triangulation
├─ Pressure-mat validation (n≈30)
├─ Threshold re-tuning
├─ Rules finalization
├─ Threshold Tuning Agent: learns cutoffs from pressure-mat ground truth
├─ Recommendation Agent: learns from Phase 2 clinician overrides
└─ Anomaly Detector: learns pathological patterns from diverse cohort

        ↓

Phase 4 (Productionization + Online Learning)  [ongoing]
├─ Authentication + RBAC
├─ Encryption & compliance
├─ Audit logging (incl. per-agent decision logs)
├─ Monitoring & observability (incl. agent override rates, confidence trends)
├─ Online learning loop: quarterly retrain agents from production feedback
├─ Agent governance dashboard: A/B testing, fairness checks
└─ K8s orchestration
```

---

## 3. Critical Dependencies & Decisions

### 3.1 Phase 0 → Phase 1 Gate

**Must have for Phase 1 start:**
- ✅ Cameras installed, synced, and calibrated.
- ✅ Test video capture works.
- ✅ Calibration outputs (`configs/cameras/*.yaml`) verified.
- ✅ Repo scaffolding complete, CI green.

**Go/No-Go Decision:** Can we record and process test video end-to-end?

### 3.2 Phase 1 → Phase 2 Gate

**Must have for Phase 2 start:**
- ✅ MVP pipeline produces schema-valid `profile.json`.
- ✅ Gating logic works (< 4 cycles → re-record).
- ✅ Processing time ≤ ~60 s.
- ✅ MediaPipe pose provides baseline (albeit coarse foot keypoints).

**Decision:** Foot-keypoint accuracy acceptable for MVP, or must Phase 2 start earlier?

### 3.3 Phase 2 → Phase 3 Gate

**Must have for Phase 3 start:**
- ✅ Custom foot model trained on ~3k annotated images.
- ✅ Rearfoot-angle accuracy visibly improved vs. Phase 1.
- ✅ No systematic bias across skin-tone subgroups.

**Decision:** Is fairness validation complete?

### 3.4 Phase 3 → Phase 4 Gate

**Must have for Phase 4 start:**
- ✅ Validation study complete (n ≈ 30, ICC > 0.85).
- ✅ Thresholds (`configs/thresholds.yaml`) and rules (`configs/rules.yaml`) re-tuned.
- ✅ Orthotist sign-off on recommendation logic.

**Decision:** Are we clinically confident?

---

## 4. Configuration vs. Code (Critical Invariant)

```
┌──────────────────────────────────────┐
│         Application Code             │
│     (src/gait/analysis/*.py)         │
└──────────────────┬───────────────────┘
                   │ computes metrics
                   ↓
┌──────────────────────────────────────────────────┐
│           Threshold Configuration                │
│         (configs/thresholds.yaml)                │
│                                                   │
│ FSA cutoffs: rearfoot_strike_fsa_min_deg: 5     │
│ Pronation: pronation_min_deg: 8                 │
│ Symmetry: asymmetry_flag_threshold_pct: 10      │
│ Confidence gates: keypoint_conf_threshold: 0.5  │
└──────────────────┬───────────────────────────────┘
                   │ classification applied
                   ↓
          [Classification Result]
                   │
                   ↓
┌──────────────────────────────────────────────────┐
│          Recommendation Rules                    │
│         (configs/rules.yaml)                     │
│                                                   │
│ IF pronation=overpronation AND arch=low:       │
│   medial_post: required                        │
│   arch_support: high                           │
│   last_shape: straight                         │
└──────────────────────────────────────────────────┘
```

**Key principle:** No numbers in code. If you're tempted to write `if rearfoot_angle > 8:`, **STOP** — put `pronation_min_deg: 8` in `configs/thresholds.yaml` instead.

---

## 5. Testing Pyramid

```
        ▲
       ███
      █████  E2E (few)
     ███████   → session_dir → profile.json on golden samples
    █████████
      █████   Integration (several)
      █████    → stage → stage with fixture data
    ███████
   █████████
   █████████  Unit (many)
   ███████████  → geometry, classifiers, schema validation
   ███████████
 █████████████
█████████████████
```

**Phase 1 exit:**
- ✅ Unit tests: geometry (rearfoot angle), classifiers (FSA, arch type), schema.
- ✅ Integration tests: pose → events → analysis → profile.
- ✅ E2E tests: 2–3 golden sample sessions end-to-end.

---

## 6. Role Responsibilities (Who Does What?)

| Role | Owns | Example Tasks |
|---|---|---|
| **Hardware Engineer** | Phase 0 rig setup | Cameras, sync, calibration boards |
| **Software Engineer** | Pipeline orchestration | Decode → ingestion → pose → events → analysis → profile |
| **ML Engineer** | Pose & keypoint models | MediaPipe wrapper, custom foot model training |
| **Biomechanist / Clinician** | Accuracy & validation | Define thresholds, tune rules, validate study |
| **Frontend Engineer** | UI & clinician viewer | React app, gait curves, cycle plots |
| **Backend Engineer** | API & storage | FastAPI, Celery, PostgreSQL, S3 integration |
| **QA / Tester** | Validation & quality gates | Test strategy, golden samples, e2e testing |
| **Data Annotator** | Dataset curation (Phase 2) | Label foot keypoints on 3k images |

---

## 7. What Happens When Things Go Wrong

### Scenario 1: Camera falls out of sync mid-session
**Mitigation:** 
- Hardware trigger rig minimizes drift; software sync (PTP/NTP) has ≤ 10 ms tolerance.
- Post-capture: re-run extrinsic calibration before processing.

### Scenario 2: Keypoint confidence drops (e.g., occlusion by clothing)
**Mitigation:**
- Operator protocol mandates ankle/shin visibility (no long trousers).
- Low-confidence cycles are dropped; if < 4 clean cycles/foot survive, gating requests re-record.

### Scenario 3: Rearfoot-angle output is noisy
**Mitigation:**
- Check 1-Euro filter settings in `configs/pipeline.yaml`.
- Validate video quality: proper lighting, steady camera.
- If calibration is stale, re-run extrinsic calibration.

### Scenario 4: Recommendation rules produce incorrect shoe specs
**Mitigation:**
- Orthotist adjusts `configs/rules.yaml` (no code change needed).
- Clinical validation study (Phase 3) tunes thresholds and rules.

### Scenario 5: Schema-breaking API change breaks downstream consumers
**Mitigation:**
- Versioned schemas: `profile/v1` → `profile/v2`.
- Migration notes document the change.
- Backward compatibility maintained for read-only consumers temporarily.

---

## 8. Quick Decision Tree

```
├─ Am I writing a threshold?
│  ├─ YES → Put it in configs/thresholds.yaml, not code ✅
│  └─ NO  → Continue
│
├─ Am I writing recommendation logic?
│  ├─ YES → Put it in configs/rules.yaml, not code ✅
│  └─ NO  → Continue
│
├─ Am I changing the profile.json schema?
│  ├─ YES → Update src/gait/profile/schema.py AND docs/API_AND_SCHEMA.md ✅
│  └─ NO  → Continue
│
├─ Am I dropping data without logging?
│  ├─ YES → Log it; surface to operator ✅
│  └─ NO  → Continue
│
├─ Am I storing raw video without encrypting?
│  ├─ YES → Encrypt at rest ✅
│  └─ NO  → Continue
│
├─ Am I mixing L/R naming conventions?
│  ├─ YES → Use {"L": ..., "R": ...} everywhere ✅
│  └─ NO  → Continue
│
├─ Am I writing an agent that hard-fails the pipeline when it errors?
│  ├─ YES → Wrap in try/except; fall back to static baseline ✅
│  └─ NO  → Continue
│
├─ Am I shipping an agent without comparing to the static baseline?
│  ├─ YES → Run held-out accuracy comparison first; agent must be ≥ baseline ✅
│  └─ NO  → Continue
│
└─ Am I enabling an agent without logging its decisions?
   ├─ YES → Add structured log: agent_name, input, output, confidence ✅
   └─ NO  → You're good!
```

---

## 9. Checklist: "Ready to Deploy to Production"

### Compliance & Privacy
- [ ] Informed consent recorded for every subject.
- [ ] Faces blurred post-pipeline (default).
- [ ] Video encrypted at rest.
- [ ] Profile pseudonymized (patient_id, identity mapping separate).
- [ ] RBAC enforced (clinician, shoe designer, admin roles).
- [ ] Audit logging on every profile read.
- [ ] Data retention policy configured with auto-purge.

### Clinical Validation
- [ ] ICC > 0.85 vs. ground truth on headline metrics.
- [ ] Rearfoot-angle repeatability SD < 2°.
- [ ] Stance-time repeatability SD < 5°.
- [ ] Thresholds and rules tuned from validation study.
- [ ] Orthotist sign-off on recommendations.

### Code Quality
- [ ] 100% of emitted profiles schema-valid.
- [ ] All tests green (unit, integration, e2e).
- [ ] Lint, type check, formatter pass.
- [ ] CI/CD pipeline configured.
- [ ] Documentation up-to-date (docs/ folder synced with code).

### Performance & Observability
- [ ] Processing time ≤ ~60 s per session on reference machine.
- [ ] Monitoring dashboards live (per-stage timings, confidence drift, dropped-cycle rate).
- [ ] Alerting configured (e.g., rerecord rate spike).
- [ ] Model drift review cadence established (quarterly).

### Operations
- [ ] Runbook written for operators.
- [ ] Capture protocol checklist ready.
- [ ] On-call rotation defined.
- [ ] Backup / disaster recovery tested.
- [ ] Kubernetes manifests (or Compose) versioned and tested.

---

## 10. Success Signals (How You'll Know It's Working)

### Week 0–2 (Phase 0 ramp)
✅ Hardware installed, calibrated, test video records successfully.

### Week 2–10 (Phase 1)
✅ End-to-end pipeline runs; `profile.json` emitted in ≤ 60 s.  
✅ Gating works: reject < 4 cycles/foot.  
✅ Clinician UI renders curves and classifications.

### Week 10–16 (Phase 2)
✅ Custom foot model trained on 3k images; rearfoot-angle accuracy improved.

### Week 16–24 (Phase 3)
✅ Validation study complete; ICC > 0.85 achieved.  
✅ Thresholds and rules finalized with orthotist.

### Week 24+ (Phase 4)
✅ Live in clinic: subjects being scanned, profiles generated, orthotists using recommendations.  
✅ Monitoring shows stable processing times, low re-record rate.  
✅ Quarterly model reviews in place; no fairness regressions detected.

---

**Next Steps:**
1. **Assemble the core team** — hardware engineer, ML engineer, software engineer, clinician.
2. **Review this playbook together** — agree on phase gates and decision criteria.
3. **Kick off Phase 0** — order cameras, set up calibration boards, scaffold repo.
4. **Establish a weekly sync** — track progress against milestones.
5. **Document decisions** — as choices are made (threshold values, rule tuning), record them and why.

Good luck! 🚀
