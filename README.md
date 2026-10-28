# ToneTrace AI — Backend Platform

ToneTrace AI is an intelligent skincare companion backend platform. Engineered for high reliability, strict zero-trust security, modular integration readiness, production-grade observability on FastAPI, PostgreSQL (Neon), and an Elasticsearch search subsystem.

---

## Architecture Overview

- **Runtime & Web Framework**: Python 3.12, FastAPI, Uvicorn (ASGI)
- **First-Party Authentication**: Argon2id password hashing (`pwdlib[argon2]`), signed JWT access tokens (`PyJWT`), rotating refresh tokens stored strictly as SHA-256 hashes (`user_sessions`), and in-memory rate limiting.
- **Search Subsystem**: Elasticsearch 8.x / 9.x with versioned index mappings, edge-ngram autocomplete analyzers, and stable read/write aliases.
- **Product & Ingredient Catalogue**: Provenance-aware cosmetic formulations with historical formula version preservation, conservative INCI ingredient parsing, and Open Beauty Facts adapter.
- **Commercial Offer Separation**: Pricing and merchant availability stored separately from scientific formulation data in integer minor currency units.
- **Reliable Data Sync**: PostgreSQL is the single authoritative source of truth. Data synchronization uses the **Transactional Outbox Pattern** (`search_outbox` table) with bounded bulk indexing, exponential backoff retries, and document-level failure tracking.
- **Settings & Validation**: Pydantic v2 & Pydantic Settings with fail-fast validation and secret masking (`SecretStr`)
- **Persistence & Migrations**: SQLAlchemy 2.0 (Async Engine via `psycopg 3`), Alembic
- **Database Target**: Neon Serverless PostgreSQL (remote), with dual-URL pooling configuration
- **Local Infrastructure**: Docker Compose running single-node Elasticsearch 8.x for local search indexing
- **OCR & Product-Label Scanning**: Replaceable OCR subsystem (verified OCR.space Free API adapter, local Tesseract candidate, deterministic mock adapter), private object storage with HMAC-SHA256 time-bounded signed URLs, conservative candidate segmentation, and human review workflows.
- **Quality & Testing**: Pytest (104 automated tests), pytest-asyncio, HTTPX, and Ruff (linter/formatter)
- **Dependency Management**: `pyproject.toml` managed with `uv` for reproducible, deterministic installs

---

## Project Structure

```text
├── app/
│   ├── api/
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py            # First-party auth (register, login, refresh, logout)
│   │   │   ├── catalog.py         # Product & ingredient catalogue, barcodes, formulas
│   │   │   ├── health.py          # Liveness, readiness, and safe integration probes
│   │   │   ├── me.py              # User profiles, skin profiles, sensitivities, consents
│   │   │   └── search.py          # Product & ingredient search, reindex, outbox sync
│   │   ├── __init__.py
│   │   └── router.py              # Root API v1 routing registry
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py              # Strict Pydantic settings with secret masking
│   │   ├── errors.py              # Centralized domain exceptions & global handlers
│   │   ├── logging.py             # Structured logging with request-ID binding
│   │   └── security.py            # Argon2id, PyJWT, token rotation, and rate limiting
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py                # SQLAlchemy DeclarativeBase & common mixins
│   │   ├── models.py              # Database models: users, catalog, formulas, offers, outbox
│   │   └── session.py             # Async engine & sessionmaker lifecycle
│   ├── providers/                 # Outbound provider integration interfaces
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── channel3.py            # Channel3 retail API contract adapter
│   │   ├── open_beauty_facts.py   # Open Beauty Facts API adapter (ODbL 1.0)
│   │   └── search_provider.py     # Elasticsearch client, mappings, and bulk helpers
│   ├── schemas/                   # Pydantic exchange contracts
│   │   ├── __init__.py
│   │   ├── auth.py                # Register, login, refresh, user response schemas
│   │   ├── catalog.py             # Products, formulas, ingredients, offers schemas
│   │   ├── common.py              # Envelope & pagination schemas
│   │   ├── consent.py             # User consent and policy tracking schemas
│   │   ├── errors.py              # Standardized API error payloads
│   │   ├── health.py              # Health check status schemas
│   │   ├── profile.py             # Profiles, skin concerns, sensitivities schemas
│   │   └── search.py              # Product/ingredient search queries, hits, and facets
│   ├── services/                  # Business logic services
│   │   ├── __init__.py
│   │   ├── auth_service.py        # Authentication & rotating session management
│   │   ├── base.py
│   │   ├── catalog_service.py     # Catalogue ingestion, provenance, reformulation
│   │   ├── profile_service.py     # Profile & consent domain workflows
│   │   ├── search_outbox_service.py # Transactional outbox sync processor
│   │   └── search_service.py      # Product/ingredient search & full reindexer
│   ├── __init__.py
│   └── main.py                    # FastAPI application factory & lifespan
├── alembic/                       # Database migrations directory
│   ├── versions/
│   ├── env.py
│   └── script.py.mako
├── docs/                          # Architecture decisions & runbook
│   ├── architecture.md
│   └── runbook.md
├── tests/                         # Pytest test suite (86 automated tests)
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_catalog.py
│   ├── test_config.py
│   ├── test_consents.py
│   ├── test_db.py
│   ├── test_errors.py
│   ├── test_health.py
│   ├── test_profiles.py
│   ├── test_search.py
│   └── test_security.py
├── .env.example                   # Reference environment configuration
├── .gitignore
├── alembic.ini                    # Alembic configuration
├── Dockerfile                     # Multi-stage non-root container image
├── docker-compose.yml             # Local infrastructure (Elasticsearch 8.x)
├── pyproject.toml                 # Package definition & tool configs
└── README.md
```

