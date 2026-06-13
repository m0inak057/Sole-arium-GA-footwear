# Task 2: Pipeline Schema & Stubs — Completion Summary

**Status:** ✓ COMPLETE  
**Date:** 2026-06-10  
**Phase:** Phase 1 (MVP Pipeline)  
**Duration:** 1 session  

---

## Executive Summary

Task 2 establishes the **data contract** and **configuration architecture** for the entire pipeline. The schema is the "source of truth" that all downstream stages depend on. Configuration loaders implement the "config-over-code" philosophy.

---

## Deliverables Completed

### 1. Pydantic Patient Profile Schema ✓

**File:** `src/gait/profile/schema.py` (450+ lines)

**Complete schema with:**
- ✓ `GaitPatientProfile` — Main output contract (10 required fields + optional metadata)
- ✓ Nested models:
  - `Anthropometrics` (height, mass, foot dimensions)
  - `Spatiotemporal` (cadence, speed, stride/step, stance/swing, double-support)
  - `FootStrike` (pattern, foot-strike angle)
  - `Pronation` (rearfoot angle, classification, time-to-peak-eversion)
  - `Arch` (type, arch height index)
  - `ShoeDesignRecommendations` (medial post, density, support, counter, heel drop, shape)

- ✓ Enums (type-safe):
  - `FootStrikePattern` (rearfoot, midfoot, forefoot)
  - `PronationClassification` (overpronation, mild_pronation, neutral, mild_supination, oversupination)
  - `ArchType` (high, normal, low)
  - `MedialPostType`, `PostDensityType`, `ArchSupportType`, `HeelCounterType`, `LastShapeType`

- ✓ Utility models:
  - `LRPair` — Enforces left/right notation (no mixed naming)
  - `LRString` — For L/R classifications

- ✓ Validation:
  - Confidence scores must be 0-1
  - L/R pairs must have both keys
  - All required fields enforced
  - JSON schema generation ready

**Why this matters:** The schema is the single source of truth. All code that computes parameters must output data matching this schema. No ambiguity about field names, types, or units.

---

### 2. Configuration Loaders ✓

**File:** `src/gait/pipeline/config.py` (250+ lines)

**Pydantic config models:**
- ✓ `ThresholdsConfig` (foot-strike, pronation, arch, symmetry, quality-gating thresholds)
- ✓ `PipelineConfig` (ingestion, pose, event detection parameters)
- ✓ `RecommendationRulesConfig` (rule version + rule list)

**Loader functions:**
- ✓ `load_thresholds(config_path)` — Loads `configs/thresholds.yaml`
- ✓ `load_pipeline_config(config_path)` — Loads `configs/pipeline.yaml`
- ✓ `load_recommendation_rules(config_path)` — Loads `configs/rules.yaml`
- ✓ `load_camera_config(camera_name, config_path)` — Loads camera calibration YAML

**Features:**
- ✓ Environment-variable support (CONFIGS_DIR)
- ✓ Graceful defaults (returns default config if file missing)
- ✓ YAML parsing with pydantic validation
- ✓ Extensible (extra fields allowed for future additions)

**Why this matters:** All tunable parameters are loaded from YAML at runtime. No magic numbers in code. Clinicians/orthotists can adjust thresholds and rules without code changes.

---

### 3. Abstract Interfaces & Base Classes ✓

**File:** `src/gait/common/interfaces.py` (350+ lines)

**Data classes:**
- ✓ `Frame` — Video frame with image, timestamp, camera view
- ✓ `Keypoint` — 2D/3D point with confidence
- ✓ `KeypointFrame` — Frame with detected keypoints
- ✓ `GaitEvent` — Gait event (heel-strike, toe-off)
- ✓ `GaitCycle` — Complete gait cycle with frames and parameters

**Abstract interfaces (ABC):**
- ✓ `VideoSource` — Video input abstraction (files, hardware, streams, synthetic)
- ✓ `PoseDetector` — Pose detection (MediaPipe, OpenPose, custom)
- ✓ `KeypointSmoother` — Smoothing/filtering (1-Euro, Kalman, etc.)
- ✓ `EventDetector` — Gait event detection (HS/TO, cycle segmentation)
- ✓ `BiomechanicalAnalyzer` — Parameter computation
- ✓ `ProfileBuilder` — Profile JSON assembly + validation
- ✓ `GatingEngine` — Quality control (RERECORD, PROCEED_OK, WARNING)
- ✓ `RecommendationEngine` — Shoe design recommendations

