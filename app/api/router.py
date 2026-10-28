"""Central API router aggregating all versioned endpoints."""

from fastapi import APIRouter

from app.api.routes import (
    ai,
    auth,
    catalog,
    evidence,
    health,
    me,
    ocr,
    routines,
    search,
    shelf,
    skin,
)

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

# Phase 6 Ingredient Evidence and Research Retrieval
api_router.include_router(evidence.router)

# Phase 7 Gemini-Powered Grounded Explanations
api_router.include_router(ai.router)

# Phase 8 Skin Analysis and Longitudinal Skin Story
api_router.include_router(skin.router)

# Phase 9 My Shelf and Product Discovery
api_router.include_router(shelf.router)

# Phase 10 Routines, Reminders, and Product Reactions
api_router.include_router(routines.router)
