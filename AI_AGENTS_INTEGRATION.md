# AI Agents Integration Roadmap

**Version:** 1.0  
**Status:** Architecture & Planning Complete (Phase 1B+)  
**Date:** 2026-06-10

---

## Executive Summary

This document outlines how AI/ML agents progressively integrate into the gait analysis pipeline to reduce hardcoding, enable adaptive decision-making, and learn from real-world data.

**Core principle:** Agents are **optional** for MVP but infrastructure is designed to support them without breaking the pipeline.

---

## Why Agents?

### Current (Phase 1 MVP): Static, Hardcoded Decisions
```python
# Hard-coded thresholds
if rearfoot_angle > 8.0:  # Magic number
    pronation_class = "overpronation"

# Static rules
if pronation == "overpronation" and arch == "low":
    recommendation = "firm_medial_post"  # From rules.yaml

# Binary quality gates
if num_clean_cycles < 4:  # Magic number
    status = "RERECORD"
else:
    status = "PROCEED_OK"
```

### With Agents (Phase 2+): Data-Driven, Adaptive Decisions
```python
# Learned thresholds (from validation data)
threshold_agent = ThresholdTuningAgent(model="trained_on_phase3_data")
if rearfoot_angle > threshold_agent.predict_optimal_cutoff():
    pronation_class = "overpronation"

# Learned recommendations (from clinician feedback)
recommendation_agent = RecommendationAgent(model="trained_on_outcomes")
recommendation = recommendation_agent.generate_shoe_design(gait_params)

# Confidence-based quality assessment
quality_agent = QualityAssessmentAgent(model="learned_gait_patterns")
confidence, flags = quality_agent.assess_session(cycles)
status = quality_agent.make_decision(confidence)  # Not binary; returns confidence
```

### Benefits
✅ **Zero magic numbers** — thresholds learned from data  
✅ **Adaptive** — adjust to new equipment, populations, shoe types  
✅ **Personalized** — learn per-demographic shoe preferences  
✅ **Continuous improvement** — production feedback loops  
✅ **Explainable** — agents provide confidence + reasoning  

---

## Agent Taxonomy

### Category 1: Decision Agents (Classification/Scoring)
These agents **replace hardcoded decision logic** with learned models.

| Agent | Current | Future | When |
|-------|---------|--------|------|
| **Quality Assessment** | `< 4 cycles = reject` | Agent scores confidence (0-1) | Phase 2 |
| **Threshold Tuner** | `configs/thresholds.yaml` hardcoded | Learns optimal cutoffs from validation data | Phase 3 |
| **Recommendation** | Static rules in `rules.yaml` | Learns from clinician overrides + outcomes | Phase 3 |
| **Anomaly Detector** | None; flags based on rules | Learns pathological patterns | Phase 3 |

### Category 2: Selection Agents (Picking Best Option)
These agents **choose which strategy to use** for a given input.

| Agent | Current | Future | When |
|-------|---------|--------|------|
| **Model Selector** | Static `pipeline.yaml: model=mediapipe` | Chooses pose model based on input quality | Phase 2 |
| **Calibration Validator** | None; assumes valid | Detects when cameras need recalibration | Phase 3 |
| **Tracker Selector** | Static `simple_iou` | Chooses tracking method (simple vs. ByteTrack) | Phase 2 |

### Category 3: Learning Agents (Continuous Feedback)
These agents **improve from production feedback** without redeployment.

| Agent | Current | Future | When |
|-------|---------|--------|------|
| **Online Threshold Tuner** | None | Learns from clinician feedback on thresholds | Phase 4 |
| **Outcome Learner** | None | Learns from shoe-comfort feedback | Phase 4 |
| **Pattern Learner** | None | Updates anomaly detection model | Phase 4 |

---

## Integration Points

### A. Ingestion (Task 3) — No agents yet
```
src/gait/ingestion/preprocessor.py  ← All parameters from pipeline.yaml
                                       (agents disabled by default)
```

