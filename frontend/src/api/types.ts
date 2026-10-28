/**
 * Core API exchange contracts verified against ToneTrace FastAPI backend.
 */

export interface ResponseMeta {
  request_id?: string | null;
  timestamp?: string | null;
}

export interface ResponseEnvelope<T> {
  status: "success" | "error";
  data: T;
  meta?: ResponseMeta | null;
}

export interface ValidationErrorItem {
  field: string;
  message: string;
  type?: string;
}

export interface ErrorDetail {
  code: string;
  message: string;
  request_id?: string | null;
  details?: ValidationErrorItem[] | Record<string, unknown> | null;
}

export interface ErrorResponse {
  error: ErrorDetail;
}

export interface PagePaginationMeta {
  page: number;
  page_size: number;
  total: number;
  total_pages?: number;
}

export interface OffsetPaginationMeta {
  limit: number;
  offset: number;
  total: number;
}

export interface HealthCheckData {
  status: "healthy" | "degraded" | "unhealthy";
  version?: string;
  timestamp?: string;
  checks?: Record<string, boolean | string>;
}

export interface UserResponse {
  id: string;
  email: string;
  account_status: string;
  is_email_verified: boolean;
  created_at: string;
  updated_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface AuthSuccessResponse {
  user: UserResponse;
  tokens: TokenResponse;
}

export interface RefreshTokenRequest {
  refresh_token: string;
  device_label?: string | null;
}

export interface UserLoginRequest {
  email: string;
  password: string;
  device_label?: string | null;
}

export interface UserRegisterRequest {
  email: string;
  password: string;
  display_name: string;
}

export interface UserProfileResponse {
  id: string;
  user_id: string;
  display_name: string;
  timezone: string;
  created_at: string;
  updated_at: string;
}

export interface SkinProfileResponse {
  id: string;
  user_id: string;
  skin_type: string | null;
  skin_concerns: string[];
  skin_goals: string[];
  created_at: string;
  updated_at: string;
}

export interface MeSummaryResponse {
  user: UserResponse;
  profile?: UserProfileResponse | null;
  skin_profile?: SkinProfileResponse | null;
  sensitivities: Array<{
    id: string;
    ingredient_name: string;
    severity: string;
    notes?: string | null;
  }>;
  preferences?: Record<string, unknown> | null;
}

export interface SkinProfileUpdateRequest {
  skin_type?: string | null;
  skin_concerns?: string[];
  skin_goals?: string[];
}

export interface UserProfileUpdateRequest {
  display_name?: string | null;
  timezone?: string | null;
}

export interface UserSensitivityItem {
  id: string;
  user_id: string;
  ingredient_name: string;
  severity: string;
  notes?: string | null;
  created_at: string;
}

export interface UserSensitivityCreateRequest {
  ingredient_name: string;
  severity?: string;
  notes?: string | null;
}

export interface UserConsentResponse {
  id: string;
  user_id: string;
  purpose: string;
  policy_version: string;
  is_granted: boolean;
  granted_at?: string | null;
  revoked_at?: string | null;
  audit_metadata?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface UserConsentUpdateRequest {
  is_granted: boolean;
  policy_version?: string;
}

// =============================================================================
// Routines & Reminders
// =============================================================================

export interface RoutineStepResponse {
  id: string;
  routine_id: string;
  step_order: number;
  time_of_day: string;
  user_product_id?: string | null;
  product_id?: string | null;
  step_label: string;
  custom_instruction?: string | null;
  frequency: string;
  wait_time_seconds?: number | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface RoutineResponse {
  id: string;
  user_id: string;
  name: string;
  description?: string | null;
  time_of_day: "morning" | "evening" | "midday" | "weekly" | "custom" | string;
  frequency: string;
  days_of_week: number[];
  preferred_local_time?: string | null;
  user_timezone: string;
  is_active: boolean;
  version: number;
  steps: RoutineStepResponse[];
  total_completions: number;
  created_at: string;
  updated_at: string;
}

export interface RoutineListResponse {
  items: RoutineResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface RoutineCompletionResponse {
  id: string;
  routine_id: string;
  user_id: string;
  completed_at: string;
  status: string;
  timezone: string;
  step_snapshots?: unknown[];
}

export interface ReminderPreferenceResponse {
  id: string;
  user_id: string;
  reminders_enabled: boolean;
  preferred_channels: string[];
  morning_reminder_enabled: boolean;
  morning_reminder_time: string;
  evening_reminder_enabled: boolean;
  evening_reminder_time: string;
  quiet_hours_enabled: boolean;
  quiet_hours_start: string;
  quiet_hours_end: string;
  timezone_override?: string | null;
  effective_timezone: string;
  opted_out_at?: string | null;
  active_notification_provider: string;
  is_simulated_delivery: boolean;
  created_at: string;
  updated_at: string;
}

// =============================================================================
// Skin Scans & Longitudinal Skin Story
// =============================================================================

export interface SkinObservationResponse {
  id: string;
  skin_scan_id: string;
  metric_code: string;
  metric_label: string;
  raw_value: number;
  display_value: number;
  unit: string;
  directionality: string;
  provider_name: string;
  confidence?: number | null;
  caveat_note: string;
  observed_at: string;
}

export interface SkinScanResponse {
  id: string;
  user_id: string;
  status: "pending" | "processing" | "succeeded" | "failed" | string;
  created_at: string;
  analyzed_at?: string | null;
  lighting_condition: string;
  camera_angle: string;
  cosmetics_worn: boolean;
  capture_notes?: string | null;
  observations: SkinObservationResponse[];
  media_count?: number;
}

export interface SkinScanListResponse {
  items: SkinScanResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface SkinStoryPoint {
  observation_id: string;
  scan_id: string;
  observed_at: string;
  raw_value: number;
  display_value: number;
  unit: string;
  directionality: string;
  is_comparable_to_baseline: boolean;
  incompatibility_reason?: string | null;
}

export interface SkinMetricTimeline {
  metric_code: string;
  metric_label: string;
  unit: string;
  directionality: string;
  points: SkinStoryPoint[];
  comparable_point_count: number;
  net_observed_delta?: number | null;
  observation_classification: string;
  non_clinical_interpretation: string;
}

export interface SkinStoryResponse {
  user_id: string;
  generated_at: string;
  total_succeeded_scans: number;
  metric_timelines: SkinMetricTimeline[];
  recent_journal_entries: Array<{
    id: string;
    recorded_at: string;
    perceived_skin_state: string;
    self_reported_observations: string[];
    notes?: string | null;
  }>;
  capture_variability_notice: string;
  non_diagnostic_disclaimer: string;
  pigmentation_and_causation_guardrail: string;
}

// =============================================================================
// Product Discovery & Catalogue
// =============================================================================

export interface RecommendationAssessment {
  is_suitable: boolean;
  decision: string;
  summary: string;
  matched_positive_rules?: string[];
  warnings?: string[];
}

export interface DiscoveryProductSummaryItem {
  product_id: string;
  source_id: string;
  name: string;
  brand: string;
  category: string;
  description?: string | null;
  image_url?: string | null;
  ingredient_count: number;
  ingredient_data_status: "complete" | "partial_text_only" | "missing" | string;
  on_user_shelf: boolean;
  user_shelf_status?: string | null;
  lowest_offer_minor_units?: number | null;
  lowest_offer_currency?: string | null;
  recommendation?: RecommendationAssessment;
}

export interface DiscoveryProductListResponse {
  items: DiscoveryProductSummaryItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  search_backend_used: string;
  rule_engine_version: string;
}

export class ApiError extends Error {
  public readonly code: string;
  public readonly status: number;
  public readonly requestId?: string | null;
  public readonly details?: unknown;

  constructor(
    message: string,
    status: number,
    code: string = "INTERNAL_ERROR",
    requestId?: string | null,
    details?: unknown
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }
}
