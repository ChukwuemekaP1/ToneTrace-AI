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
- **Quality & Testing**: Pytest (86 automated tests), pytest-asyncio, HTTPX, and Ruff (linter/formatter)
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

### 4. Running the Application

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
- Interactive Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- Interactive ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### 4. Product & Ingredient Catalogue (Phase 4)

- **Provenance Tracking**: Every formulation list preserves its data source (`data_sources`), retrieval timestamp, and raw packaging declaration.
- **Formula Versioning**: When a cosmetic product is reformulated, historical formulas are preserved in `product_ingredient_lists` rather than overwritten.
- **Commercial Separation**: Retail offers (`product_offers`) and prices are strictly separated from chemical formula data, with currency minor units (e.g. cents) and retrieval timestamps.
- **Open Beauty Facts Adapter**: Official v2 adapter with rate limit backoff and ODbL v1.0 attribution.
- **Channel3 Adapter**: Isolated provider contract adapter with honest unconfigured reporting when credentials are not supplied.

#### Endpoints
- `GET /api/v1/products/{product_id}` — Product detail with brand, variants, current formula, and offers.
- `GET /api/v1/products/barcode/{barcode}` — Barcode lookup across SKUs.
- `GET /api/v1/products/{product_id}/ingredients` — Ordered ingredient list for current or specific formula version.
- `GET /api/v1/ingredients/{ingredient_id}` — Standardized INCI cosmetic ingredient definition.
- `POST /api/v1/products/ingest/barcode/{barcode}` — Authenticated, rate-limited barcode ingestion.
- `POST /api/v1/products/{product_id}/reformulate` — Record a new formulation version while preserving history.
- `POST /api/v1/products/{product_id}/offers` — Record commercial merchant offer.

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
