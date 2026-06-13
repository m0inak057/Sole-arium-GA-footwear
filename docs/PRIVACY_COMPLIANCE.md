# Data, Privacy & Compliance
## Gait Analysis Module — Handling Sensitive Health Video

| Field | Value |
|---|---|
| Document | Privacy & Compliance |
| Version | 1.0 |
| Jurisdiction (primary) | India — DPDP Act, 2023 |
| Related | [DATA_CAPTURE_PROTOCOL.md](./DATA_CAPTURE_PROTOCOL.md), [API_AND_SCHEMA.md](./API_AND_SCHEMA.md), [DATA_FLOW.md §Data lifecycle](./DATA_FLOW.md) |

> **Note:** this document describes the project's intended privacy posture and engineering controls. It is not legal advice; confirm obligations with qualified counsel before processing real patient data.

---

## 1. Why this matters
The subject is **directly identifiable** in the captured video. All captures must therefore be treated as **sensitive personal health data**, with the strictest handling in the system.

---

## 2. Regulatory baseline

### 2.1 India — DPDP Act, 2023 (primary)
The system is designed to honor the core DPDP principles:
- **Informed consent** — captured before any recording; specific to the gait-analysis and footwear-design purpose.
- **Purpose limitation** — data is used only for the stated purpose; no secondary use without fresh consent.
- **Data minimization** — capture and retain only what the analysis needs (faces are not needed).
- **Retention limitation** — a defined retention policy; delete when the purpose is fulfilled or consent withdrawn.
- **Right to erasure / correction** — subjects can request deletion or correction of their data.
- **Accountability** — audit logging and access controls demonstrate compliance.

### 2.2 If exporting internationally
If data ever crosses borders, additionally align with:
- **HIPAA** (US health data) where applicable.
- **GDPR** (EU) — lawful basis, data subject rights, cross-border transfer safeguards.

---

## 3. Data classification

| Data | Classification | Handling |
|---|---|---|
| Raw video (face visible) | Highly sensitive | Encrypt at rest; blur faces post-pipeline; shortest retention |
| Face-blurred video | Sensitive | Encrypted; retained per policy |
| Keypoint time-series (Parquet) | Sensitive (biometric-derived) | Encrypted; pseudonymous |
| `profile.json` | Sensitive (health) | Encrypted; pseudonymous; RBAC-gated |
| Subject metadata (age, height, weight, foot dims) | Sensitive (health) | Encrypted; pseudonymous |
| Identity ↔ pseudonym mapping | Highly sensitive | Stored separately, tightest access |

---

## 4. Consent

- Consent is recorded **before** capture; no consent → no capture (enforced in the protocol and UI).
- Consent specifies purpose, what is captured, retention duration, and the subject's rights.
- **Facial retention requires explicit, separate consent.** By default, faces are blurred/blacked-out once the pipeline has run, because faces are not needed for analysis.
- Withdrawal of consent triggers deletion per the retention/erasure process.

---

## 5. Face handling
- The gait pipeline does **not** use facial information.
- Once the pipeline has run, faces in stored video are **blurred or blacked-out** by default.
- Original (un-blurred) video is retained only with explicit consent and for the minimum necessary time.

(See the data-lifecycle diagram in [DATA_FLOW.md](./DATA_FLOW.md).)

---

## 6. Security controls

| Control | Requirement |
|---|---|
| **Encryption at rest** | All video, time-series, profiles, and metadata encrypted |
| **Encryption in transit** | TLS for all API and storage access |
| **Signed URLs** | Video retrieval via time-limited signed URLs, never public links |
| **Role-based access control (RBAC)** | Distinct roles: clinician, shoe designer, admin — least privilege |
| **Audit logging** | Every read of a patient profile is logged (who, what, when) |
| **Pseudonymization** | Profiles keyed by pseudonymous `patient_id`; identity mapping stored separately |
| **Secrets management** | No credentials in code or committed `.env`; use a secrets store |

### 6.1 Role → access matrix (illustrative)

| Resource | Clinician | Shoe Designer | Admin |
|---|---|---|---|
| Raw video | Read (own patients) | — | Read |
| Face-blurred video | Read | — | Read |
| `profile.json` | Read/Update (recommendations) | Read | Read |
| Subject identity mapping | Limited | — | Read |
| Recommendation rules (`rules.yaml`) | Read/Update | Read | Read/Update |
| Audit logs | — | — | Read |

---

## 7. Retention & deletion

- Define a concrete **retention period** per data class (shortest for un-blurred video).
- On expiry or consent withdrawal: delete video, time-series, profile, and metadata; retain only what law requires (if anything), and log the deletion.
- Periodically purge data past its retention window automatically.

---

## 8. Data subject rights (operational)

| Right | How it is honored |
|---|---|
| Access | Provide the subject's stored data on verified request |
| Correction | Update incorrect metadata/profile fields |
| Erasure | Delete on withdrawal of consent or request |
| Purpose transparency | Consent form states purpose and retention up front |

---

## 9. AI agent decisions — privacy and audit obligations (Phase 2+)

AI agent predictions are derived from sensitive biometric data and therefore carry the same handling obligations as the profile itself.

| Control | Requirement |
|---|---|
| **Agent decision logging** | Every agent prediction must be logged with: `agent_name`, `input_summary`, `output`, `confidence`, `was_overridden_by_clinician`. These logs are health-derived data — encrypt and RBAC-gate like profiles. |
| **Training data provenance** | Agent training data (gait cycles + labels) must be pseudonymized and covered by consent. If fresh consent is needed for re-use of historical data for training, obtain it before training. |
| **Purpose limitation** | Agent training data may only be used to improve the gait analysis pipeline. Secondary use (e.g., aggregated research) requires separate consent and DPA agreement. |
| **Right to erasure** | If a subject exercises the right to erasure, their data must be removed from agent training datasets; retrain or document the data lineage so affected model versions are flagged. |
| **Model fairness as a compliance obligation** | Phase 3+ agents must pass fairness checks before deployment. Systematic inaccuracy across demographic groups is a discriminatory harm — not just an accuracy issue. |

---

## 10. Engineering checklist (privacy by design)

- [ ] Consent recorded and verifiable before capture
- [ ] Capture limited to what analysis needs (ankles/shins, not identity-rich extras)
- [ ] Video encrypted at rest immediately on upload
- [ ] Face-blur step runs after the pipeline (unless explicit retention consent)
- [ ] Profiles pseudonymized; identity mapping stored separately
- [ ] RBAC enforced on every endpoint
- [ ] Signed URLs for all video access
- [ ] Every profile read is audit-logged
- [ ] Retention timers configured; automatic purge in place
- [ ] Cross-border export path (if any) reviewed against HIPAA/GDPR
- [ ] Agent decision logs encrypted and RBAC-gated (same as profiles)
- [ ] Agent training data pseudonymized and consent-covered
- [ ] Right-to-erasure process covers agent training datasets
- [ ] Agent fairness check completed before Phase 3+ deployment
