# ToneTrace AI — Backend Runbook & Operations Guide

This runbook provides actionable operational instructions for bootstrapping, testing, running, and troubleshooting the ToneTrace AI backend platform.

---

## 1. Quickstart Checklist

### 1.1 Development Environment Setup
1. **Clone the repository**:
   ```bash
   git clone <repo-url>
   cd "ToneTrace AI"
   ```

2. **Initialize Python 3.12 Virtual Environment with `uv`**:
   ```bash
   uv venv --python 3.12
   # Activate on Windows:
   .venv\Scripts\activate
   # Activate on macOS/Linux:
   source .venv/bin/activate
   ```

3. **Install Package & Dependencies**:
   ```bash
   uv pip install -e ".[dev]"
   ```

4. **Prepare Environment File**:
   ```bash
   cp .env.example .env
   ```

---

## 2. Database Migrations & Neon Connection

ToneTrace AI uses two distinct connection strings for Neon:
- `DATABASE_URL`: Pooled connection endpoint for application runtime traffic.
- `DIRECT_URL`: Direct unpooled connection endpoint for Alembic migrations.

### 2.1 Applying Migrations
```bash
# Check current migration revision
alembic current

# Apply pending migrations
alembic upgrade head

# Downgrade one revision
alembic downgrade -1
```

---

## 3. Elasticsearch Search Subsystem Operations (Phase 3)

### 3.1 Verifying Cluster Connectivity
Test live cluster status and latency:
```bash
curl -X GET "http://localhost:8000/health/ready"
```
Or via python directly:
```bash
uv run python -c "from app.providers.search_provider import get_search_provider; print(get_search_provider().check_health())"
```

### 3.2 Full Reindex from PostgreSQL
To rebuild both products and ingredients indices from PostgreSQL:
```bash
curl -X POST "http://localhost:8000/api/v1/search/reindex" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

### 3.3 Triggering Outbox Synchronization
To manually process pending transactional outbox events:
```bash
curl -X POST "http://localhost:8000/api/v1/search/sync-outbox?batch_size=50" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

### 3.4 Searching Products & Ingredients
Search products with brand filter and sensitivity avoidance:
```bash
curl -X GET "http://localhost:8000/api/v1/search/products?q=hydration&category=serum&exclude_ingredients=fragrance" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

Search ingredients with autocomplete:
```bash
curl -X GET "http://localhost:8000/api/v1/search/ingredients?q=niacin" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

---

## 5. Product & Ingredient Catalogue Operations (Phase 4)

### 5.1 Barcode Ingestion from Open Beauty Facts
Ingest a product from packaging barcode (e.g. CeraVe Moisturizing Cream `3337875597371`):
```bash
curl -X POST "http://localhost:8000/api/v1/products/ingest/barcode/3337875597371" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

### 5.2 Product & Formula Lookup
Fetch comprehensive product detail:
```bash
curl -X GET "http://localhost:8000/api/v1/products/barcode/3337875597371"
```

Fetch ordered packaging ingredients for a specific product:
```bash
curl -X GET "http://localhost:8000/api/v1/products/<PRODUCT_UUID>/ingredients"
```

### 5.3 Recording a Product Reformulation
Append a new formulation revision while preserving historical formula versions:
```bash
curl -X POST "http://localhost:8000/api/v1/products/<PRODUCT_UUID>/reformulate" \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "formula_version": "2024-reformulation",
    "raw_ingredient_text": "Water, Niacinamide, Glycerin, Ceramide NP",
    "ingredient_names": ["Water", "Niacinamide", "Glycerin", "Ceramide NP"],
    "data_source_code": "manufacturer_notice"
  }'
```

### 5.4 Recording Commercial Offers
Record merchant price in exact minor units (e.g. `$24.50` = `2450` USD):
```bash
curl -X POST "http://localhost:8000/api/v1/products/<PRODUCT_UUID>/offers" \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "merchant_name": "Sephora",
    "price_minor_units": 2450,
    "currency": "USD",
    "offer_url": "https://sephora.com/product-example",
    "is_in_stock": true
  }'
