# Staging Deployment & Validation Protocol

Before redeploying to AWS production with the July 2026 fixes, follow this checklist to validate the system in a staging environment that matches production config.

---

## Phase 1: Environment Setup (1–2 hours)

### 1.1 Provision Staging Infrastructure

On AWS (or your staging environment):

- [ ] **EC2 or ECS instance** with GPU support (same machine type as production API worker).
- [ ] **RDS PostgreSQL** instance (or CloudSQL equivalent) — separate database from production.
- [ ] **ElastiCache Redis** — separate from production.
- [ ] **S3 bucket** for video/timeseries storage — staging prefix (e.g., `s3://bucket/staging/`).
- [ ] **IAM roles** — same permissions as production API/worker roles.
- [ ] Security groups: allow internal communication (API ↔ worker, worker ↔ Redis/Postgres/S3).

### 1.2 Deploy Code

```bash
# On the staging instance
git clone <repo-url> gait-staging
cd gait-staging
git checkout main  # Or the branch with the July 2026 fixes

# Copy staging `.env` (created separately, with STAGING_ prefixes)
cp .env.staging .env

# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head  # or equivalent

# Build Docker images
docker build -t gait-api:staging -f docker/Dockerfile.api .
docker build -t gait-worker:staging -f docker/Dockerfile.worker .
```

### 1.3 Verify Environment Variables

Check that all of these are set correctly for **staging**:

```bash
# Core
export GAIT_API_KEYS="staging-test-key-change-in-production"
export DATABASE_URL="postgresql://user:pass@staging-rds.aws.com/gait_staging"
export CELERY_BROKER_URL="redis://staging-redis.elasticache.amazonaws.com:6379/0"
export CELERY_RESULT_BACKEND="redis://staging-redis.elasticache.amazonaws.com:6379/1"

# Storage
export STORAGE_TYPE="s3"
export AWS_S3_BUCKET="my-bucket-staging"
export AWS_S3_REGION="us-east-1"
export AWS_ACCESS_KEY_ID="staging-key"
export AWS_SECRET_ACCESS_KEY="staging-secret"

# Models
export POSE_MODEL_PATH="/models/pose_landmarker_lite.task"
export FACE_BLUR_ENABLED="true"

# Logging & Monitoring
export SENTRY_DSN="https://staging-key@sentry.io/staging-project"
export LOG_LEVEL="INFO"
```

### 1.4 Start Services

```bash
docker-compose -f docker-compose.staging.yml up -d

# Wait for services to be ready
sleep 10

# Verify health endpoints
curl http://staging-api:8000/health
curl http://staging-api:8000/api/v1/health
```

---

## Phase 2: Regression Testing (1–2 hours)

### 2.1 Run Unit Tests in Staging Environment

```bash
# Run the new rearfoot alignment + FPA tests
pytest tests/unit/test_rearfoot_alignment_fpa_fixes.py -v

# Run full unit test suite (excluding pre-existing failures)
pytest tests/unit --ignore=tests/unit/test_api_models.py \
  --ignore=tests/unit/test_db_models.py \
  --ignore=tests/unit/test_db_session_repo.py -q

# Expected result: ≥ 819 passing, 3 pre-existing failures in face_blur
```

### 2.2 End-to-End Test: Walking Video + Static Photo Fallback

Upload the same test session used in **Phase E validation** (from `data/uploads/c93a62e5-e7b0-4da5-9385-a477f31868a9/`):

```bash
# Create session
SESSION_ID=$(curl -s -X POST http://staging-api:8000/api/v1/sessions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: staging-test-key-change-in-production" \
  -d '{
    "patient_id": "staging_regression_test",
    "trial_condition": "barefoot",
    "anthropometrics": {
      "height_cm": 175, "mass_kg": 70,
      "foot_length_mm": {"L": 260, "R": 260},
      "foot_width_mm": {"L": 95, "R": 95},
      "dominant_foot": "right"
    }
  }' | jq -r '.session_id')

# Upload videos + static photo
BASE=data/uploads/c93a62e5-e7b0-4da5-9385-a477f31868a9
for pair in "anterior:$BASE/anterior/3_FRONT_ANGLE.mp4" \
            "sagittal:$BASE/sagittal/3_SIDE_ANGLE.mp4" \
            "posterior:$BASE/posterior/3_BACK_ANGLE.mp4" \
            "static_posterior:$BASE/static_posterior/Rear_foot_1.jpg"; do
  view="${pair%%:*}"; file="${pair#*:}"
  curl -s -X POST "http://staging-api:8000/api/v1/sessions/$SESSION_ID/uploads?camera_view=$view" \
    -H "X-API-Key: staging-test-key-change-in-production" \
    -F "file=@$file"
done

# Trigger processing
curl -s -X POST "http://staging-api:8000/api/v1/sessions/$SESSION_ID/process" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: staging-test-key-change-in-production" -d '{}'

# Poll until completion (max 2 minutes)
for i in {1..24}; do
  STATUS=$(curl -s "http://staging-api:8000/api/v1/sessions/$SESSION_ID/status" \
    -H "X-API-Key: staging-test-key-change-in-production" | jq -r '.status')
  echo "Status: $STATUS"
  [ "$STATUS" = "COMPLETED" ] && break
  sleep 5
done

# Fetch and verify profile
PROFILE=$(curl -s "http://staging-api:8000/api/v1/sessions/$SESSION_ID/profile" \
  -H "X-API-Key: staging-test-key-change-in-production" | jq '.profile')

echo "$PROFILE" | jq '.rearfoot_alignment'
echo "$PROFILE" | jq '.wedging_prescription'
```

