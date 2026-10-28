# ToneTrace AI — Frontend & Backend Contract Analysis

This document provides a systematic verification of the API contract between the ToneTrace FastAPI backend and the frontend client, explicitly resolving potential ambiguities and contract conflicts before frontend implementation.

---

## 1. Response Envelope & Error Envelope Structure

### 1.1 Success Envelope
Every standard business endpoint wraps its payload in `ResponseEnvelope[T]`:
```json
{
  "status": "success",
  "data": { ... },
  "meta": {
    "request_id": "c1f7b8...4a2",
    "timestamp": "2026-10-28T07:15:00.000000Z"
  }
}
```
- `status`: Always `"success"` on HTTP 200/201.
- `data`: Typed entity or paginated container.
- `meta`: Optional object containing `request_id` (string correlation ID) and `timestamp`.

### 1.2 Error Envelope
When an exception occurs (domain error, 401, 403, 404, 409, 422, 429, 500), FastAPI returns:
```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Routine with ID '...' not found",
    "request_id": "c1f7b8...4a2",
    "details": null
  }
}
```
- Note: Schema validation errors (`HTTP 422`) return `code: "VALIDATION_ERROR"` with `details: [{"field": "...", "message": "...", "type": "..."}]`.

---

## 2. Pagination Formats Across Domains (Critical Divergence)

The backend uses **three distinct pagination patterns** depending on the domain:

1. **Page/PageSize with TotalPages** (`shelf`, `discovery`):
   ```json
   {
     "items": [...],
     "total": 42,
     "page": 1,
     "page_size": 20,
     "total_pages": 3
   }
   ```
2. **Page/PageSize without TotalPages** (`routines`, `routine_completions`, `product_reactions`):
   ```json
   {
     "items": [...],
     "total": 12,
     "page": 1,
     "page_size": 10
   }
   ```
   *Frontend Client Action*: The client normalizer must compute `total_pages = Math.ceil(total / page_size)` when `total_pages` is omitted.

3. **Limit/Offset Pagination** (`skin_scans`, `skin_journal`):
   ```json
   {
     "items": [...],
     "total": 5,
     "limit": 20,
     "offset": 0
   }
   ```
   *Frontend Client Action*: The client must pass `?limit=20&offset=0` for skin scans and journal endpoints, rather than `page`/`page_size`.

4. **Nested Formula List** (`GET /api/v1/products/{product_id}/ingredients`):
   Returns a single formula object containing an ordered list:
   `data.ingredients: list[ProductIngredientResponse]` rather than a root-level paginated list.

---

## 3. Primary Key & Identifier Serialization (UUIDs)

- All primary keys (`User.id`, `Product.id`, `Ingredient.id`, `SkinScan.id`, `Routine.id`, `UserProduct.id`) are UUIDs stored as 32-character hex strings in PostgreSQL (`CHAR(32)`).
- When serialized via Pydantic schemas, they are presented as standard lowercase hyphenated UUID strings (e.g., `3fa85f64-5717-4562-b3fc-2c963f66afa6`) or 32-char hex.
- The frontend must treat all IDs strictly as opaque strings and never cast to numeric integers.

---

## 4. File Upload Field Names & Size Limits

1. **OCR Label Scan (`POST /api/v1/ocr/scans`)**:
   - `Content-Type`: `multipart/form-data`
   - Form field name: **`file`** (FastAPI `UploadFile`)
   - Optional form fields: `idempotency_key` (string)
   - Max file size: `5 * 1024 * 1024` bytes (5 MB) enforced by `UPLOAD_MAX_FILE_SIZE_BYTES`
   - Allowed MIME types: `image/jpeg`, `image/png`, `image/webp`
   - Initial status: `pending` (OCR processing is asynchronous/job-based).

2. **Facial Skin Scan (`POST /api/v1/skin/scans`)**:
   - `Content-Type`: `multipart/form-data`
   - Form field name: **`file`** (FastAPI `UploadFile`)
   - Form fields:
     - `idempotency_key` (string, optional)
     - `lighting_condition` (`"natural_daylight" | "indoor_warm" | "indoor_cool" | "ring_light" | "dim_or_uneven" | "unknown"`, default: `"unknown"`)
     - `camera_angle` (`"frontal" | "slight_angle" | "unknown"`, default: `"frontal"`)
     - `cosmetics_worn` (`boolean`, default: `false`)
     - `capture_notes` (`string`, optional)
     - `requested_metrics` (`string`, comma-separated, optional)
   - Prerequisite: Active user consent for `skin_data_processing` or `facial_scan_processing` via `PUT /api/v1/me/consents/facial_scan_processing` prior to upload.

---

## 5. Image Storage & Retrieval Behavior

