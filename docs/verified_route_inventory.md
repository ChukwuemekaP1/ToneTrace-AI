# ToneTrace AI — Verified Route Inventory & API Contract Audit

Generated from live `/openapi.json` and verified AST route inspection.

Total Route Operations Verified: 72

## Authentication (5 endpoints)

| Method | Path | Summary | Auth | Request Schema | Response Schema | Parameters |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| **POST** | `/api/v1/auth/login` | Authenticate with email and password | Public | `UserLoginRequest` | `ResponseEnvelope_AuthSuccessResponse_` | None |
| **POST** | `/api/v1/auth/logout` | Revoke an active refresh token session | Public | `RefreshTokenRequest` | `ResponseEnvelope_dict_str__str__` | None |
| **POST** | `/api/v1/auth/logout-all` | Revoke all active sessions for the current user | Public | None | `ResponseEnvelope_dict_str__Any__` | header:authorization, header:x-user-id |
| **POST** | `/api/v1/auth/refresh` | Rotate refresh token and obtain new access token | Public | `RefreshTokenRequest` | `ResponseEnvelope_TokenResponse_` | None |
| **POST** | `/api/v1/auth/register` | Register a new user account | Public | `UserRegisterRequest` | `ResponseEnvelope_AuthSuccessResponse_` | None |


## User Profile (10 endpoints)

| Method | Path | Summary | Auth | Request Schema | Response Schema | Parameters |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| **GET** | `/api/v1/me` | Get current user aggregate profile and preferences | Public | None | `ResponseEnvelope_MeSummaryResponse_` | header:authorization, header:x-user-id |
| **PATCH** | `/api/v1/me` | Update user display name or timezone | Public | `UserProfileUpdateRequest` | `ResponseEnvelope_UserProfileResponse_` | header:authorization, header:x-user-id |
| **DELETE** | `/api/v1/me` | Delete the authenticated user account and purge all private stored media | Public | None | `ResponseEnvelope_dict_str__Any__` | header:authorization, header:x-user-id |
| **GET** | `/api/v1/me/consents` | List all privacy and data processing consents | Public | None | `ResponseEnvelope_list_UserConsentResponse__` | header:authorization, header:x-user-id |
| **PUT** | `/api/v1/me/consents/{purpose}` | Record or update consent for a specific purpose | Public | `UserConsentUpdateRequest` | `ResponseEnvelope_UserConsentResponse_` | path:purpose (req), header:authorization, header:x-user-id |
| **GET** | `/api/v1/me/sensitivities` | List reported ingredient sensitivities | Public | None | `ResponseEnvelope_list_UserSensitivityItem__` | header:authorization, header:x-user-id |
| **POST** | `/api/v1/me/sensitivities` | Add an ingredient sensitivity to avoid | Public | `UserSensitivityCreateRequest` | `ResponseEnvelope_UserSensitivityItem_` | header:authorization, header:x-user-id |
| **DELETE** | `/api/v1/me/sensitivities/{sensitivity_id}` | Remove an ingredient sensitivity | Public | None | `ResponseEnvelope_dict_str__str__` | path:sensitivity_id (req), header:authorization, header:x-user-id |
| **GET** | `/api/v1/me/skin-profile` | Get self-reported skin profile attributes | Public | None | `ResponseEnvelope_SkinProfileResponse_` | header:authorization, header:x-user-id |
| **PUT** | `/api/v1/me/skin-profile` | Update or set skin profile attributes | Public | `SkinProfileUpdateRequest` | `ResponseEnvelope_SkinProfileResponse_` | header:authorization, header:x-user-id |


## Routines, Reminders & Reactions (12 endpoints)