### 2.3 Verify Results

**Expected outcomes:**

- [ ] `rearfoot_alignment.angle_deg.L` and `.R` are within ±30° (or null).
- [ ] `rearfoot_alignment.method` is `"static_image"` (static photo used) or `"walking_video_midstance"` (fallback).
- [ ] `wedging_prescription.left_wedge_degree_deg` and `.right_wedge_degree_deg` are bounded (typically 3–7°).
- [ ] If method is `"walking_video_midstance"`, `clinical_rationale` includes the disclaimer: *"Note: measurement derived from dynamic gait video — for clinical use confirm with static standing assessment."*
- [ ] `spatiotemporal.foot_progression_angle_left_deg` and `.right_deg` are either:
  - Within ±20° (plausible), OR
  - `null` (unreliable, > ±45° detected and rejected).
- [ ] No errors in worker logs; check:
  ```bash
  docker logs gait-worker-staging --tail=100 | grep -i "error\|fail\|exception"
  ```

---

## Phase 3: Real Static Photo Validation (1–2 hours)

Follow the **Real Static Photo Test Protocol** below to acquire and process one real compliant static standing photo.

---

## Phase 4: Production Checklist (30 minutes)

Once staging validation passes, prepare production deployment:

### 4.1 Pre-Deployment Review

- [ ] All 819 unit tests pass locally.
- [ ] Staging end-to-end test completed successfully.
- [ ] Real static photo test completed and metrics are within tolerance.
- [ ] Documentation (`CHANGELOG.md`, API_AND_SCHEMA.md, etc.) is up-to-date.
- [ ] Commit message is clear and references the July 2026 fixes.
- [ ] Code review is approved.

### 4.2 Production Deployment Steps

```bash
# Tag the release
git tag -a v1.0.1-july-2026-fixes -m "Rearfoot alignment & FPA fixes (July 2026)"
git push origin v1.0.1-july-2026-fixes

# Trigger production deployment (your CD pipeline)
# Usually: merge to main → CI runs tests → CD deploys to ECS/Lambda
```

### 4.3 Post-Deployment Smoke Test

Within 5 minutes of deployment going live:

```bash
# Verify production API is healthy
curl https://api.solearium.com/health

# Create a test session
curl -s -X POST https://api.solearium.com/api/v1/sessions \
  -H "X-API-Key: $PROD_API_KEY" -d {...}

# Monitor error rates
# Check Sentry dashboard for new errors
# Check CloudWatch logs for worker exceptions
# Check Prometheus metrics for latency spikes
```

### 4.4 Monitoring & Rollback

Monitor for **24 hours** post-deployment:

- [ ] **Error rate**: Should remain < 0.1% (same as pre-deployment).
- [ ] **Rearfoot alignment angles**: Check that distributions stay within ±30° (query S3 profile samples).
- [ ] **FPA values**: Check that nulling works (unreliable values should be `null`, not garbage).
- [ ] **Processing time**: Should remain ~60s per session (same as before).
- [ ] **Worker health**: No stuck tasks, no memory leaks.

**If issues arise:**

```bash
# Rollback to previous version
git revert HEAD
git push origin main
# (Redeploy via CD pipeline)
```

---

## Real Static Photo Test Protocol

### Objective

Validate that the static posterior photo upload feature works end-to-end with a real compliant standing photo, and produces anatomically plausible rearfoot alignment measurements.

### Equipment & Environment

**Photographer setup:**
- Smartphone or camera (1080p+ resolution).
- Level floor, good lighting (natural or studio), plain background (optional but ideal).
- 2–3 metres clear space behind the subject.

**Subject requirements:**
- Volunteer (or staff member) aged 18+.
- Barefoot (no shoes, socks, or orthotics).
- Shorts or capris (knees must be bare below mid-thigh).
- Natural posture (feet shoulder-width apart, arms at sides, relaxed gaze forward).

### Photography Protocol