**Why this matters:** Each stage of the pipeline has a clear contract. Different implementations can be swapped (e.g., MediaPipe → custom model) without breaking the pipeline. Perfect for testing (mock implementations) and hardware integration.

---

### 4. YAML Configuration Files ✓

**File:** `configs/thresholds.yaml` (70 lines)
- ✓ Foot-strike angle thresholds (rearfoot, midfoot, forefoot)
- ✓ Pronation angle thresholds (5 classes)
- ✓ Arch height index thresholds
- ✓ Symmetry detection threshold
- ✓ Quality gating (min confidence, min cycles, target cycles)
- ✓ Smoothing parameters (1-Euro filter)
- ✓ Event detection thresholds

**File:** `configs/rules.yaml` (100+ lines)
- ✓ 10 example rules covering:
  - Overpronation + low arch → firm support
  - Mild pronation + normal arch → conservative
  - Neutral → standard
  - Oversupination + high arch → lateral cushioning
  - Forefoot striker → reduced heel drop
  - Rearfoot striker → standard heel drop
  - High asymmetry → flag for review
  - Early peak eversion → firm support
  - Pathological gait → mandatory review
  - Pediatric adjustments → moderate support

**File:** `configs/pipeline.yaml` (70 lines)
- ✓ Ingestion (FPS, resolution, sync tolerance, tracking model)
- ✓ Pose (model choice, confidence, smoothing)
- ✓ Event detection (thresholds)
- ✓ Analysis (kinematics, symmetry)
- ✓ Profile (schema version, metadata)
- ✓ Features (multi-view 3D, pressure-mat, custom models, face-blur)
- ✓ Performance (timeouts, batch processing)
- ✓ Development (mock video, synthetic data, skip gates)

**Why this matters:** All three configs are loaded at runtime. Changes can be made without redeploying code. Orthotists can adjust rules directly. Clinicians can tune thresholds based on patient population.

---

### 5. Synthetic Test Fixtures ✓

**File:** `tests/fixtures/synthetic_data.py` (350+ lines)

**SyntheticGaitGenerator class:**
- ✓ `generate_keypoint_trajectory()` — Sinusoidal keypoint motion with noise
- ✓ `generate_keypoint_frame()` — Single frame with 14 realistic keypoints
- ✓ `generate_keypoint_frames()` — Multi-camera, multi-frame sequences
- ✓ `generate_gait_cycle()` — Complete gait cycle with keypoints + stance/swing phases
- ✓ `generate_synthetic_profile()` — Full patient profile for any gait type

**Convenience fixtures:**
- ✓ `synthetic_frames_normal_gait()` — Normal gait frames
- ✓ `synthetic_profile_neutral()` — Neutral pronation profile
- ✓ `synthetic_profile_overpronation()` — Overpronation profile

**Features:**
- ✓ Generates 120 fps video data
- ✓ Realistic kinematic patterns (sine/cosine motions)
- ✓ Configurable noise
- ✓ Multi-camera support
- ✓ Matches schema exactly (ready to validate)

**Why this matters:** Developers can test the pipeline without hardware. Phase 1 work can proceed in parallel with hardware setup. Continuous integration tests don't need real video.

---

### 6. Comprehensive Unit Tests ✓

**File:** `tests/unit/test_schema.py` (350+ lines)

**Tests:**
- ✓ LRPair validation (requires both L and R)
- ✓ FootStrike validation (all pattern types)
- ✓ Pronation validation (all 5 classifications)
- ✓ Arch validation (all 3 types)
- ✓ Recommendations validation (all enum values)
- ✓ Complete profile validation (valid + invalid cases)
- ✓ Confidence score validation (0-1 bounds)
- ✓ JSON serialization

**Coverage:** 15+ test cases

**File:** `tests/unit/test_config.py` (250+ lines)

