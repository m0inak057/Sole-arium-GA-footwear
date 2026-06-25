# Data Flow & Diagrams
## Gait Analysis Module — Visual Flows

| Field | Value |
|---|---|
| Document | Data Flow & Diagrams |
| Version | 1.0 |
| Format | Mermaid (renders in GitHub, VS Code with Mermaid extension, Obsidian, etc.) |
| Related | [ARCHITECTURE.md](./ARCHITECTURE.md), [DATA_CAPTURE_PROTOCOL.md](./DATA_CAPTURE_PROTOCOL.md) |

> If a diagram does not render in your viewer, paste the code block into <https://mermaid.live>.

---

## 1. End-to-end pipeline (data flow)

```mermaid
flowchart TD
    A[Capture Layer<br/>Sagittal + Posterior + optional Plantar cams] -->|raw video streams| B[Ingestion & Preprocessing]
    B -->|clean, undistorted, ROI-cropped frames| C[Pose & Foot Keypoint Estimation]
    C -->|time-series of 2D/3D keypoints| D[Gait Event Detection]
    D -->|segmented gait cycles| E[Biomechanical Analysis Engine]
    E -->|parameter vector + classifications| F[Patient Profile Generator]
    F -->|profile.json| G[(Downstream:<br/>Shoe Design Module)]

    subgraph Preprocess [Ingestion details]
        B1[Decode & demux] --> B2[Timestamp align]
        B2 --> B3[Undistort / calibrate]
        B3 --> B4[Background subtraction]
        B4 --> B5[Person tracking]
        B5 --> B6[ROI crop]
    end
    B -.-> Preprocess
```

---

## 2. Pose & keypoint estimation (two-tier strategy)

```mermaid
flowchart LR
    F[Clean frames] --> TA[Tier A:<br/>Whole-body 2D pose<br/>MediaPipe / RTMPose / YOLOv8-Pose]
    F --> TB[Tier B:<br/>Custom foot keypoint net<br/>HRNet / ViTPose / RTMPose]
    TA --> M{Multi-camera?}
    TB --> M
    M -->|Yes| TR[Multi-view triangulation<br/>→ 3D keypoints]
    M -->|No| LF[Monocular 2D→3D lifter<br/>VideoPose3D / MotionBERT]
    TR --> SM[Temporal smoothing<br/>1-Euro / Savitzky–Golay]
    LF --> SM
    SM --> OUT[Keypoint time-series<br/>ready for event detection]
```

---

## 3. Gait event detection & cycle segmentation

```mermaid
flowchart TD
    KP[Keypoint time-series] --> BP[Bandpass filter<br/>heel & toe trajectories]
    BP --> HS[Detect Heel-Strike HS<br/>vertical minimum + velocity zero-crossing]
    BP --> TO[Detect Toe-Off TO<br/>toe velocity transition]
    HS --> XC[Cross-check with<br/>sagittal foot angle]
    HS --> CNN{Thresholding<br/>reliable?}
    CNN -->|No| CNN1[1D-CNN event model<br/>trained on labeled events]
    CNN -->|Yes| SEG[Segment cycles]
    CNN1 --> SEG
    XC --> SEG
    TO --> SEG
    SEG --> ST[Stance phase<br/>HS→TO ~60%]
    SEG --> SW[Swing phase<br/>TO→next HS ~40%]
    ST --> SUB[Sub-phases:<br/>initial contact, loading response,<br/>mid-stance, terminal stance, pre-swing]
    SW --> SUB2[Sub-phases:<br/>initial / mid / terminal swing]
```

---

## 4. Biomechanical analysis fan-out

```mermaid
flowchart LR
    CYC[Segmented cycles] --> SP[Spatiotemporal<br/>cadence, speed, stride/step length,<br/>step width, stance/swing time,<br/>double support, foot progression]
    CYC --> KIN[Kinematics<br/>ankle, knee, hip angles,<br/>pelvic tilt/drop, trunk lean]
    CYC --> FSC[Foot-strike classifier<br/>FSA at HS → rearfoot/midfoot/forefoot]
    CYC --> PRO[Pronation/supination<br/>rearfoot angle at mid-stance]
    CYC --> ARCH[Arch type<br/>arch height index / wet footprint]
    SP --> SYM[Symmetry indices<br/>flag > 10% asymmetry]
    KIN --> SYM
    PRO --> SYM
    SP --> AGG[Aggregate per cycle<br/>mean ± SD]
    KIN --> AGG
    FSC --> AGG
    PRO --> AGG
    ARCH --> AGG
    SYM --> AGG
    AGG --> PROF[Patient Profile Generator]
```

---

## 5. Session sequence (operator → system → output)

```mermaid
sequenceDiagram
    actor Op as Operator
    participant UI as Clinician UI
    participant API as FastAPI
    participant Q as Celery + Redis
    participant W as GPU Worker
    participant DB as PostgreSQL / S3
    actor Cl as Clinician

    Op->>UI: Register subject (ID, age, height, weight, foot dims, dominant side)
    Op->>UI: Run static calibration trial (3 s)
    Op->>UI: Run ≥6 dynamic walking passes (barefoot + shod)
    UI->>API: Upload synchronized video + metadata
    API->>DB: Store raw video + session metadata
    API->>Q: Enqueue processing job
    Q->>W: Dispatch task
    W->>W: Ingest → pose → events → analysis
    W->>W: Confidence gating & cycle filtering
    alt < 4 clean cycles per foot
        W-->>API: FAIL: insufficient cycles
        API-->>UI: Prompt operator to RE-RECORD
    else enough clean cycles
        W->>DB: Write profile.json + time-series (Parquet)
        W-->>API: Done
        API-->>UI: Results ready
        Cl->>UI: Review curves, cycle plots, classifications
        Cl->>UI: Adjust rules / override if needed
        UI->>DB: Persist final profile.json
    end
```

