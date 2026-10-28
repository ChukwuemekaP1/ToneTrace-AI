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