### B. Pose (Task 4+) — Model Selector Agent
```
src/gait/pose/detector.py
    ↓ Instead of:
    pose_model = load_model(config.model_name)  # Always "mediapipe"
    
    ↓ With agent:
    pose_model_selector = ModelSelectorAgent()
    pose_model = pose_model_selector.select_model(frame_quality)
```

### C. Analysis (Task 6+) — Threshold Tuning Agent
```
src/gait/analysis/pronation.py
    ↓ Instead of:
    if rearfoot_angle > config.thresholds.overpronation_min_deg:
        classification = "overpronation"
    
    ↓ With agent:
    threshold_agent = ThresholdTuningAgent(trained_model_path)
    cutoff = threshold_agent.predict_optimal_cutoff()  # Learned from data
    if rearfoot_angle > cutoff:
        classification = "overpronation"
```

### D. Profile (Task 7+) — Recommendation Agent + Quality Agent
```
src/gait/profile/builder.py
    ↓ Recommendation
    recommendation_agent = RecommendationAgent(model=config.agents.recommendation_model)
    recommendations = recommendation_agent.generate(gait_params)
    
    ↓ Quality Assessment
    quality_agent = QualityAssessmentAgent(model=config.agents.quality_model)
    confidence, flags = quality_agent.assess(cycles)
    profile.needs_human_review = quality_agent.should_review(confidence)
```

---

## Agent Architecture

### Base Class (All agents inherit from this)
```python
from abc import ABC, abstractmethod

class GaitAgent(ABC):
    """Base class for all gait analysis agents."""
    
    def __init__(self, model_path: str, config: dict):
        """Load trained model and config."""
        self.model = load_model(model_path)
        self.config = config
    
    @abstractmethod
    def predict(self, input_data: dict) -> dict:
        """Agent-specific prediction logic."""
        pass
    
    def get_confidence(self) -> float:
        """Return confidence in the last prediction [0, 1]."""
        return self.last_confidence
    
    def get_reasoning(self) -> dict:
        """Return why the agent made this prediction."""
        return self.last_reasoning
```

### Configuration (in `configs/agents.yaml` or `pipeline.yaml`)
```yaml
agents:
  enabled: false                    # Global switch; off for MVP

  quality_assessment:
    enabled: false                  # Phase 2+
    model_path: models/quality_v1.pth
    confidence_threshold: 0.7       # Flag if confidence < this
    version: 1

  threshold_tuner:
    enabled: false                  # Phase 3+
    model_path: models/thresholds_v1.pth
    version: 1

  recommendation:
    enabled: false                  # Phase 3+
    model_path: models/recommendations_v1.pth
    version: 1

  anomaly_detector:
    enabled: false                  # Phase 3+
    model_path: models/anomaly_v1.pth
    version: 1

  model_selector:
    enabled: false                  # Phase 2+
    model_path: models/selector_v1.pth
    version: 1
```

---

## Phase-by-Phase Rollout

### Phase 1B (Current): Infrastructure Only
```
✓ Agent-friendly config structure in place
✓ src/gait/agents/ directory created (empty)
✓ pipeline.yaml has agents section (all disabled)
✓ GaitAgent base class defined
✗ No trained models yet
✗ No agent learning logic yet
```

### Phase 2 (Weeks 3-8): First Agent (Quality Assessment)
```
✓ Collect training data from MVP sessions
✓ Train quality assessment model
  - Input: gait cycle keypoints + metadata
  - Output: quality_score (0-1), flags (list of issues)
✓ Integrate into profile builder
  - Replace: if num_cycles < 4 → reject
  - With: quality_score = quality_agent.assess(cycles)
✓ Test with production data
```

**Impact:** Reduces false negatives (some < 4-cycle sessions are actually good)