```

---

## 4. Failure Simulation & Recovery Runbook

### 4.1 Simulating Elasticsearch Cluster Failure
1. Set `ELASTICSEARCH_URL=http://localhost:9999` in `.env` (or simulate cluster offline).
2. Query `/api/v1/search/products`: Returns `503 Service Unavailable` with `"Search service is currently unavailable"`.
3. Check `/health/ready`: Returns degraded status with connection error details without crashing.
4. Mutate product in PostgreSQL: Entity is saved, and a row is recorded in `search_outbox` with `status='pending'`. No user data is lost.
5. Restore cluster credentials in `.env`.
6. Run `POST /api/v1/search/sync-outbox`: All pending events are dispatched and marked `completed`.

---

## 5. OCR & Label Scanning Operations (Phase 5)

### 5.1 Configuring OCR Providers
Set the provider in `.env`:
```ini
# Online OCR (OCR.space Free API)
OCR_PROVIDER=ocr_space
OCR_API_KEY=K8503831748457488957
OCR_BASE_URL=https://api.ocr.space/parse/image

# Storage Configuration
STORAGE_PROVIDER=local
STORAGE_LOCAL_DIR=./var/storage
STORAGE_SIGNING_SECRET=tonetrace-storage-secret-key-change-in-production-12345
```
For local testing without internet access, set:
```ini
OCR_PROVIDER=mock
```

### 5.2 Uploading a Product Label for Scanning
```bash
curl -X POST http://localhost:8000/api/v1/ocr/scans \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -F "file=@label.jpg;type=image/jpeg" \
  -F "idempotency_key=unique-upload-123"
```

### 5.3 Reviewing and Confirming Candidates
```bash
curl -X POST http://localhost:8000/api/v1/ocr/scans/<SCAN_ID>/confirm \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "ingredients": [
      {"candidate_id": "<CANDIDATE_UUID>", "position": 1, "name": "Water (Aqua)", "is_confirmed": true},
      {"candidate_id": null, "position": 2, "name": "Niacinamide", "is_confirmed": true}
    ]
  }'
```

---

## 6. Ingredient Evidence & Channel3 Operations (Phase 6)

### 6.1 Configuring PubMed, CosIng, and Channel3
Add the following variables to `.env` (never commit secret keys):
```ini
# NCBI PubMed E-utilities
PUBMED_BASE_URL=https://eutils.ncbi.nlm.nih.gov/entrez/eutils
PUBMED_TOOL_NAME=tonetrace_ai
PUBMED_CONTACT_EMAIL=engineering@tonetrace.ai
PUBMED_API_KEY=

# European Commission CosIng Search API
COSING_API_URL=https://api.tech.ec.europa.eu/search-api/prod/rest/search
COSING_API_KEY=85942466-f22d-4c56-9682-6c1d3d35103d
EVIDENCE_CACHE_TTL_HOURS=168

# Channel3 Universal Product Catalog
CHANNEL3_BASE_URL=https://api.trychannel3.com
CHANNEL3_API_KEY=<YOUR_CHANNEL3_API_KEY>
```

### 6.2 Refreshing & Inspecting Ingredient Evidence
```bash
# Trigger restricted CosIng + PubMed retrieval/refresh
curl -X POST http://localhost:8000/api/v1/ingredients/<INGREDIENT_UUID>/evidence/refresh \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"sources": ["cosing", "pubmed"], "topic": "hyperpigmentation", "max_pubmed_results": 5, "force_refresh": false}'

# Query cached, epistemically separated evidence
curl "http://localhost:8000/api/v1/ingredients/<INGREDIENT_UUID>/evidence?page=1&page_size=20"
```

