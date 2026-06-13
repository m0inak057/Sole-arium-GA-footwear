# Engineering Rules & Conventions
## Gait Analysis Module

| Field | Value |
|---|---|
| Document | Engineering Rules |
| Version | 1.0 |
| Related | [PROJECT_STRUCTURE.md](./PROJECT_STRUCTURE.md), [API_AND_SCHEMA.md](./API_AND_SCHEMA.md), [VALIDATION_QA.md](./VALIDATION_QA.md) |

These are the rules that keep the codebase consistent, the pipeline trustworthy, and the output contract stable. They are deliberately opinionated.

---

## 1. Golden rules (project-specific, non-negotiable)

1. **One contract out.** Nothing outside this module may depend on anything except `profile.json`. Internal representations are free to change.
2. **No thresholds in code.** Every tunable number (FSA cutoffs, rearfoot-angle bands, symmetry %, confidence gates) lives in `configs/thresholds.yaml`. A magic number in a classifier is a bug.
3. **No recommendation logic hardcoded.** Shoe-design mapping lives in `configs/rules.yaml`, applied by `profile/recommend.py`. The orthotist owns those rules.
4. **The schema has one source of truth:** `src/gait/profile/schema.py` (pydantic). The JSON Schema in `API_AND_SCHEMA.md` is generated from it. Changing one without the other is forbidden.
5. **Fail loudly on bad data.** If confidence gating leaves < 4 clean cycles per foot, raise and request re-record. Never fabricate or silently impute a profile.
6. **Confidence travels with data.** Keypoints, cycles, and classifications carry confidence; downstream code must respect gates, not bypass them.
7. **Calibration is data.** Camera intrinsics/extrinsics live in `configs/cameras/`, never in source.
8. **Models are external, pinned artifacts.** Weights are never committed; they are versioned and pulled from an artifact store.
9. **Privacy is not optional.** No code path stores un-blurred video beyond the consented window. See [PRIVACY_COMPLIANCE.md](./PRIVACY_COMPLIANCE.md).
10. **A schema-breaking change bumps the version** (`profile/v2`) and ships a migration note.

---

## 2. Language & tooling

| Concern | Standard |
|---|---|
| Language | Python 3.11+ |
| Formatting | `black` (line length 100) |
| Linting | `ruff` |
| Imports | `ruff`/`isort` ordering |
| Typing | `mypy` in strict-ish mode; public functions fully typed |
| Tests | `pytest` |
| Dep management | `pyproject.toml` (poetry / uv / pip-tools — pick one, pin it) |
| Pre-commit | `pre-commit` runs format + lint + type check |

> CI runs format check, lint, type check, and the test suite. A red pipeline cannot merge.

---

## 3. Naming conventions

| Thing | Convention | Example |
|---|---|---|
| Packages / modules | `snake_case`, singular by stage | `pose`, `events`, `analysis` |
| Files | `snake_case.py` | `foot_strike.py`, `pronation.py` |
| Functions | `snake_case`, verb-first | `compute_rearfoot_angle()`, `detect_heel_strike()` |
| Classes / pydantic models | `PascalCase` | `GaitPatientProfile`, `GaitCycle` |
| Constants | `UPPER_SNAKE_CASE` | `DEFAULT_FPS` |
| Config keys | `snake_case` | `overpronation_min_deg` |
| Units in names | Always suffix the unit | `stride_length_m`, `rearfoot_angle_deg`, `mass_kg` |
| Left/Right | `{"L": ..., "R": ...}` everywhere | never `left`/`right` mixed with `L`/`R` |

> **Units rule:** any numeric quantity that has a unit must carry it in the name. `angle` is a bug; `rearfoot_angle_deg` is correct.

---

## 4. Code structure rules

- **Pure functions for analysis.** Each function in `analysis/` and `pose/` should be a function of its input + config, with no hidden global state — so it is unit-testable on a fixture.
- **Stages don't reach across.** `analysis/` imports from `common/`, not from `api/`. Dependencies flow toward `common/`, never the reverse.
- **No I/O in math.** Geometry/signal functions take arrays in and return arrays/values out. Reading/writing files belongs in `common/io.py` or the pipeline layer.
- **Config is loaded once** at the pipeline boundary and passed down explicitly; modules don't read YAML on their own.
- **Type the boundaries.** Anything crossing a stage boundary uses the dataclasses/types in `common/types.py` or pydantic models.

---

## 5. Git workflow

### Branching
- `main` — always releasable; protected.
- `feature/<short-desc>` — new work (e.g. `feature/rearfoot-angle`).
- `fix/<short-desc>` — bug fixes.
- `chore/<short-desc>` — tooling/infra/docs-only.

