# Gait Analysis Module — Documentation Suite

> Computer-Vision-Based Module for Customized Orthopedic Footwear Prototyping

This folder contains the full documentation set required to design, build, validate, and ship the Gait Analysis Module — the first stage of the orthopedic footwear pipeline. Each document is self-contained but cross-references the others.

---

## How to read these docs

If you are new to the project, read in this order:

1. **[PRD.md](./PRD.md)** — *Why* this exists and *what* it must do. Start here.
2. **[ARCHITECTURE.md](./ARCHITECTURE.md)** — *How* the system is structured at a high level (includes AI Agents Layer §8).
3. **[DATA_FLOW.md](./DATA_FLOW.md)** — *How* data moves through the system (visual diagrams).
4. **[PROJECT_STRUCTURE.md](./PROJECT_STRUCTURE.md)** — *Where* code lives in the repo (includes `agents/` module).
5. **[API_AND_SCHEMA.md](./API_AND_SCHEMA.md)** — The *contract* between this module and the shoe-design module.
6. **[DATA_CAPTURE_PROTOCOL.md](./DATA_CAPTURE_PROTOCOL.md)** — The *operational* procedure for recording a subject.
7. **[VALIDATION_QA.md](./VALIDATION_QA.md)** — How we *prove* the system is accurate (includes agent validation).
8. **[PRIVACY_COMPLIANCE.md](./PRIVACY_COMPLIANCE.md)** — Legal, privacy, and data-handling obligations.
9. **[ENGINEERING_RULES.md](./ENGINEERING_RULES.md)** — Coding standards and team conventions (includes AI Agent Rules §11).
10. **[ROADMAP.md](./ROADMAP.md)** — The phased delivery plan (AI agents integrated per phase).

**For AI agents specifically:**
- **[../AI_AGENTS_INTEGRATION.md](../AI_AGENTS_INTEGRATION.md)** — Full AI agents roadmap, taxonomy, integration points, and governance.

---

## Document map

| Document | Purpose | Primary audience |
|---|---|---|
| `PRD.md` | Product requirements, scope, goals, success metrics | Everyone, stakeholders |
| `ARCHITECTURE.md` | System architecture, components, tech stack, AI agents layer | Engineers, architects |
| `DATA_FLOW.md` | Pipeline / sequence / state / agent diagrams | Engineers |
| `PROJECT_STRUCTURE.md` | Repository layout & module responsibilities (incl. agents/) | Engineers |
| `API_AND_SCHEMA.md` | REST endpoints + patient-profile JSON schema + rules YAML | Engineers, integrators |
| `DATA_CAPTURE_PROTOCOL.md` | Step-by-step capture SOP for operators | Clinicians, operators |
| `VALIDATION_QA.md` | Validation, calibration, repeatability, test strategy, agent validation | Engineers, QA, clinicians |
| `PRIVACY_COMPLIANCE.md` | DPDP 2023, consent, retention, security, agent audit logging | Everyone, legal |
| `ENGINEERING_RULES.md` | Coding standards, git workflow, review rules, AI agent rules | Engineers |
| `ROADMAP.md` | Phased roadmap with milestones, exit criteria, AI agent milestones | Everyone, PM |
| `../AI_AGENTS_INTEGRATION.md` | AI agents roadmap, taxonomy, integration, governance (Phase 2+) | Engineers, ML team |

---

## The one-sentence summary

> Given **6 walking passes** of a subject, this module returns within **~60 seconds** a structured **JSON patient profile** containing spatiotemporal parameters, a pronation/supination classification per foot, a foot-strike pattern, an arch type, a symmetry assessment, and a first-pass shoe-design recommendation block — and that JSON is the **single contract** with the rest of the footwear system.

---

## Project glossary

| Term | Meaning |
|---|---|
| **HS** | Heel-strike — the instant the heel contacts the ground (start of stance) |
| **TO** | Toe-off — the instant the toe leaves the ground (start of swing) |
| **Stance phase** | The portion of the gait cycle where the foot is on the ground (~60% in walking) |
| **Swing phase** | The portion where the foot is in the air (~40%) |
| **Gait cycle** | One full HS-to-next-HS of the *same* foot |
| **Rearfoot angle** | Frontal-plane angle of the calcaneus relative to the shank; the basis of pronation measurement |
| **Pronation** | Inward roll of the foot/ankle; excessive = overpronation |
| **Supination** | Outward roll of the foot/ankle; excessive = oversupination |
| **FSA** | Foot-strike angle — angle of the plantar foot to the ground at HS |
| **Spatiotemporal** | Distance- and time-based gait parameters (cadence, stride length, etc.) |
| **Markerless** | Pose estimation from video alone, with no physical markers on the body |
| **Keypoint** | A tracked anatomical landmark (e.g., calcaneus, malleolus, MTP head) |
| **Patient profile** | The output JSON consumed by the shoe-design module |
| **Medial post** | A firmer wedge on the inner midsole used to control overpronation |
| **Last** | The foot-shaped form a shoe is built around |
| **DPDP** | India's Digital Personal Data Protection Act, 2023 |
| **GaitAgent** | Base class for all AI agents (`src/gait/agents/base.py`); exposes `predict()`, `get_confidence()`, `get_reasoning()` |
| **Static baseline** | The YAML-driven classification/recommendation computed before any agent override; always the fallback if an agent is disabled or low-confidence |
| **Agent confidence** | A 0–1 score the agent attaches to each prediction; below the configured threshold, the static baseline is used instead |

---

## Status & ownership

| Field | Value |
|---|---|
| Document version | 1.1 |
| Last updated | 2026-06-12 |
| Module phase | Phase 0 Complete; Phase 1 In Progress (Task 3: Ingestion) |
| AI agents status | Infrastructure scaffolded (Phase 1B); agents disabled in MVP; Phase 2+ deployment |
| Source of truth | This `/docs` folder, version-controlled with the code |

> **Convention:** documentation lives in the same repository as the code and is reviewed in the same pull requests. A code change that breaks the patient-profile schema **must** update `API_AND_SCHEMA.md` in the same PR.