| Method | Path | Summary | Auth | Request Schema | Response Schema | Parameters |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| **POST** | `/api/v1/me/product-reactions` | Record a user-reported product reaction with urgent-care safety evaluation | Public | `StandaloneReactionCreateRequest` | `ResponseEnvelope_SafetyAwareReactionResponse_` | header:authorization, header:x-user-id |
| **GET** | `/api/v1/me/product-reactions` | List the user's reported product reactions | Public | None | `ResponseEnvelope_ReactionListResponse_` | query:reaction_type, query:severity, query:user_product_id, query:product_id, query:page, query:page_size, header:authorization, header:x-user-id |
| **GET** | `/api/v1/me/reminders` | Get the user's reminder preferences and timezone configuration | Public | None | `ResponseEnvelope_ReminderPreferenceResponse_` | header:authorization, header:x-user-id |
| **PUT** | `/api/v1/me/reminders` | Update the user's reminder preferences, opt-outs, quiet hours, and timezone | Public | `ReminderPreferenceUpdateRequest` | `ResponseEnvelope_ReminderPreferenceResponse_` | header:authorization, header:x-user-id |
| **POST** | `/api/v1/me/reminders/dispatch` | Evaluate and dispatch a routine reminder with idempotency and quiet-hour checks | Public | `ReminderDispatchRequest` | `ResponseEnvelope_ReminderDeliveryResponse_` | header:authorization, header:x-user-id |
| **GET** | `/api/v1/me/routines` | List the authenticated user's skincare routines | Public | None | `ResponseEnvelope_RoutineListResponse_` | query:time_of_day, query:is_active, query:page, query:page_size, header:authorization, header:x-user-id |
| **POST** | `/api/v1/me/routines` | Create a new skincare routine with ordered steps | Public | `RoutineCreateRequest` | `ResponseEnvelope_RoutineResponse_` | header:authorization, header:x-user-id |
| **GET** | `/api/v1/me/routines/{routine_id}` | Retrieve a specific routine owned by the user | Public | None | `ResponseEnvelope_RoutineResponse_` | path:routine_id (req), header:authorization, header:x-user-id |
| **PATCH** | `/api/v1/me/routines/{routine_id}` | Update a routine or its ordered steps without erasing completion history | Public | `RoutineUpdateRequest` | `ResponseEnvelope_RoutineResponse_` | path:routine_id (req), header:authorization, header:x-user-id |
| **DELETE** | `/api/v1/me/routines/{routine_id}` | Delete a routine owned by the user | Public | None | `ResponseEnvelope_dict_str__str__` | path:routine_id (req), header:authorization, header:x-user-id |
| **POST** | `/api/v1/me/routines/{routine_id}/completions` | Record a routine completion with timezone-aware step snapshots | Public | `RoutineCompletionCreateRequest` | `ResponseEnvelope_RoutineCompletionResponse_` | path:routine_id (req), header:authorization, header:x-user-id |
| **GET** | `/api/v1/me/routines/{routine_id}/completions` | List historical completions for a routine | Public | None | `ResponseEnvelope_RoutineCompletionListResponse_` | path:routine_id (req), query:page, query:page_size, header:authorization, header:x-user-id |


## My Shelf & Product Discovery (7 endpoints)

| Method | Path | Summary | Auth | Request Schema | Response Schema | Parameters |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| **GET** | `/api/v1/discovery/products` | Discover products with explainable, source-backed suitability rules | Public | None | `ResponseEnvelope_DiscoveryProductListResponse_` | query:q, query:category, query:brand, query:goal, query:exclude_user_sensitivities, query:exclude_ingredients, query:require_complete_ingredients, query:sort_by, query:page, query:page_size, header:authorization, header:x-user-id |
| **GET** | `/api/v1/discovery/products/{product_id}` | Retrieve product discovery detail, rule trace, and optional grounded AI explanation | Public | None | `ResponseEnvelope_DiscoveryProductDetailResponse_` | path:product_id (req), query:goal, query:include_ai_explanation, header:authorization, header:x-user-id |
| **GET** | `/api/v1/me/shelf` | List authenticated user's personal product shelf | Public | None | `ResponseEnvelope_ShelfListResponse_` | query:page, query:page_size, query:status, query:category, query:is_custom, query:sort_by, header:authorization, header:x-user-id |
| **POST** | `/api/v1/me/shelf` | Add a catalogue-linked or custom product to My Shelf | Public | `ShelfItemCreateRequest` | `ResponseEnvelope_ShelfItemResponse_` | header:authorization, header:x-user-id |
| **GET** | `/api/v1/me/shelf/{item_id}` | Get a single item from My Shelf | Public | None | `ResponseEnvelope_ShelfItemResponse_` | path:item_id (req), header:authorization, header:x-user-id |
| **PATCH** | `/api/v1/me/shelf/{item_id}` | Update a shelf item or record a product reaction | Public | `ShelfItemUpdateRequest` | `ResponseEnvelope_ShelfItemResponse_` | path:item_id (req), header:authorization, header:x-user-id |
| **DELETE** | `/api/v1/me/shelf/{item_id}` | Remove an item from My Shelf | Public | None | `ResponseEnvelope_dict_str__str__` | path:item_id (req), header:authorization, header:x-user-id |


## Product & Ingredient Catalogue (9 endpoints)