### Commits (Conventional Commits)
```
<type>(<scope>): <summary>

[optional body]
```
Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`, `build`, `ci`.
Scopes mirror packages: `pose`, `events`, `analysis`, `profile`, `api`, `docs`, `configs`.

Examples:
- `feat(analysis): add time-to-peak-eversion metric`
- `fix(events): correct toe-off velocity zero-crossing`
- `docs(api): bump profile schema to v1.1 (additive arch field)`

### Pull requests
- Small and focused; one logical change.
- Must pass CI (format, lint, types, tests).
- Must update docs in the **same PR** when behavior or the schema changes.
- At least one reviewer approval.

---

## 6. Review checklist (reviewer ticks)

- [ ] No magic numbers — thresholds came from `configs/`
- [ ] No hardcoded recommendation logic
- [ ] Units present in all numeric names
- [ ] `L`/`R` convention followed
- [ ] New/changed schema reflected in `profile/schema.py` **and** `API_AND_SCHEMA.md`
- [ ] Tests added/updated (unit + integration where relevant)
- [ ] Confidence gating respected; no silent imputation
- [ ] No secrets / credentials / large model weights committed
- [ ] Privacy-sensitive paths reviewed (no un-blurred video leakage)
- [ ] Public functions typed and docstringed

---

## 7. Testing rules
- Every classifier change adds boundary tests on **both sides** of each threshold.
- Every schema change adds/updates a schema-validation test.
- Golden-sample e2e snapshots are updated only with explicit reviewer sign-off (see [VALIDATION_QA.md](./VALIDATION_QA.md)).
- Filters/smoothing changes must include a test asserting event-frame timing is preserved within tolerance.

---

## 8. Documentation rules
- Docs live in `/docs` in the same repo and are versioned with the code.
- The README doc map stays accurate when docs are added/removed.
- Any change to the patient-profile schema updates `API_AND_SCHEMA.md` and notes the version.
- Operational changes (camera positions, fps, protocol) update `DATA_CAPTURE_PROTOCOL.md`.

---

## 9. Error handling & logging
- Use structured logging (`common/logging.py`); log per-stage timings, confidence distributions, dropped-cycle counts.
- Raise typed, descriptive exceptions at stage boundaries; never swallow errors silently.
- The re-record condition is a **first-class, expected outcome**, not an exception to hide — surface it cleanly to the API/UI.

---

## 10. Performance rules
- Keep the GPU-heavy work (pose, 3D, analysis) in the Celery worker; keep the API async and light.
- Crop to ROI before expensive inference.
- Respect the ~60 s/session budget; a change that regresses processing time on the reference machine must justify it.

---

## 11. AI agent rules (Phase 2+)

These rules govern how AI agents integrate into the pipeline without breaking its correctness or trustworthiness.

1. **Agents are optional overrides, never hard dependencies.** Always compute the static YAML-driven baseline first. The agent result is used only when: (a) the agent is enabled, (b) its confidence ≥ `config.agents.<name>.confidence_threshold`. On any exception or low confidence, fall back to the static result silently. The pipeline must produce correct output even if every agent is removed.

2. **Confidence gates apply to agent decisions.** An agent that returns `confidence < threshold` is treated as if it produced no result. The caller uses the static baseline instead.

3. **Every agent decision is logged.** Each agent call must emit a structured log entry containing: `agent_name`, `input`, `output`, `confidence`, `reasoning`, `was_overridden_by_clinician`. This log is the training signal for future agent versions.

4. **No agent ships without baseline comparison.** A new agent model may only be deployed to production when its accuracy on a held-out, diverse validation set is **≥ the static YAML baseline**. This comparison is part of the PR review checklist.

5. **Fairness is a gate.** Agent accuracy must not drop systematically across skin-tone, arch type, or demographic subgroups vs. the baseline. Run disaggregated metrics before any Phase 3+ agent promotion.

6. **Agents are versioned like models.** `pipeline.yaml` pins the agent model version (e.g., `quality_v1`). Rollback = edit `pipeline.yaml` + restart worker. No code change needed.

7. **`src/gait/agents/` only imports from `common/`.** The agents module may not import from `analysis/`, `profile/`, or `pipeline/`. Dependency direction: `agents/` ← `common/`.

8. **Agent weights live in `models/agents/` and are gitignored.** Pulled from artifact store and pinned by version, same as pose model weights. Never commit weights.

### Agent-specific review checklist additions
- [ ] Agent result used only when `enabled=True AND confidence ≥ threshold`
- [ ] Static baseline always computed first; agent is an override
- [ ] Agent decision logged with confidence + reasoning
- [ ] No agent import from `analysis/`, `profile/`, or `pipeline/`
- [ ] Model card written if new agent weights are being shipped
- [ ] Accuracy vs. static baseline verified on held-out set
- [ ] Fairness check run across subgroups