### Phase 3 (Weeks 9-14): Learning Agents (Thresholds, Recommendations, Anomaly)
```
✓ Run validation study (30 patients + pressure mat ground truth)
✓ Train threshold-tuning agent
  - Input: rearfoot_angle, foot_strike_angle, arch_height_index
  - Output: optimal_classification_thresholds
✓ Train recommendation agent
  - Input: gait parameters + clinician overrides (Phase 2 feedback)
  - Output: shoe_design_recommendations
✓ Train anomaly detector
  - Input: gait cycle patterns
  - Output: anomaly_score (0-1) + type (e.g., "limp", "asymmetry")
✓ Update all agents in production
```

**Impact:** Thresholds tuned to real clinical data; recommendations adaptive

### Phase 4 (Ongoing): Online Learning
```
✓ Collect production feedback (clinician overrides, patient outcomes)
✓ Retrain agents quarterly
✓ Implement feedback loops
  - Clinician overrides → recommendation agent learns
  - Patient follow-up data → quality agent improves
  - New shoe type arrives → agent adapts to new population
```

**Impact:** System continuously improves from real-world feedback

---

## Data Requirements for Training

### Quality Assessment Agent (Phase 2)
- **Training data:** 100+ gait sessions (with manual quality labels)
- **Features:** keypoint trajectories, cycle counts, confidence scores
- **Labels:** quality_score (0-1), flags (list of issues)
- **Model:** Random Forest or simple neural network

### Threshold Tuning Agent (Phase 3)
- **Training data:** Validation study (30 patients × multiple shoe types)
- **Ground truth:** Pressure mat measurements
- **Features:** Computed gait parameters (rearfoot_angle, FSA, AHI)
- **Labels:** Actual pronation class (from pressure mat), foot strike type
- **Model:** Logistic regression or SVM for classification boundaries

### Recommendation Agent (Phase 3)
- **Training data:** Clinical outcomes (Phase 2+)
- **Features:** Gait parameters + demographics (age, shoe type, activity level)
- **Labels:** Clinician overrides (what they actually prescribed vs. what rules said)
- **Model:** Gradient boosting or neural network

### Anomaly Detector (Phase 3)
- **Training data:** Normal gait patterns from healthy subjects (100+)
- **Features:** Keypoint trajectories, spatiotemporal parameters
- **Labels:** Anomaly type (normal vs. limp vs. asymmetry vs. pathological)
- **Model:** Isolation Forest or VAE (variational autoencoder)

---

## Backward Compatibility (Critical!)

### Non-Breaking Agent Additions
Agents must **never break the pipeline** if they fail or are disabled.

**Safe agent integration pattern:**
```python
# In src/gait/analysis/pronation.py

def classify_pronation(rearfoot_angle: float, config: PipelineConfig) -> str:
    """Classify pronation with optional agent override."""
    
    # Always compute static classification first (baseline)
    baseline_class = _static_classify(
        rearfoot_angle,
        config.thresholds.pronation
    )
    
    # If agent is enabled, use agent decision; else use baseline
    if config.agents.enabled and config.agents.threshold_tuner.enabled:
        try:
            agent = ThresholdTuningAgent(config.agents.threshold_tuner.model_path)
            agent_class = agent.predict({"rearfoot_angle": rearfoot_angle})
            confidence = agent.get_confidence()
            if confidence < config.agents.threshold_tuner.confidence_threshold:
                # Low confidence → fall back to baseline
                return baseline_class
            return agent_class
        except Exception as e:
            logger.warning(f"Threshold agent failed; using baseline: {e}")
            return baseline_class
    
    return baseline_class
```

**Key invariant:** If agent is missing/broken/disabled, pipeline still works using static rules.

---

## Monitoring Agents

### Per-Agent Metrics
```python
class AgentMetrics:
    agent_name: str
    predictions_made: int
    confidence_mean: float          # Average confidence of predictions
    confidence_std: float
    overrides: int                  # How often clinician overrode agent
    override_rate: float            # % of decisions overridden
    accuracy_vs_ground_truth: float # (Phase 3+ with validation data)
    version: str                    # Model version used
```