### 6.3 Searching Channel3 & Syncing Product Offers
```bash
# Search Channel3 universal product catalog
curl "http://localhost:8000/api/v1/products/channel3/search?query=Niacinamide&limit=5" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"

# Sync live Channel3 merchant offers for a PostgreSQL catalog product
curl -X POST http://localhost:8000/api/v1/products/<PRODUCT_UUID>/offers/sync-channel3 \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

---

## 7. Gemini Grounded Explanations Operations (Phase 7)

### 7.1 Configuring Gemini
Add to `.env`:
```ini
GEMINI_API_KEY=<YOUR_GEMINI_API_KEY>
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_TIMEOUT_SECONDS=20.0
GEMINI_MAX_RETRIES=2
GEMINI_MAX_CONTEXT_CHARS=16000
AI_RATE_LIMIT_PER_MINUTE=10
```

### 7.2 Requesting a Grounded Explanation
```bash
curl -X POST http://localhost:8000/api/v1/ai/explanations \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "schema_version": "1.0",
    "question": "How does Niacinamide in this product relate to hyperpigmentation?",
    "product_ids": ["<PRODUCT_UUID>"],
    "ingredient_ids": ["<INGREDIENT_UUID>"]
  }'
```

---

## 8. Skin Analysis & Skin Story Operations (Phase 8)

### 8.1 Configuring YouCam S2S v2.0 or Mock Provider
Add to `.env`:
```ini
SKIN_ANALYSIS_PROVIDER=youcam
SKIN_ANALYSIS_API_KEY=<YOUR_YOUCAM_BEARER_API_KEY>
SKIN_ANALYSIS_SECRET_KEY=<YOUR_YOUCAM_SECRET_OR_RSA_KEY>
SKIN_ANALYSIS_BASE_URL=https://yce-api-01.makeupar.com
SKIN_ANALYSIS_TIMEOUT_SECONDS=20.0
SKIN_ANALYSIS_RETENTION_DAYS=90
```

### 8.2 Submitting a Skin Scan & Viewing Longitudinal Skin Story
```bash
# 1. Grant explicit consent for facial skin data processing
curl -X PUT http://localhost:8000/api/v1/me/consents/skin_data_processing \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"policy_version": "1.0.0", "is_granted": true}'

# 2. Upload facial scan image with capture conditions
curl -X POST http://localhost:8000/api/v1/skin/scans \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -F "file=@selfie.jpg" \
  -F "lighting_condition=natural_daylight" \
  -F "camera_angle=frontal" \
  -F "cosmetics_worn=false" \
  -F "idempotency_key=scan-2026-10-27-am"

# 3. Retrieve longitudinal Skin Story
curl http://localhost:8000/api/v1/skin/story \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

---

## 9. My Shelf & Product Discovery Operations (Phase 9)

### 9.1 Managing My Shelf & Product Reactions
```bash
# Add a catalogue-linked or custom product to My Shelf
curl -X POST http://localhost:8000/api/v1/me/shelf \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "custom_name": "Compounded Azelaic Gel",
    "custom_brand": "Local Derm Pharmacy",
    "custom_category": "treatment",
    "status": "in_use",
    "private_notes": "Applying in evening routine."
  }'

# Discover products with explainable suitability rules
curl "http://localhost:8000/api/v1/discovery/products?goal=hyperpigmentation&sort_by=suitability_desc" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

---

## 10. Routines, Reminders & Product Reactions Operations (Phase 10)

### 10.1 Creating a Routine, Logging Completions & Configuring Reminders
```bash
# Create an ordered routine
curl -X POST http://localhost:8000/api/v1/me/routines \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Morning Brightening & SPF Routine",
    "time_of_day": "morning",
    "frequency": "daily",
    "preferred_local_time": "08:00",
    "steps": [
      {"step_order": 1, "custom_instruction": "Gentle cleanse with lukewarm water"},
      {"step_order": 2, "custom_instruction": "Apply broad-spectrum SPF 50"}
    ]
  }'

# Configure reminder preferences & timezone
curl -X PUT http://localhost:8000/api/v1/me/reminders \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "reminders_enabled": true,
    "preferred_channels": ["in_app"],
    "morning_reminder_enabled": true,
    "morning_reminder_time": "08:00",
    "evening_reminder_enabled": true,
    "evening_reminder_time": "21:00",
    "quiet_hours_enabled": true,
    "quiet_hours_start": "22:30",
    "quiet_hours_end": "07:00",
    "timezone_override": "America/New_York"
  }'