---

## Search & Synchronization Architecture (Phase 3)

1. **PostgreSQL Authoritative Source of Truth**:
   - `products`, `ingredients`, and `product_ingredients` store authoritative catalog data.
   - Elasticsearch contains derived, rebuildable search indices. If an index is lost or corrupted, it can be regenerated completely using `POST /api/v1/search/reindex`.
2. **Transactional Outbox Synchronization**:
   - Any catalog write writes a `search_outbox` row inside the **same database transaction**.
   - The `SearchOutboxService` batch processor dispatches bounded chunks (default 50) using the official Elasticsearch bulk helper.
   - Partial failures are handled per-document: successful items are marked `completed`, failed items record error details and increment `retry_count` with backoff.
3. **Versioned Indexing & Aliases**:
   - `tonetrace_products_v1` pointed to by `tonetrace_products_current`
   - `tonetrace_ingredients_v1` pointed to by `tonetrace_ingredients_current`
4. **Analyzers**:
   - `skincare_text_analyzer`: Standard tokenizer + lowercase + asciifolding.
   - `skincare_autocomplete_analyzer`: Edge-ngram (min_gram=2, max_gram=15) for responsive type-ahead matching.
5. **Deterministic Sorting & Sensitivity Filtering**:
   - Product search supports filtering out products containing specific ingredient names (`exclude_ingredients`), directly integrating with user sensitivities.
   - Deterministic sorting uses `_score: desc, id: asc` to guarantee predictable pagination without item jitter.
6. **Graceful Degradation & Readiness**:
   - If Elasticsearch is disabled or fails, endpoints return a clear `503 Service Unavailable` with structured diagnostic details instead of returning deceptive empty result lists.

---

## API Endpoints Reference

### Catalog Search (`/api/v1/search`)
- `GET /api/v1/search/products`: Search cosmetic products with query text, brand, category, and ingredient exclusion. Includes category/brand facet aggregations.
- `GET /api/v1/search/ingredients`: Search ingredients with autocomplete, function, and safety rating filters. Includes facet aggregations.
- `POST /api/v1/search/reindex`: Rebuild all Elasticsearch indices directly from authoritative PostgreSQL tables.
- `POST /api/v1/search/sync-outbox`: Manually process pending transactional outbox sync events to Elasticsearch.

### Authentication (`/api/v1/auth`)
- `POST /api/v1/auth/register`: Create user account with display name and initial blank profile. Returns `User` and token pair.
- `POST /api/v1/auth/login`: Authenticate with email and password. Returns `User` and token pair.
- `POST /api/v1/auth/refresh`: Exchange valid refresh token for a new access token and rotated refresh token.
- `POST /api/v1/auth/logout`: Revoke a single refresh token session.
- `POST /api/v1/auth/logout-all`: Revoke all active sessions for the current authenticated user.