### 5.1 Storage Backend Reality
- The default and active storage provider in development/MVP is **PostgreSQL BYTEA** (`STORAGE_PROVIDER="postgres"`).
- In this mode, image bytes reside directly in the `media_assets.image_bytes` column in Neon PostgreSQL.
- **Signed URLs are NOT external S3/GCS bucket links**. Instead, the backend generates an HMAC-SHA256 signed route:
  ```text
  /api/v1/ocr/assets/view?key={encoded_key}&exp={expires_at}&sig={signature}
  ```
- *Frontend Action*:
  - The frontend image helper must prefix relative paths with the configured `VITE_API_BASE_URL` (e.g. `http://localhost:8000/api/v1/ocr/assets/view?...`).
  - For authenticated in-app previews, the client can also fetch `GET /api/v1/ocr/assets/by-id/{asset_id}` with an `Authorization: Bearer <token>` header, returning a direct binary image stream (`Response(content=image_bytes, media_type=mime_type)`).

---

## 6. User Profile, Timezone & Consent Routes

### 6.1 Timezone Management
- Timezone is stored on the user profile (`UserProfile.timezone`).
- Default: `"UTC"`.
- Update route: **`PATCH /api/v1/me`**
  ```json
  {
    "timezone": "America/New_York",
    "display_name": "Skincare Enthusiast"
  }
  ```
- *Verified*: Timezone is an IANA string (e.g., `Europe/London`, `America/Los_Angeles`).

### 6.2 Consent Tracking
- `GET /api/v1/me/consents`: Returns list of consent records (`UserConsentResponse`).
- `PUT /api/v1/me/consents/{purpose}`: Grants or revokes consent (`{"granted": true}`).
  - Known purposes: `"skin_data_processing"`, `"facial_scan_processing"`, `"marketing_notifications"`.

---

## 7. Reminders: Delivery vs. Preference Storage

### 7.1 What Exists
- Preference Storage: `GET /api/v1/me/reminders` and `PUT /api/v1/me/reminders` are fully implemented.
  - Controls: `reminders_enabled`, `morning_reminder_enabled`, `morning_reminder_time`, `evening_reminder_enabled`, `evening_reminder_time`, `quiet_hours_enabled`, `quiet_hours_start`, `quiet_hours_end`, `timezone_override`.
- Simulation Dispatch: `POST /api/v1/me/reminders/dispatch` records a reminder dispatch in `reminder_delivery_records`.
  - Response explicitly includes:
    `"is_simulated": true`, `"actual_external_delivery": false`,
    `"delivery_mode_disclosure": "Local simulated dispatch. No real SMS or push notification sent."`

### 7.2 What Does NOT Exist
- There is **no live external Twilio SMS or Apple APNs / Firebase Cloud Messaging push delivery provider** connected.
- The UI must NOT promise real push notifications or SMS delivery; it should honestly frame reminders as scheduled in-app check-ins or simulated dispatch records.

---

## 8. AI Explanations: Single Request vs. Conversational Chat

### 8.1 API Contract
- Endpoint: `POST /api/v1/ai/explanations`
- Request Schema (`ExplanationRequest`):
  ```json
  {
    "schema_version": "1.0",
    "question": "Why is niacinamide good for redness?",
    "product_ids": ["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    "ingredient_ids": ["7cb11a28-9412-4217-a1cb-8758b991ef14"],
    "ocr_job_id": null,
    "search_query": null,
    "include_user_skin_profile": true
  }
  ```
- Response Schema (`ExplanationResponse`):
  - `explanation_id`: UUID
  - `grounding_status`: `"grounded" | "fallback_applied"`
  - `summary`: Short Markdown summary
  - `findings`: Array of grounded findings with `claim`, `finding_type`, `confidence`, and `source_ids`
  - `source_references`: Array of cited sources (`prod:<uuid>`, `ing:<uuid>`, `ev:<uuid>`, `res:<uuid>`)
  - `uncertainty_and_limitations`: Scientific guardrails
  - `safety_notice`: Disclaimer regarding medical advice

### 8.2 What Does NOT Exist
- **No conversational multi-turn chat session history API exists**.
- There is no `/api/v1/ai/conversations` or `/api/v1/ai/messages` endpoint.
- Each explanation call is an idempotent, single-turn grounded inquiry scoped to selected products/ingredients.

---

## 9. Authentication: First-Party vs. Social Login

### 9.1 Verified Implementation
- First-Party email/password only:
  - `POST /api/v1/auth/register` (`email`, `password`)
  - `POST /api/v1/auth/login` (`email`, `password`) -> `{ access_token, refresh_token, token_type: "bearer", expires_in: 900 }`
  - `POST /api/v1/auth/refresh` (`refresh_token`) -> rotated token pair
  - `POST /api/v1/auth/logout` (`refresh_token`)
  - `POST /api/v1/auth/logout-all` (revokes all active sessions for caller)

### 9.2 What Does NOT Exist
- No Google OAuth (`/auth/google/callback`)
- No Apple Sign-In
- No social buttons should trigger unbacked endpoints.
