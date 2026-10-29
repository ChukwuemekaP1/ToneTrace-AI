# ToneTrace AI — Production Deployment Guide

This guide details how to deploy ToneTrace AI to production cloud vendors (Vercel, Render, Railway, Neon) or self-hosted container infrastructure.

---

## 1. Cloud Architecture Overview

| Layer | Recommended Vendor | Configuration File |
| :--- | :--- | :--- |
| **Frontend SPA** | [Vercel](https://vercel.com) or Render Static | `frontend/vercel.json`, `frontend/Dockerfile` |
| **Backend API** | [Render](https://render.com) or [Railway](https://railway.app) | `Dockerfile`, `render.yaml` |
| **PostgreSQL Database** | [Neon](https://neon.tech) Serverless Postgres | SSL-required pooled connection string |
| **Search Engine** | [Elastic Cloud](https://cloud.elastic.co) (ES 8.x) | Managed cluster endpoint with API key |
| **Media / Storage** | AWS S3 or Cloudflare R2 | Private bucket with presigned time-limited URLs |

---

## 2. Option A: Vendor Deployment (Vercel + Render + Neon)

### Step 1: Provision Neon PostgreSQL
1. Create a project on [Neon](https://neon.tech).
2. Copy your pooled connection URI:
   ```text
   postgresql+psycopg://username:password@ep-xyz-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```

### Step 2: Deploy Backend to Render
1. Connect your Git repository to **Render**.
2. Select **Web Service** using the root `Dockerfile` (or use Blueprint with `render.yaml`).
3. Set environment variables:
   - `ENVIRONMENT`: `production`
   - `DEBUG`: `false`
   - `DATABASE_URL`: *(Your Neon connection string from Step 1)*
   - `JWT_SECRET_KEY`: *(Generate a 32+ character random secret)*
   - `ALLOWED_CORS_ORIGINS`: `["https://your-frontend.vercel.app"]`
   - `OCR_SPACE_API_KEY`: *(Your OCR.space key)*
   - `GEMINI_API_KEY`: *(Your Google AI Studio Gemini API key)*
   - `YOUCAM_API_KEY`: *(Your YouCam S2S API key)*
4. Set Health Check path to `/health/live`.

### Step 3: Deploy Frontend to Vercel
1. Import the Git repository in **Vercel**.
2. Set Root Directory to `frontend`.
3. Framework Preset: **Vite**.
4. Set Build Command: `pnpm build`, Output Directory: `dist`.
5. Set Environment Variable:
   - `VITE_API_BASE_URL`: `https://your-backend-api.onrender.com` (or leave empty to let `frontend/vercel.json` proxy rewrites route `/api` requests).

---

## 3. Option B: Self-Hosted Docker Compose

To deploy ToneTrace AI on your own Linux / VPS server (Ubuntu/Debian with Docker & Docker Compose):

```bash
# 1. Clone repository
git clone https://github.com/your-org/tonetrace-ai.git
cd tonetrace-ai

# 2. Configure environment variables
cp .env.example .env.production
# Edit JWT_SECRET_KEY, GEMINI_API_KEY, OCR_SPACE_API_KEY, etc.

# 3. Launch with production compose
docker compose -f docker-compose.prod.yml up -d --build

# 4. Run database migrations inside API container
docker compose -f docker-compose.prod.yml exec api alembic upgrade head
```

The application will be live at:
- Web Frontend: `http://your-server-ip` (Port 80)
- Backend API Docs: `http://your-server-ip:8000/docs` (if DEBUG=true)
- Health Check: `http://your-server-ip/health/live`

---

## 4. Production Environment Variables Checklist

| Variable Name | Required | Description | Example / Format |
| :--- | :--- | :--- | :--- |
| `ENVIRONMENT` | Yes | App runtime mode | `production` |
| `DATABASE_URL` | Yes | Async PostgreSQL connection string | `postgresql+psycopg://user:pass@host:5432/tonetrace` |
| `JWT_SECRET_KEY` | Yes | 32+ byte cryptographic key for tokens | Random 64-hex string |
| `ALLOWED_CORS_ORIGINS` | Yes | JSON array of permitted origins | `["https://app.tonetrace.ai"]` |
| `OCR_SPACE_API_KEY` | Recommended | OCR.space label extraction | `K8XXXXXXXX88957` |
| `GEMINI_API_KEY` | Recommended | Grounded AI ingredient explanations | `AIzaSy...` |
| `YOUCAM_API_KEY` | Optional | Facial skin analysis provider | Vendor license key |
| `ELASTICSEARCH_URL` | Optional | Semantic product & ingredient search | `https://username:password@es-cluster.es.io:9243` |
| `STORAGE_PROVIDER` | Optional | Private image storage backend | `postgres` or `s3` |
