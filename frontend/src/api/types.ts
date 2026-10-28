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