---

## 6. Quality-gating decision flow

```mermaid
flowchart TD
    S[Session captured] --> KPC{Keypoint confidence<br/>above threshold<br/>on critical frames?}
    KPC -->|No| DROP[Drop affected cycle]
    KPC -->|Yes| KEEP[Keep cycle]
    DROP --> COUNT{≥ 4 clean cycles<br/>per foot?}
    KEEP --> COUNT
    COUNT -->|No| RE[Request RE-RECORD<br/>fail loudly, no profile emitted]
    COUNT -->|Yes| YIELD{≥ 8 clean cycles<br/>per foot target met?}
    YIELD -->|No| WARN[Proceed with warning<br/>lower reliability flag]
    YIELD -->|Yes| OK[Proceed to analysis]
    WARN --> OK
    OK --> EMIT[Emit profile.json<br/>with confidence scores]
```

---

## 7. Health assessment rule mapping (YAML-driven)

```mermaid
flowchart TD
    AN[Analytical findings<br/>pronation, arch, foot-strike, symmetry] --> RULES[(rules.yaml<br/>editable by clinician)]
    RULES --> R1{Overpronation<br/>+ low arch?}
    R1 -->|Yes| O1["Defect: Overpronation + Flat Arch<br/>Exercises: Short foot, glute bridges<br/>What went right: —"]
    RULES --> R2{Oversupination<br/>+ high arch?}
    R2 -->|Yes| O2["Defect: Oversupination<br/>Exercises: Lateral band walks<br/>What went right: Strong arch"]
    RULES --> R3{Forefoot<br/>striker?}
    R3 -->|Yes| O3["Defect: Forefoot strike pattern<br/>Exercises: Heel-walking drills<br/>What went right: —"]
    O1 --> REC["health_assessment block<br/>in profile.json<br/>(what_went_right, defects_found,<br/>improvement_plan)"]
    O2 --> REC
    O3 --> REC
    REC --> HR{Pathological gait<br/>detected?}
    HR -->|Yes| REVIEW[Flag for human review]
    HR -->|No| FINAL[Patient receives assessment<br/>and improvement plan]
```

---

## 8. Gait cycle state machine

```mermaid
stateDiagram-v2
    [*] --> HeelStrike
    HeelStrike --> LoadingResponse: initial contact
    LoadingResponse --> MidStance
    MidStance --> TerminalStance: peak eversion measured here
    TerminalStance --> PreSwing
    PreSwing --> ToeOff
    ToeOff --> InitialSwing
    InitialSwing --> MidSwing
    MidSwing --> TerminalSwing
    TerminalSwing --> HeelStrike: next cycle (same foot)

    note right of MidStance
        Most diagnostic instant
        for pronation/supination
    end note
    note right of ToeOff
        Stance ends (~60%),
        swing begins (~40%)
    end note
```

---

## 9. AI agent decision flow (Phase 2+)

Every decision point that currently uses static YAML thresholds is designed to optionally route through an AI agent. The static baseline is always computed first; the agent result is used only when enabled and high-confidence.

```mermaid
flowchart TD
    INPUT[Gait parameters<br/>from analysis stage] --> STATIC[Compute static baseline<br/>from configs/thresholds.yaml<br/>or configs/rules.yaml]
    STATIC --> AGENT_EN{Agent enabled<br/>in pipeline.yaml?}
    AGENT_EN -->|No| USE_STATIC[Use static result]
    AGENT_EN -->|Yes| AGENT[Run GaitAgent.predict<br/>returns result + confidence]
    AGENT --> CONF{confidence ≥<br/>threshold?}
    CONF -->|No| USE_STATIC
    CONF -->|Yes| USE_AGENT[Use agent result]
    AGENT -->|Exception| USE_STATIC
    USE_STATIC --> LOG[Log decision:<br/>agent_name, input, output,<br/>confidence, source=static/agent]
    USE_AGENT --> LOG
    LOG --> OUT[Decision output<br/>to profile stage]

    subgraph Agents [Phase 2+ agents at each stage]
        QA[Quality Assessment Agent<br/>Phase 2: replaces binary cycle gate]
        TH[Threshold Tuning Agent<br/>Phase 3: replaces FSA/pronation/arch cutoffs]
        REC[Recommendation Agent<br/>Phase 3: replaces rules.yaml mappings]
        AN[Anomaly Detector<br/>Phase 3: replaces rule-based pathology flag]
    end
```

**Key invariant:** removing the entire `agents/` module produces identical pipeline behavior (static baseline path always exists).

---

## 10. Data lifecycle (capture → storage → privacy)

```mermaid
flowchart LR
    CAP[Raw video captured] --> CONSENT{Informed consent<br/>recorded?}
    CONSENT -->|No| STOP[Do not store / process]
    CONSENT -->|Yes| ENC[Encrypt video at rest]
    ENC --> PROC[Run gait pipeline]
    PROC --> BLUR[Blur / black-out faces<br/>unless explicit retention consent]
    BLUR --> STORE[(Encrypted store<br/>signed-URL access)]
    STORE --> RBAC[Role-based access:<br/>clinician vs. shoe designer]
    RBAC --> AUDIT[Audit-log every<br/>profile read]
    STORE --> RET{Retention period<br/>elapsed?}
    RET -->|Yes| DEL[Delete per policy]
    RET -->|No| STORE
```