| Method | Path | Summary | Auth | Request Schema | Response Schema | Parameters |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| **GET** | `/api/v1/ingredients/{ingredient_id}` | Get standardized ingredient details | Public | None | `ResponseEnvelope_IngredientDetailResponse_` | path:ingredient_id (req) |
| **GET** | `/api/v1/products/barcode/{barcode}` | Get product detail by barcode | Public | None | `ResponseEnvelope_ProductDetailResponse_` | path:barcode (req) |
| **GET** | `/api/v1/products/channel3/search` | Search Channel3 universal product catalog and offers | Public | None | `ResponseEnvelope_Channel3SearchResponse_` | query:query (req), query:limit, query:max_price, header:authorization, header:x-user-id |
| **POST** | `/api/v1/products/ingest/barcode/{barcode}` | Ingest product by barcode from Open Beauty Facts | Public | None | `ResponseEnvelope_IngestProductResponse_` | path:barcode (req), header:authorization, header:x-user-id |
| **GET** | `/api/v1/products/{product_id}` | Get product detail by UUID | Public | None | `ResponseEnvelope_ProductDetailResponse_` | path:product_id (req) |
| **GET** | `/api/v1/products/{product_id}/ingredients` | Get ordered ingredient list for a product | Public | None | `ResponseEnvelope_list_ProductIngredientItemResponse__` | path:product_id (req), query:formula_version |
| **POST** | `/api/v1/products/{product_id}/offers` | Record commercial price offer | Public | `AddOfferRequest` | `ResponseEnvelope_ProductOfferResponse_` | path:product_id (req), header:authorization, header:x-user-id |
| **POST** | `/api/v1/products/{product_id}/offers/sync-channel3` | Sync live merchant offers from Channel3 for a product | Public | None | `ResponseEnvelope_Channel3SyncOffersResponse_` | path:product_id (req), header:authorization, header:x-user-id |
| **POST** | `/api/v1/products/{product_id}/reformulate` | Record product reformulation (preserving historical formulas) | Public | `AddReformulationRequest` | `ResponseEnvelope_ProductIngredientListResponse_` | path:product_id (req), header:authorization, header:x-user-id |


## Catalog Search (4 endpoints)

| Method | Path | Summary | Auth | Request Schema | Response Schema | Parameters |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| **GET** | `/api/v1/search/ingredients` | Search cosmetic ingredients with autocomplete, function, and safety rating filters | Public | None | `ResponseEnvelope_SearchResultsResponse_IngredientSearchHit__` | query:q, query:function, query:safety_rating, query:page, query:page_size, header:authorization, header:x-user-id |
| **GET** | `/api/v1/search/products` | Search cosmetic products with text matching and sensitivity exclusion | Public | None | `ResponseEnvelope_SearchResultsResponse_ProductSearchHit__` | query:q, query:brand, query:category, query:exclude_ingredients, query:page, query:page_size, query:sort_by, header:authorization, header:x-user-id |
| **POST** | `/api/v1/search/reindex` | Rebuild entire Elasticsearch index directly from authoritative PostgreSQL tables | Public | None | `ResponseEnvelope_ReindexResponse_` | header:authorization, header:x-user-id |
| **POST** | `/api/v1/search/sync-outbox` | Process pending transactional outbox events to Elasticsearch | Public | None | `ResponseEnvelope_dict_str__int__` | query:batch_size, header:authorization, header:x-user-id |


## OCR & Label Scanning (6 endpoints)

| Method | Path | Summary | Auth | Request Schema | Response Schema | Parameters |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| **GET** | `/api/v1/ocr/assets/by-id/{asset_id}` | Retrieve owned private image asset bytes (authenticated owner only) | Public | None | `any` | path:asset_id (req), header:authorization, header:x-user-id |
| **DELETE** | `/api/v1/ocr/assets/by-id/{asset_id}` | Delete owned private image asset bytes from PostgreSQL | Public | None | `ResponseEnvelope_MediaAssetDeleteResponse_` | path:asset_id (req), header:authorization, header:x-user-id |
| **GET** | `/api/v1/ocr/assets/view` | Stream private stored image asset via time-limited signed URL | Public | None | `any` | query:key (req), query:exp (req), query:sig (req) |
| **POST** | `/api/v1/ocr/scans` | Upload product label image and extract formulation ingredients | Public | `Body_create_scan_api_v1_ocr_scans_post` | `ResponseEnvelope_OCRScanResponse_` | header:authorization, header:x-user-id |
| **GET** | `/api/v1/ocr/scans/{scan_id}` | Retrieve OCR scan status, raw text, and candidate ingredients | Public | None | `ResponseEnvelope_OCRScanResponse_` | path:scan_id (req), header:authorization, header:x-user-id |
| **POST** | `/api/v1/ocr/scans/{scan_id}/confirm` | Review, edit, and confirm candidate ingredients from OCR scan | Public | `ConfirmScanRequest` | `ResponseEnvelope_ConfirmScanResponse_` | path:scan_id (req), header:authorization, header:x-user-id |


## Ingredient Evidence & Research Retrieval (4 endpoints)