**Tests:**
- ✓ Load thresholds from YAML
- ✓ Load pipeline config with defaults
- ✓ Load recommendation rules
- ✓ Partial overrides (custom + defaults)
- ✓ Missing files (graceful fallbacks)
- ✓ Pydantic validation
- ✓ Extra fields allowed (flexibility)

**Coverage:** 12+ test cases

**Why this matters:** Schema and config validation are tested. Developers can't accidentally break the contract. Tests serve as examples of how to use the APIs.

---

## Key Architecture Decisions

### 1. L/R Naming Convention Enforced
```python
# ✓ Correct (enforced by schema)
pattern={"L": FootStrikePattern.REARFOOT, "R": FootStrikePattern.MIDFOOT}

# ✗ Wrong (rejects at validation time)
pattern={"left": ..., "right": ...}  # Will fail
pattern={"L": ..., "R": ...} + {"R": ...}  # Missing L fails
```

**Why:** Prevents L/R mixing bugs. One convention throughout codebase.

### 2. Enums for Classifications
```python
# ✓ Type-safe
pronation: {"L": PronationClassification.OVERPRONATION, ...}

# ✗ String-based (error-prone)
pronation: {"L": "overpronation", ...}
```

**Why:** IDE autocomplete, compile-time checking, no typos.

### 3. Configuration Interfaces vs. Hardcoding
```python
# ✓ Config-over-code
thresholds = load_thresholds()
if rearfoot_angle > thresholds.pronation.overpronation_min_deg:
    classify = PronationClassification.OVERPRONATION

# ✗ Hardcoded (no flexibility)
if rearfoot_angle > 8.0:  # Magic number
    classify = "overpronation"  # String literal
```

**Why:** Clinical teams can tune thresholds without touching code.

### 4. Abstract Interfaces for Swappable Implementations
```python
# ✓ Plug-and-play
class PoseDetector(ABC):
    @abstractmethod
    def detect(self, frame: Frame) -> KeypointFrame: pass

# Implementation 1 (Phase 1): MediaPipe
class MediaPipePoseDetector(PoseDetector):
    def detect(self, frame): ...

# Implementation 2 (Phase 2): Custom model
class CustomPoseDetector(PoseDetector):
    def detect(self, frame): ...

# Same pipeline code works with either:
detector = MediaPipePoseDetector()  # or CustomPoseDetector()
keypoints = detector.detect(frame)
```

**Why:** Can switch models without rewriting pipeline code.

---

## What's Ready for Phase 1B

### Immediately Usable:
- ✓ Schema — all input/output contracts defined
- ✓ Config loaders — YAML loading works
- ✓ Interfaces — all pipeline stages have contracts
- ✓ Synthetic data — developers can test without hardware
- ✓ Tests — validation framework in place

### Phase 1B Work (Weeks 3-8):
- [ ] Implement `src/gait/ingestion/` (video decode, preprocessing)
- [ ] Implement `src/gait/pose/` (MediaPipe wrapper)
- [ ] Implement `src/gait/events/` (HS/TO detection, cycle segmentation)
- [ ] Implement `src/gait/analysis/` (parameter computation)
- [ ] Implement `src/gait/profile/builder.py` (profile assembly + rules)
- [ ] Implement `src/gait/api/main.py` (FastAPI routes)
- [ ] Wire together in `src/gait/pipeline/run.py`

All implementations will inherit from interfaces, load configs, and output schema-valid data.

---

## Files Created

| File | Lines | Purpose |
|------|-------|---------|
| `src/gait/profile/schema.py` | 450 | Patient profile Pydantic models |
| `src/gait/pipeline/config.py` | 250 | Config loaders (YAML → Python) |
| `src/gait/common/interfaces.py` | 350 | Abstract pipeline interfaces |
| `configs/thresholds.yaml` | 70 | Tunable classification thresholds |
| `configs/rules.yaml` | 100 | Orthopedic recommendation rules |
| `configs/pipeline.yaml` | 70 | Processing configuration |
| `tests/fixtures/synthetic_data.py` | 350 | Synthetic data generators |
| `tests/unit/test_schema.py` | 350 | Schema validation tests |
| `tests/unit/test_config.py` | 250 | Config loader tests |
| **TOTAL** | **2,240+** | **Complete data contract + fixtures** |

