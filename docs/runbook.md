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

## 5. Automated Testing & Verification

Run the full automated test suite (69 tests covering Auth, Profiles, Outbox, Search, and DB):
```bash
uv run pytest
```

Run code formatting and style checks:
```bash
uv run ruff check .
uv run ruff format --check .
```