# Record a product reaction (automatically evaluates urgent-care guidance)
curl -X POST http://localhost:8000/api/v1/me/product-reactions \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "product_id": "<PRODUCT_UUID>",
    "reaction_type": "allergic_suspect",
    "severity": "severe",
    "symptoms": ["facial swelling", "hives"],
    "is_rapidly_worsening": true
  }'
```

---

## 11. Automated Testing & Verification

Run the full automated test suite (147 tests covering Auth, Profiles, Outbox, Search, Catalogue, OCR, Evidence, Channel3, Gemini Grounded Explanations, Skin Analysis & Story, My Shelf & Product Discovery, Routines, Reminders & Reactions, and Security & Release Verification):
```bash
uv run pytest
```

Run code formatting and style checks:
```bash
uv run ruff check .
uv run ruff format --check .
```

---

## 12. Phase 11 Production Operations, Security & Release Guide

### 12.1 Complete Environment Variable Inventory

| Variable | Required in Prod | Default (Dev) | Purpose & Security Notes |
| :--- | :--- | :--- | :--- |
| `ENVIRONMENT` | Yes | `development` | Must be `production` in production deployments. Enforces strict security guards. |
| `DEBUG` | Yes (`false`) | `false` | **Never** enable in production (`Settings` raises a critical startup violation if `True`). |
| `LOG_LEVEL` | No | `INFO` | Structured JSON logger verbosity (`INFO`, `WARNING`, `ERROR`). |
| `ALLOWED_CORS_ORIGINS` | Yes | `http://localhost:3000,...` | Explicit comma-separated HTTPS origins. Wildcard `*` is blocked in production. |
| `DATABASE_URL` | Yes | `postgresql+psycopg://...` | Pooled PostgreSQL connection URL (`sslmode=require` on Neon). |
| `DIRECT_URL` | Yes (Migrations) | `None` | Unpooled PostgreSQL connection URL used by Alembic DDL migrations. |
| `AUTH_PROVIDER` | No | `local` | Authentication backend (`local` JWT or `supabase`). |
| `AUTH_JWT_SECRET` | Yes | *(dev placeholder)* | Minimum 32-byte high-entropy secret for HS256 signing. |
| `AUTH_JWT_ISSUER` | No | `tonetrace-ai` | Validated `iss` claim on every JWT. |
| `AUTH_JWT_AUDIENCE` | No | `tonetrace-users` | Validated `aud` claim on every JWT. |
| `AUTH_ACCESS_TOKEN_EXPIRE_MINUTES` | No | `30` | Short-lived access token lifetime. |
| `AUTH_REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | Refresh session lifetime with single-use token rotation & replay revocation. |
| `AUTH_RATE_LIMIT_ENABLED` | Yes (`true`) | `true` | Enables brute-force and costly-endpoint rate limiters. |
| `ALLOW_DEV_AUTH_BYPASS` | Yes (`false`) | `false` | Strictly forbidden in `staging` and `production`. |
| `ELASTICSEARCH_ENABLED` | No | `true` | Master toggle for Elasticsearch search & indexing. |
| `ELASTICSEARCH_URL` | Yes (if enabled) | `http://localhost:9200` | Must use `https://` in production. |
| `ELASTICSEARCH_API_KEY` | Yes (if Cloud) | `None` | Scoped Elasticsearch API key with index-level privileges only. |
| `ELASTICSEARCH_INDEX_PREFIX` | No | `tonetrace` | Prefix for versioned indices (`tonetrace_products_v1`, `tonetrace_ingredients_v1`). |
| `OCR_PROVIDER` | Yes | `mock` | `ocr_space` (online), `tesseract` (local), or `mock` (dev/tests only). |
| `OCR_API_KEY` | If `ocr_space` | `None` | OCR.space API key transmitted via `apikey` header over HTTPS. |
| `STORAGE_PROVIDER` | Yes | `local` | Must be `s3` (Cloudflare R2 / AWS S3 private bucket) in production. |
| `STORAGE_SIGNING_SECRET` | Yes | *(dev placeholder)* | Dedicated HMAC secret for expiring private media URLs (`STORAGE_SIGNED_URL_TTL_SECONDS=900`). |
| `STORAGE_S3_BUCKET` / `ENDPOINT_URL` / `ACCESS_KEY_ID` / `SECRET_ACCESS_KEY` | If `s3` | `None` | Private S3/R2 bucket credentials. Never enable public bucket ACLs. |
| `PUBMED_CONTACT_EMAIL` / `PUBMED_API_KEY` | Recommended | `engineering@tonetrace.ai` | NCBI E-utilities identification and rate-limit key (10 req/s with key, 3 req/s without). |
| `COSING_API_KEY` | No | `85942466-...` | European Commission CosIng Search API key. |
| `CHANNEL3_API_KEY` | Optional | `None` | Channel3 catalog & live price comparison key (`x-api-key`). |
| `GEMINI_API_KEY` | Yes (for AI) | `None` | Official Google GenAI SDK key for grounded explanations. |
| `GEMINI_MODEL` | No | `gemini-3.5-flash-lite` | Configured Gemini model for structured JSON grounded output. |
| `SKIN_ANALYSIS_PROVIDER` | Yes | `mock` | Set to `youcam` only after commercial credentials (`SKIN_ANALYSIS_API_KEY`) are provisioned. |
| `SKIN_ANALYSIS_RETENTION_DAYS` | No | `90` | Default retention window for private facial scan photos (`ScanMedia`). |