---

## Testing

### Run all Task 2 tests:
```bash
pytest tests/unit/test_schema.py -v
pytest tests/unit/test_config.py -v
```

### Expected output:
```
tests/unit/test_schema.py::TestLRPair::test_lr_pair_valid PASSED
tests/unit/test_schema.py::TestFootStrikeSchema::test_foot_strike_pattern_valid PASSED
...
tests/unit/test_config.py::TestThresholdsLoading::test_load_thresholds_custom_path PASSED
...

=================== 27 passed in X.XXs ===================
```

---

## No Gaps Verification

✓ **Schema:** Every field in API_AND_SCHEMA.md is modeled  
✓ **Thresholds:** All thresholds from PRD are in config  
✓ **Rules:** Example rules cover all gait types  
✓ **Interfaces:** All 8 pipeline stages have abstract contracts  
✓ **Synthetic data:** Can generate any profile type (neutral/overpronation/oversupination)  
✓ **Tests:** Schema + config validation covered  
✓ **Type safety:** Enums prevent typos/mixing  
✓ **L/R notation:** Enforced in schema, no mixing  
✓ **Config loading:** All 4 config types covered (thresholds, pipeline, rules, cameras)  

---

## Next Steps (Phase 1B)

### Week 3: Ingestion
- [ ] `src/gait/ingestion/decode.py` — Video file decoding
- [ ] `src/gait/ingestion/calibrate.py` — Camera undistortion
- [ ] `src/gait/ingestion/segment_bg.py` — Background subtraction
- [ ] `src/gait/ingestion/track.py` — Person tracking
- [ ] `src/gait/ingestion/roi.py` — ROI cropping

### Week 4: Pose Estimation
- [ ] `src/gait/pose/body_2d.py` — MediaPipe wrapper
- [ ] `src/gait/pose/lift_3d.py` — 2D→3D monocular lifting
- [ ] `src/gait/pose/smooth.py` — 1-Euro filtering

### Week 5: Event Detection
- [ ] `src/gait/events/detect.py` — HS/TO detection
- [ ] `src/gait/events/segment_cycles.py` — Cycle segmentation

### Week 6: Analysis
- [ ] `src/gait/analysis/spatiotemporal.py`
- [ ] `src/gait/analysis/foot_strike.py`
- [ ] `src/gait/analysis/pronation.py`
- [ ] `src/gait/analysis/arch.py`
- [ ] `src/gait/analysis/symmetry.py`

### Week 7: Profile & Rules
- [ ] `src/gait/profile/builder.py` — Profile assembly
- [ ] `src/gait/profile/recommend.py` — Rule application
- [ ] `src/gait/profile/confidence.py` — Gating logic
- [ ] `src/gait/profile/validator.py` — JSON schema validation

### Week 8: API & Integration
- [ ] `src/gait/api/main.py` — FastAPI app
- [ ] `src/gait/api/routes/sessions.py` — Session endpoints
- [ ] `src/gait/api/tasks.py` — Celery tasks
- [ ] `src/gait/pipeline/run.py` — Pipeline orchestration

All implementations will:
- ✓ Inherit from interfaces in `common/interfaces.py`
- ✓ Load config via `pipeline/config.py`
- ✓ Output data matching `profile/schema.py`
- ✓ Be tested against synthetic data from `tests/fixtures/synthetic_data.py`

---

## Sign-Off

✓ **Schema:** Single source of truth (source of truth = COMPLETE)  
✓ **Config loaders:** YAML → Python (config-over-code = COMPLETE)  
✓ **Interfaces:** All pipeline stages (contracts = COMPLETE)  
✓ **Synthetic data:** Testing without hardware (developer velocity = COMPLETE)  
✓ **Tests:** Schema + config validation (confidence = COMPLETE)  

**Status:** Task 2 is COMPLETE. Phase 1B can begin immediately.

---

**Next:** Proceed to Phase 1B implementation (Weeks 3-8).

*Last Updated: 2026-06-10*  
*Phase: 1 (MVP Pipeline)*