| Method | Path | Summary | Auth | Request Schema | Response Schema | Parameters |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| **GET** | `/api/v1/ingredients/{ingredient_id}/evidence` | Get auditable ingredient evidence and research citations | Public | None | `ResponseEnvelope_IngredientEvidenceListResponse_` | path:ingredient_id (req), query:page, query:page_size, query:source, query:category, query:review_status, query:study_type |
| **POST** | `/api/v1/ingredients/{ingredient_id}/evidence` | Create human-reviewed interpretation or segregated marketing claim | Public | `CreateEvidenceRequest` | `ResponseEnvelope_IngredientEvidenceItemResponse_` | path:ingredient_id (req), header:authorization, header:x-user-id |
| **POST** | `/api/v1/ingredients/{ingredient_id}/evidence/refresh` | Restricted research retrieval and refresh from CosIng and PubMed | Public | `EvidenceRefreshRequest` | `ResponseEnvelope_EvidenceRefreshResponse_` | path:ingredient_id (req), header:authorization, header:x-user-id |
| **PATCH** | `/api/v1/ingredients/{ingredient_id}/evidence/{evidence_id}/review` | Update evidence review status and record audit trail | Public | `UpdateEvidenceReviewRequest` | `ResponseEnvelope_IngredientEvidenceItemResponse_` | path:ingredient_id (req), path:evidence_id (req), header:authorization, header:x-user-id |


## Skin Analysis & Skin Story (8 endpoints)

| Method | Path | Summary | Auth | Request Schema | Response Schema | Parameters |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| **POST** | `/api/v1/skin/journal` | Create a user-authored Skin Story journal entry | Public | `CreateSkinJournalEntryRequest` | `ResponseEnvelope_SkinJournalEntryResponse_` | header:authorization, header:x-user-id |
| **GET** | `/api/v1/skin/journal` | List authenticated user's Skin Story journal entries | Public | None | `ResponseEnvelope_SkinJournalListResponse_` | query:limit, query:offset, header:authorization, header:x-user-id |
| **POST** | `/api/v1/skin/scans` | Submit a facial photo for provider-backed skin analysis | Public | `Body_create_skin_scan_api_v1_skin_scans_post` | `ResponseEnvelope_SkinScanResponse_` | header:authorization, header:x-user-id |
| **GET** | `/api/v1/skin/scans` | List authenticated user's skin scans | Public | None | `ResponseEnvelope_SkinScanListResponse_` | query:limit, query:offset, query:status, header:authorization, header:x-user-id |
| **GET** | `/api/v1/skin/scans/{scan_id}` | Retrieve a specific skin scan and its normalized observations | Public | None | `ResponseEnvelope_SkinScanResponse_` | path:scan_id (req), query:poll_if_processing, header:authorization, header:x-user-id |
| **DELETE** | `/api/v1/skin/scans/{scan_id}` | Delete a skin scan and purge its private stored media | Public | None | `ResponseEnvelope_SkinScanDeleteResponse_` | path:scan_id (req), header:authorization, header:x-user-id |
| **POST** | `/api/v1/skin/scans/{scan_id}/poll` | Poll external provider for an asynchronous skin scan task | Public | None | `ResponseEnvelope_SkinScanResponse_` | path:scan_id (req), header:authorization, header:x-user-id |
| **GET** | `/api/v1/skin/story` | Retrieve longitudinal Skin Story of compatible visual observations and journal notes | Public | None | `ResponseEnvelope_SkinStoryResponse_` | query:metric, query:journal_limit, header:authorization, header:x-user-id |


## AI Grounded Explanations (1 endpoints)

| Method | Path | Summary | Auth | Request Schema | Response Schema | Parameters |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| **POST** | `/api/v1/ai/explanations` | Generate a grounded skincare explanation backed by retrieved evidence | Public | `ExplanationRequest` | `ResponseEnvelope_ExplanationResponse_` | header:authorization, header:x-user-id |


## Health & Diagnostics (6 endpoints)

| Method | Path | Summary | Auth | Request Schema | Response Schema | Parameters |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| **GET** | `/api/v1/health/integrations` | Safe Integration Status | Public | None | `IntegrationStatusResponse` | None |
| **GET** | `/api/v1/health/live` | Process Liveness Probe | Public | None | `LivenessResponse` | None |
| **GET** | `/api/v1/health/ready` | Service Readiness Probe | Public | None | `ReadinessResponse` | None |
| **GET** | `/health/integrations` | Safe Integration Status | Public | None | `IntegrationStatusResponse` | None |
| **GET** | `/health/live` | Process Liveness Probe | Public | None | `LivenessResponse` | None |
| **GET** | `/health/ready` | Service Readiness Probe | Public | None | `ReadinessResponse` | None |