Run `Settings.audit_production_readiness()` at deployment check time to surface any remaining mock providers or default signing secrets:
```bash
uv run python -c "from app.core.config import get_settings; print(get_settings().audit_production_readiness())"
```

### 12.2 External Provider Setup Links & Prerequisites
- **Neon PostgreSQL**: [https://console.neon.tech](https://console.neon.tech) — Provision pooled (`DATABASE_URL`) and direct (`DIRECT_URL`) connection strings with `sslmode=require`.
- **Elastic Cloud / Elasticsearch 8.x**: [https://cloud.elastic.co](https://cloud.elastic.co) — Create a deployment and generate an API key restricted to `tonetrace_*` indices (`read`, `write`, `manage`, `create_index`).
- **Google Gemini API (`google-genai`)**: [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey) — Provision `GEMINI_API_KEY` and monitor free-tier vs. paid-tier RPM/RPD quotas.
- **OCR.space API**: [https://ocr.space/ocrapi](https://ocr.space/ocrapi) — Provision `OCR_API_KEY` (free tier has 25,000 requests/month and 1 MB file size limit; Pro tier recommended for production).
- **Perfect Corp / YouCam Skin Analysis S2S API v2.0**: [https://www.perfectcorp.com/business/products/ai-skin-diagnostic](https://www.perfectcorp.com/business/products/ai-skin-diagnostic) — Requires enterprise contract, `SKIN_ANALYSIS_API_KEY`, and `SKIN_ANALYSIS_SECRET_KEY`.
- **Cloudflare R2 / Private S3 Storage**: [https://dash.cloudflare.com](https://dash.cloudflare.com) — Create a strictly private bucket (`STORAGE_S3_BUCKET`) with zero public access and configure an S3 API token.

### 12.3 Database Migration & Rollback Precautions
1. Always run migrations against `DIRECT_URL` (unpooled connection) before rolling out new application containers:
   ```bash
   uv run alembic check
   uv run alembic upgrade head
   ```
2. **Rollback**: Test downgrades in staging first (`uv run alembic downgrade -1`). Never drop columns containing user consent audit logs or active formulation history without a verified snapshot.

### 12.4 Image Storage (PostgreSQL BYTEA MVP Override) & Retention Lifecycle

> [!NOTE]
> **MVP Architectural Decision**: For the hackathon MVP, Neon PostgreSQL is the sole persistent application data store. Validated small image bytes are stored directly in PostgreSQL `BYTEA` (`MediaAsset.image_bytes`). No external object-storage provider (S3 / Cloudflare R2 / GCS) or bucket credentials are required.

- **PostgreSQL BYTEA Storage**:
  - Image bytes are stored in `media_assets.image_bytes` (`BYTEA`) using SQLAlchemy deferred column loading (`mapped_column(LargeBinary, deferred=True)`), ensuring standard database queries never load raw binary data into memory.
  - Maximum upload size is bounded at 5MB (`UPLOAD_MAX_FILE_SIZE_BYTES=5242880`).
  - Access is restricted strictly to authenticated owners via `GET /api/v1/ocr/assets/by-id/{asset_id}` and `DELETE /api/v1/ocr/assets/by-id/{asset_id}`, or via short-lived HMAC-signed URLs (`GET /api/v1/ocr/assets/view`). Non-owners receive HTTP 404 (preventing ID enumeration).
- **Retention & Ephemeral Cleanup**:
  - Configurable via `OCR_IMAGE_RETENTION_POLICY` (`retain` vs. `delete_after_ocr`) and `OCR_IMAGE_RETENTION_DAYS`.
  - When `OCR_IMAGE_RETENTION_POLICY=delete_after_ocr`, image bytes are permanently purged immediately after OCR candidate segmentation completes.
- **Operational Trade-offs of In-Database Image Storage**:
  - *Database Sizing*: Storing binary images in `BYTEA` increases database disk consumption.
  - *Transfer & Egress*: Large binary payloads increase PostgreSQL connection pool bandwidth requirements.
  - *Backup & Restore*: Increases WAL volume and pg_dump / Neon snapshot backup/restore durations.
- **Post-Hackathon Migration Path**:
  - Transitioning to dedicated private object storage (Cloudflare R2 or AWS S3) with pre-signed upload/download URLs is planned as a post-hackathon improvement rather than a launch blocker.

### 12.5 Object Storage Lifecycle, Consent Revocation & Account Deletion
- **Private Storage Only**: All label images (`MediaAsset`) and facial photos (`ScanMedia`) use random UUID keys (`ocr/{user_id}/{uuid}.{ext}`, `skin/{user_id}/{uuid}.{ext}`) and short-lived HMAC-signed URLs (`900s` TTL).
- **Consent Revocation (`PUT /api/v1/me/consents/skin_data_processing` with `is_granted=false`)**: Immediately purges the user's retained facial scan photos from object storage/BYTEA and marks `ScanMedia.is_deleted = True`.
- **Full Account Deletion (`DELETE /api/v1/me`)**: Immediately purges all `MediaAsset` and `ScanMedia` objects belonging to the user from object storage/BYTEA, writes a sanitized `SystemAuditLog` entry (`user_account_deleted`), and cascades deletion across `users`, `user_sessions`, `user_profiles`, `skin_profiles`, `user_consents`, `ocr_jobs`, `skin_scans`, `user_products`, `routines`, `reminder_preferences`, and `product_reactions`.

### 12.6 Logging, Monitoring & Backup Expectations
- **Redacted Structured Logging**: `app/core/logging.py` outputs structured JSON logs with `request_id` correlation and automatically redacts `password`, `token`, `secret`, `authorization`, `api_key`, `jwt`, and `cookie` fields.
- **Health Probes**:
  - Liveness: `GET /health/live` (container uptime check).
  - Readiness: `GET /health/ready` (verifies PostgreSQL connectivity and reports Elasticsearch status).
- **Backups**: Rely on Neon PostgreSQL Point-in-Time Restore (PITR) configured for at least 7–30 days in production, plus daily S3/R2 bucket replication for unpurged media assets.

### 12.6 Post-Deployment Smoke Test Checklist
1. `GET /health/live` -> `200 OK` (`status: "healthy"`).
2. `GET /health/ready` -> `200 OK` (`database.connected: true`).
3. Verify `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and `X-Request-ID` headers are present on responses.
4. Register/authenticate a smoke-test user (`POST /api/v1/auth/register` or `/login`), fetch `/api/v1/me`, and clean up via `DELETE /api/v1/me`.