### Profiles & Sensitivities (`/api/v1/me`)
- `GET /api/v1/me`: Retrieve full profile summary (user, profile, skin attributes, sensitivities, preferences).
- `PATCH /api/v1/me`: Update display name or timezone.
- `GET /api/v1/me/skin-profile`: Get self-reported skin type, concerns, and skincare goals.
- `PUT /api/v1/me/skin-profile`: Update skin attributes.
- `GET /api/v1/me/sensitivities`: List reported ingredient sensitivities.
- `POST /api/v1/me/sensitivities`: Add a new ingredient sensitivity/avoidance.
- `DELETE /api/v1/me/sensitivities/{id}`: Delete an ingredient sensitivity record.
- `GET /api/v1/me/consents`: List all explicit consent records.
- `PUT /api/v1/me/consents/{purpose}`: Grant or revoke consent with audit metadata.

### Health & Observability (`/health` & `/api/v1/health`)
- `GET /health/live`: Fast process vitality check (no external network dependencies).
- `GET /health/ready`: Critical dependency health check (verifies Neon database and Elasticsearch connectivity).
- `GET /health/integrations`: Safe status reporting without secret exposure.

---

## Getting Started

### Prerequisites

- Python 3.12+
- [`uv`](https://github.com/astral-sh/uv) (recommended)
- Docker (optional for local Elasticsearch 8.x)

### 1. Installation

```bash
uv venv --python 3.12
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # macOS / Linux

uv pip install -e ".[dev]"
```

### 2. Environment Configuration

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Configure your Neon database and Elasticsearch settings:
```ini
ENVIRONMENT=development
DATABASE_URL=postgresql://neondb_owner:***@ep-xyz-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require
DIRECT_URL=postgresql://neondb_owner:***@ep-xyz.us-east-2.aws.neon.tech/neondb?sslmode=require
AUTH_JWT_SECRET=tonetrace-dev-insecure-jwt-secret-do-not-use-in-production-1234567890

# Elasticsearch
ELASTICSEARCH_ENABLED=true
ELASTICSEARCH_URL=https://fb49803805804ad5803da3dacd95245a.us-central1.gcp.cloud.es.io:443
ELASTICSEARCH_API_KEY=Vy1hTmVxRUJTNVVzdXNXM2VFb246X2RFZ3h6MXEwb0V2NlVUUFFRYmJ4QQ==
ELASTICSEARCH_INDEX_PREFIX=tonetrace_
```

### 3. Running Database Migrations

Apply pending migrations to Neon PostgreSQL:
```bash
alembic upgrade head
```

### 4. Running the Backend Application

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
- Interactive Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- Interactive ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

### 5. Running the Frontend Mobile Client

The mobile web frontend is housed in `frontend/` and runs on port 3000 (matching backend CORS configuration).

```bash
cd frontend

# Copy environment configuration
cp .env.example .env

# Install dependencies
pnpm install --ignore-scripts

# Start development server on http://localhost:3000
pnpm dev

# Run type checking and test suite
pnpm typecheck
pnpm test
```

- **Proxy vs CORS**: By default, Vite proxies `/api` and `/health` requests to `http://localhost:8000`. For direct CORS, set `VITE_API_BASE_URL=http://localhost:8000` in `frontend/.env`.
- **Responsive Layout**: Designed for a 390px baseline (iPhone 14/15/16). On wider desktop displays, the interface centers a maximum-430px mobile shell.
- **Design System Showcase**: Available directly on the **Showcase** tab for visual review of design tokens, buttons, chips, glass cards, inputs, and error fallbacks.

### 4. Product & Ingredient Catalogue (Phase 4)

- **Provenance Tracking**: Every formulation list preserves its data source (`data_sources`), retrieval timestamp, and raw packaging declaration.
- **Formula Versioning**: When a cosmetic product is reformulated, historical formulas are preserved in `product_ingredient_lists` rather than overwritten.
- **Commercial Separation**: Retail offers (`product_offers`) and prices are strictly separated from chemical formula data, with currency minor units (e.g. cents) and retrieval timestamps.
- **Open Beauty Facts Adapter**: Official v2 adapter with rate limit backoff and ODbL v1.0 attribution.
- **Channel3 Adapter**: Isolated provider contract adapter with honest unconfigured reporting when credentials are not supplied.

#### Catalogue Endpoints
- `GET /api/v1/products/{product_id}` — Product detail with brand, variants, current formula, and offers.
- `GET /api/v1/products/barcode/{barcode}` — Barcode lookup across SKUs.
- `GET /api/v1/products/{product_id}/ingredients` — Ordered ingredient list for current or specific formula version.
- `GET /api/v1/ingredients/{ingredient_id}` — Standardized INCI cosmetic ingredient definition.
- `POST /api/v1/products/ingest/barcode/{barcode}` — Authenticated, rate-limited barcode ingestion.
- `POST /api/v1/products/{product_id}/reformulate` — Record a new formulation version while preserving history.
- `POST /api/v1/products/{product_id}/offers` — Record commercial merchant offer.

### 5. OCR & Product-Label Scanning (Phase 5)

- **Replaceable OCR Subsystem**:
  - **Online OCR Adapter**: Verified integration with OCR.space Free API (`https://api.ocr.space/parse/image`) supporting multipart uploads, rate limit backoff (HTTP 429), and execution status handling.
  - **Local OCR Adapter**: Host Tesseract engine candidate with binary detection and clear failure guidance.
  - **Deterministic Mock Adapter**: Predictable candidate ingredient responses for offline development and CI.
- **Private Object Storage**:
  - Files are never stored under public web roots or exposed via permanent public URLs.
  - `LocalStorageProvider` incorporates traversal immunity and time-limited HMAC-SHA256 signature verification.
  - `S3StorageProvider` provides pre-signed URL generation for S3/Cloudflare R2 deployments.
- **Zero-Trust Input Validation**:
  - Format checks (JPEG, PNG, WebP) with Pillow decoding verification.
  - Bounded dimensions (≤ 4096px) and maximum file size enforcement (≤ 10MB).
  - SHA-256 asset content hashing for integrity.
- **Untrusted Text Handling & Catalog Linking**:
  - Raw OCR output is quarantined and immutable in `ocr_jobs.raw_text`.
  - Conservative segmentation strips marketing filler, percentages, and bullets.
  - Candidates are automatically matched against canonical INCI catalog ingredients (`ingredients`, `ingredient_aliases`).
- **Human Review Workflow**:
  - Extracted formulations remain provisional candidates until verified or corrected via confirmation endpoint.
  - All scans and media assets are strictly isolated to the authenticated owning user.

#### OCR Endpoints
- `POST /api/v1/ocr/scans` — Authenticated upload of label image, validation, OCR execution, and candidate ingredient segmentation. Supports `idempotency_key`.
- `GET /api/v1/ocr/scans/{scan_id}` — Retrieve scan status, raw text, and candidate ingredients (user-scoped).
- `POST /api/v1/ocr/scans/{scan_id}/confirm` — Review, edit, and confirm candidate formulation ingredients.
- `GET /api/v1/ocr/assets/view` — Stream private image asset with valid HMAC signature and expiration timestamp.

### Phase 6: Ingredient Evidence, Research Retrieval & Channel3 Integration
- **Authoritative Scientific & Regulatory Sources**:
  - **European Commission CosIng**: Official EC Search REST API (`GROWTH_COSING`) and official CSV inventory parser for INCI nomenclature, CAS/EC numbers, cosmetic functions, and Regulation (EC) No 1223/2009 restrictions.
  - **NCBI PubMed E-utilities**: Official `esearch.fcgi` and `efetch.fcgi` integration with mandatory `tool` and `email` attribution parameters, rate-limit compliance, study design classification (`rct`, `meta_analysis`, `in_vitro`, etc.), and honest `has_full_text=False` representation.
- **Strict 4-Way Epistemic Separation**:
  1. `identity_reference` — Official CosIng ingredient identity, CAS/EC, functions, and EU regulatory restrictions.
  2. `published_research` — Peer-reviewed PubMed bibliographic records and abstracts (`has_full_text=False`, missing abstracts marked `insufficient`).
  3. `human_interpretation` — Authored/reviewed dermatological interpretations with provenance and immutable review history (`evidence_review_status`).
  4. `marketing_claims` — Commercial/brand packaging claims strictly isolated from scientific evidence (`reference_only`).
- **Channel3 Universal Product Catalog (`channel3-api`)**:
  - Live integration with `https://api.trychannel3.com/v1` using `CHANNEL3_API_KEY` from `.env`, supporting product search, offer hydration, `x-user-id` attribution, and syncing merchant offers in integer minor currency units.

#### Evidence & Channel3 Endpoints
- `GET /api/v1/ingredients/{ingredient_id}/evidence` — Cached read-only retrieval with pagination, source/category/review_status/study_type filters, 4-way separated groups, and epistemic guardrails.
- `POST /api/v1/ingredients/{ingredient_id}/evidence/refresh` — Restricted, rate-limited research retrieval and refresh from EC CosIng and NCBI PubMed with TTL caching and idempotent deduplication.
- `POST /api/v1/ingredients/{ingredient_id}/evidence` — Authenticated authoring of human-reviewed interpretations or segregated marketing claims.
- `PATCH /api/v1/ingredients/{ingredient_id}/evidence/{evidence_id}/review` — Authenticated review status transition (`verified`, `disputed`, `conflicting_flagged`, `incorrect_match_flagged`, `rejected`) with audit trail.
- `GET /api/v1/products/channel3/search` — Authenticated live product and offer search against the Channel3 v1 universal catalog.
- `POST /api/v1/products/{product_id}/offers/sync-channel3` — Authenticated sync of live Channel3 merchant offers for a catalog product.

### Phase 7: Gemini-Powered Grounded Explanations
- **Replaceable Language-Model Interface (`LLMExplanationProvider`)**:
  - Backed by the official Google GenAI SDK (`google-genai` >= 2.30.1) using the Interactions API (`client.aio.interactions.create`) with `store=False` and structured JSON output (`response_format`).
  - Configured via `GEMINI_API_KEY` and `GEMINI_MODEL` (default `gemini-3.5-flash-lite`; also supports `gemini-3.8-flash`, `gemini-4-argon`, `gemini-3.1-flash-lite`, `gemma-4-31b-it`). Explicitly rejects deprecated legacy models (`gemini-1.5-*`, `gemini-2.0-*`, `gemini-2.5-*`).
- **7-Step Grounding & Verification Pipeline (`ExplanationService`)**:
  1. Validates schema-versioned request (`schema_version="1.0"`) and scans for red-flag medical symptoms requiring professional dermatologist escalation.
  2. Retrieves authoritative products, ingredients, OCR scan candidates, and auditable evidence from PostgreSQL and Elasticsearch.
  3. Builds a compact, bounded context (`GEMINI_MAX_CONTEXT_CHARS`) with deterministic source IDs (`prod:...`, `ing:...`, `ev:...`, `res:...`, `offer:...`, `ocr:...`) and isolates untrusted product descriptions/OCR text inside sanitized `<untrusted_data>` tags.
  4. Requests a structured JSON explanation (`GeminiStructuredExplanationPayload`) from Gemini.
  5. Validates the structured JSON payload.
  6. Verifies that every cited source ID belongs to the retrieved context and checks that the output does not invent ingredient concentrations (`%`), invent prices, or assert medical diagnoses.
  7. Rejects unsupported citations or ungrounded claims and returns a deterministic safe fallback synthesized strictly from retrieved records.

#### AI Explanation Endpoint
- `POST /api/v1/ai/explanations` — Authenticated, per-user rate-limited endpoint returning grounded findings, resolved `source_references`, `uncertainty_and_limitations`, non-diagnostic `safety_notice`, and `generation_metadata`.

### Phase 8: Skin Analysis & Longitudinal Skin Story
- **Replaceable Skin-Analysis Provider Interface (`BaseSkinAnalysisProvider`)**:
  - **YouCam S2S v2.0 Adapter (`YouCamSkinAnalysisAdapter`)**: Verified integration with the Perfect Corp / YouCam S2S v2.0 API (`POST /s2s/v2.0/file/skin-analysis` -> pre-signed S3 PUT upload -> `POST /s2s/v2.0/task/skin-analysis` -> `GET /s2s/v2.0/task/skin-analysis/{task_id}`).
  - **Deterministic Mock Adapter (`MockSkinAnalysisAdapter`)**: Offline-safe, deterministic adapter for local development and automated tests. Never fabricates a successful scan when an external provider is unavailable or times out.
- **Privacy, Consent, Storage & Retention**:
  - Requires explicit, unrevoked user consent (`skin_data_processing` or `facial_scan_processing` in `user_consents`) before accepting or processing any facial photo.
  - Stores facial photos strictly in private object storage (`scan_media` + `media_assets`), never in PostgreSQL, with configurable retention expiration (`SKIN_ANALYSIS_RETENTION_DAYS`) and user-initiated deletion (`DELETE /api/v1/skin/scans/{scan_id}`).
  - Normalized observations (`skin_observations`) are persisted with metric code, raw value, display value, unit, directionality, provider/model version, and interpretation version (`tonetrace-obs-v1.0`), without retaining restricted raw provider payloads (`raw_payload_retained=False`).
- **Longitudinal Skin Story & Journal (`SkinStoryResponse`)**:
  - Compares historical observations only when `metric_code`, `unit`, `provider_name`, `provider_model_version`, and `interpretation_version` match the baseline, explicitly disclosing any version or provider incompatibility.
  - Uses strictly non-clinical framing (`visual_metric_increase`, `visual_metric_decrease`, `visual_metric_stable`), never infers the biological cause of pigmentation or diagnoses a skin condition, and explains how lighting, camera, angle, and cosmetics affect visual measurements.

#### Skin Analysis & Skin Story Endpoints
- `POST /api/v1/skin/scans` — Submit a facial photo with capture conditions and optional `idempotency_key`.
- `GET /api/v1/skin/scans` — List authenticated user's skin scans.
- `GET /api/v1/skin/scans/{scan_id}` — Retrieve a single scan and its normalized observations (supports `?poll_if_processing=true`).
- `POST /api/v1/skin/scans/{scan_id}/poll` — Poll an asynchronous provider task in `processing` state.
- `DELETE /api/v1/skin/scans/{scan_id}` — Purge private stored scan photos and delete scan observations.
- `GET /api/v1/skin/story` — Retrieve longitudinal, compatibility-checked metric timelines and recent journal entries.
- `POST /api/v1/skin/journal` — Record a user-authored longitudinal skin observation and routine entry.
- `GET /api/v1/skin/journal` — List user-authored skin story journal entries.

### Phase 9: My Shelf & Product Discovery
- **Personal Product Shelf (`user_products` & `product_reactions`)**:
  - Supports both public catalogue-linked products (`product_id`) and custom user-defined products (`is_custom=True`) not present in the public catalogue.
  - Tracks status (`in_use`, `wishlist`, `finished`, `paused`, `discontinued`, `avoided`), `opened_at`, `expires_at`, strictly private notes (`is_public=False`), sensitivity alerts against `user_sensitivities`, and personal reaction/tolerance history (`product_reactions`).
  - Gracefully handles unavailable or removed catalogue records (`catalogue_status="catalogue_unavailable"`).
- **Product Discovery & Explainable Rule Engine (`tonetrace-discovery-rules-v1.0`)**:
  - Uses Elasticsearch for free-text search when enabled, honours the documented fallback policy (`ELASTICSEARCH_FALLBACK_TO_DB`), and hydrates canonical product, ingredient, evidence, and commercial offer records from PostgreSQL.
  - Evaluates 5 versioned, traceable rules (`R1_INGREDIENT_DATA_COMPLETENESS`, `R2_SENSITIVITY_AND_REACTION_EXCLUSION`, `R3_GOAL_AND_EVIDENCE_ALIGNMENT`, `R4_SKIN_TYPE_CATEGORY_FIT`, `R5_COMMERCIAL_OFFER_SEGREGATION`).
  - Never treats missing ingredient data as proof of safety, never claims exact concentrations without evidence, never guarantees pigmentation results, and strictly separates commercial offers from scientific suitability.

#### My Shelf & Discovery Endpoints
- `GET /api/v1/me/shelf` — List authenticated user's shelf items with pagination, filters, and sorting.
- `POST /api/v1/me/shelf` — Add a catalogue-linked or custom product to My Shelf.
- `GET /api/v1/me/shelf/{item_id}` — Retrieve a single user-owned shelf item.
- `PATCH /api/v1/me/shelf/{item_id}` — Update status, dates, private notes, or log a `ProductReaction`.
- `DELETE /api/v1/me/shelf/{item_id}` — Remove an item from My Shelf.
- `GET /api/v1/discovery/products` — Search and evaluate catalogue products with explainable suitability assessments.
- `GET /api/v1/discovery/products/{product_id}` — Full canonical product detail, rule evaluation trace, and optional grounded Gemini explanation (`?include_ai_explanation=true`).

### Phase 10: Routines, Reminders & Product Reactions
- **Routine Planning & Immutable Completion History (`routines`, `routine_steps`, `routine_completions`)**:
  - Ordered routine steps (`step_order`) supporting user shelf products (`user_product_id`), public catalogue products (`product_id`), or custom application instructions (`custom_instruction`), with strict ownership validation.
  - Editing a routine increments `version` while preserving historical `RoutineCompletion` records (`routine_version_snapshot`, `routine_name_snapshot`, `completed_steps_snapshot`).
  - Completion timestamps are converted using the user's configured IANA timezone (`local_date`, `local_time`, `user_timezone`).
- **User-Controlled Reminders & Notification Provider (`reminder_preferences`, `reminder_deliveries`)**:
  - Replaceable `BaseNotificationProvider` interface (`app/providers/notification.py`) with `LocalRecordingNotificationAdapter` (`is_simulated=True`, `actual_external_delivery=False`, `status="recorded_local_not_sent"`), clearly distinguished from external push/email delivery.
  - Enforces idempotency keys (`uq_reminder_deliveries_user_idempotency`), opt-outs (`reminders_enabled`), local quiet hours (`quiet_hours_start`..`quiet_hours_end`), and delivery failure capture.
- **Safety-Aware Product Reactions (`product_reactions`)**:
  - User-reported observations only (`is_causal_proof=False`, `is_medical_diagnosis=False`).
  - Automatically surfaces urgent-care guidance (`requires_urgent_care_guidance=True`) and suspends ordinary cosmetic recommendations (`ordinary_recommendations_suspended=True`) when a severe or rapidly worsening reaction is reported.

#### Routines, Reminders & Reactions Endpoints
- `GET /api/v1/me/routines` — List user routines with ordered steps and completion counts.
- `POST /api/v1/me/routines` — Create a new skincare routine with validated ordered steps.
- `GET /api/v1/me/routines/{routine_id}` — Retrieve a user-owned routine.
- `PATCH /api/v1/me/routines/{routine_id}` — Update routine metadata or steps (increments `version` without erasing history).
- `DELETE /api/v1/me/routines/{routine_id}` — Delete a routine while preserving completion snapshots.
- `POST /api/v1/me/routines/{routine_id}/completions` — Log a timezone-aware routine completion session.
- `GET /api/v1/me/routines/{routine_id}/completions` — List historical completions for a routine.
- `GET /api/v1/me/reminders` — Retrieve user reminder preferences, quiet hours, timezone, and notification adapter info.
- `PUT /api/v1/me/reminders` — Update reminder schedule, opt-out toggles, quiet hours, and timezone override.
- `POST /api/v1/me/reminders/dispatch` — Evaluate opt-outs, quiet hours, timezone, and idempotency keys to dispatch a reminder.
- `POST /api/v1/me/product-reactions` — Record a user-reported product reaction with automatic urgent-care guidance evaluation.
- `GET /api/v1/me/product-reactions` — List user-reported product reactions with non-diagnostic disclaimers.

---

## Testing & Code Quality

Run tests with `pytest`:
```bash
uv run pytest
```

Run linter and formatter checks with `ruff`:
```bash
uv run ruff check .
uv run ruff format --check .
```