1. **Positioning:**
   - Subject stands facing **away** from camera (posterior view).
   - Camera is at approximately **hip height** (aligned with the subject's greater trochanter).
   - Camera is **2–3 metres** behind the subject (full body visible, head to toes).
   - Subject's feet are **shoulder-width apart** and clearly visible.

2. **Capture:**
   - Take **3 photos** (burst mode or 3 sequential shots to account for slight movement).
   - Ensure **full body is visible**: head, torso, waist, knees, ankles, feet (no cropping).
   - High resolution: at least 1920×1080; portrait orientation is preferred.
   - Focus on the subject's lower legs and feet (confirm sharpness before proceeding).

3. **Quality checklist:**
   - [ ] Head and shoulders visible
   - [ ] Full torso visible (from neck to waist)
   - [ ] Full legs visible (hip to ankle)
   - [ ] Both feet fully visible and in focus
   - [ ] No cropping of any body part
   - [ ] Good lighting (no deep shadows on feet/ankles)
   - [ ] Subject is barefoot and upright
   - [ ] Photo is in landscape or portrait, but full body fits in frame

### Processing Protocol

1. **Select best photo** from the 3 shots (sharpest, best framing).

2. **Upload to staging:**
   ```bash
   SESSION_ID=$(curl -s -X POST http://staging-api:8000/api/v1/sessions \
     -H "Content-Type: application/json" \
     -H "X-API-Key: staging-test-key-change-in-production" \
     -d '{
       "patient_id": "real_static_photo_test",
       "trial_condition": "barefoot",
       "anthropometrics": {
         "height_cm": 175, "mass_kg": 70,
         "foot_length_mm": {"L": 260, "R": 260},
         "foot_width_mm": {"L": 95, "R": 95},
         "dominant_foot": "right"
       }
     }' | jq -r '.session_id')

   # Upload just the static photo (no walking videos for this test)
   curl -s -X POST "http://staging-api:8000/api/v1/sessions/$SESSION_ID/uploads?camera_view=static_posterior" \
     -H "X-API-Key: staging-test-key-change-in-production" \
     -F "file=@real_static_standing_photo.jpg"
   ```

3. **Process:**
   ```bash
   curl -s -X POST "http://staging-api:8000/api/v1/sessions/$SESSION_ID/process" \
     -H "X-API-Key: staging-test-key-change-in-production" -d '{}'

   # Poll until complete
   for i in {1..30}; do
     STATUS=$(curl -s "http://staging-api:8000/api/v1/sessions/$SESSION_ID/status" \
       -H "X-API-Key: staging-test-key-change-in-production" | jq -r '.status')
     [ "$STATUS" = "COMPLETED" ] && break
     sleep 3
   done
   ```

4. **Verify results:**
   ```bash
   PROFILE=$(curl -s "http://staging-api:8000/api/v1/sessions/$SESSION_ID/profile" \
     -H "X-API-Key: staging-test-key-change-in-production" | jq '.profile')

   echo "Rearfoot alignment:"
   echo "$PROFILE" | jq '.rearfoot_alignment'

   echo "Wedging prescription:"
   echo "$PROFILE" | jq '.wedging_prescription'
   ```

### Expected Outcomes

For a healthy, normally-aligned subject with no obvious pronation/supination issues:

| Metric | Expected Range | Passes? |
|--------|-----------------|---------|
| `rearfoot_alignment.angle_deg.L` | ±5 to ±15° | [ ] |
| `rearfoot_alignment.angle_deg.R` | ±5 to ±15° | [ ] |
| `rearfoot_alignment.method` | `"static_image"` | [ ] |
| `rearfoot_alignment.frame_count.L` | `1` (single frame) | [ ] |
| `rearfoot_alignment.classification.L` | `"normal"` or `"mild_*"` | [ ] |
| `rearfoot_alignment.classification.R` | `"normal"` or `"mild_*"` | [ ] |
| `wedging_prescription.left_wedge_degree_deg` | 0–5° (or `null` if normal) | [ ] |
| `wedging_prescription.right_wedge_degree_deg` | 0–5° (or `null` if normal) | [ ] |
| `wedging_prescription.clinical_rationale` | No "dynamic gait" disclaimer | [ ] |
| Processing time | < 10 seconds (static only) | [ ] |
| Worker logs | No errors, no "cropped image" warnings | [ ] |

**If any outcome fails:** Inspect the photo (may be cropped) and worker logs, then re-run with a corrected photo.

### Sign-Off

Once results are verified and within expected ranges:

- [ ] Real static photo test **PASSED**.
- [ ] Staging deployment is approved for promotion to production.

---

## Summary

| Phase | Duration | Blocker? | Approval |
|-------|----------|----------|----------|
| Setup | 1–2 hours | No | DevOps |
| Regression testing | 1–2 hours | **YES** | QA |
| Real static photo test | 1–2 hours | **YES** | Clinical |
| Production deployment | 30 min | No | DevOps + PM |

**Total time to production:** ~4–6 hours once all prerequisites are in place.

---

*Last updated: 2026-07-18*
