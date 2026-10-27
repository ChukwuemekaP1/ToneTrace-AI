"""Central API router aggregating all versioned endpoints."""

from fastapi import APIRouter

from app.api.routes import auth, catalog, health, me, ocr, search

api_router = APIRouter()

# Health and observability endpoints
api_router.include_router(health.router)

# Phase 2 First-Party Authentication and Session Management
api_router.include_router(auth.router)

# Phase 2 User Profiles, Skin Profiles, Sensitivities, and Consents
api_router.include_router(me.router)

# Phase 3 Elasticsearch Search Foundation
api_router.include_router(search.router)

# Phase 4 Product and Ingredient Catalogue
api_router.include_router(catalog.router)

# Phase 5 OCR and Product-Label Scanning
api_router.include_router(ocr.router)