### Logging (Structured JSON)
```json
{
  "timestamp": "2026-06-15T10:23:45Z",
  "event": "agent_prediction",
  "agent_name": "threshold_tuner",
  "input": {"rearfoot_angle": 10.5},
  "output": "overpronation",
  "confidence": 0.91,
  "reasoning": {"overpronation_cutoff": 8.2, "margin": 2.3},
  "was_overridden": false
}
```

---

## Agent Governance

### Model Versioning
- Each agent model is versioned (e.g., `quality_v1.pth`, `threshold_v2.pth`)
- `pipeline.yaml` specifies which version to use
- Easy rollback if new model regresses

### Model Approval Workflow (Phase 3+)
1. **Train** agent on validation data
2. **Validate** vs. ground truth (pressure mat, clinical consensus)
3. **Compare** to static baseline
4. **Approve** only if accuracy improves + confidence > threshold
5. **Deploy** by updating `pipeline.yaml` + model file
6. **Monitor** override rates in production

### Fairness Checks (Phase 3+)
- Test agent accuracy across demographic groups
- Ensure no systematic bias by age, shoe type, gender
- Log disaggregated metrics per subgroup

---

## Future: Online Learning Loop (Phase 4)

```
┌──────────────────┐
│ Production       │
│ (Clinician uses  │
│  agent & may     │
│  override)       │
└────────┬─────────┘
         ↓
┌──────────────────┐
│ Collect          │
│ - Clinician      │
│   overrides      │
│ - Patient        │
│   follow-up      │
│ - Outcome data   │
└────────┬─────────┘
         ↓
┌──────────────────┐
│ Quarterly        │
│ Retraining       │
│ (Retrain agents  │
│  on new data)    │
└────────┬─────────┘
         ↓
┌──────────────────┐
│ A/B Testing      │
│ (New vs. old     │
│  agent)          │
└────────┬─────────┘
         ↓
┌──────────────────┐
│ Approve &        │
│ Deploy           │
│ (Update models)  │
└──────────────────┘
```

---

## For Implementers

### Phase 1B (Task 3-7): Do This
- [ ] Config structure supports agents (DONE in `pipeline.yaml`)
- [ ] All thresholds/rules in YAML (not hardcoded)
- [ ] Expose confidence scores in every decision
- [ ] Log all decisions with reasoning (for future agent training)
- [ ] Design components to accept agent overrides (gracefully fallback to baseline)

### Phase 2+: Future Implementers Will Do This
- [ ] Collect training data from Phase 1 MVP deployments
- [ ] Build agent training pipeline
- [ ] Implement agent loading/inference in decision points
- [ ] Add monitoring dashboards for agent metrics
- [ ] Create retraining & approval workflows

---

## Success Criteria (Phase 1B)

✅ `pipeline.yaml` has `agents:` section (all disabled)  
✅ `src/gait/agents/` directory exists with `base.py`  
✅ All thresholds/rules externalized (ready for agent override)  
✅ All decisions log confidence + reasoning (for training data)  
✅ Baseline (static) path always works if agents disabled  

---

## Q&A

**Q: Will agents slow down the pipeline?**  
A: Not if designed right. Agent inference (forward pass) is ~1-10ms per decision. Negligible vs. video decoding/pose estimation.

**Q: What if agents hallucinate wrong thresholds?**  
A: Validation study (Phase 3) compares agents vs. pressure-mat ground truth before deployment. Only deploy if accuracy ≥ baseline.

**Q: Can we revert an agent?**  
A: Yes. `pipeline.yaml` version pins the model. Change version → rollback. Fast.

**Q: How do we know when agents are broken?**  
A: Per-agent metrics logged continuously. Monitoring dashboard alerts if override rate spikes.

---

**See also:** IMPLEMENTATION_PLAYBOOK.md §11 for agent integration timeline.
