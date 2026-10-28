/**
 * ToneTrace API Client
 *
 * Implements strict envelope unwrapping, correlation ID headers,
 * authentication token injection, and typed error normalization.
 */

import { env } from "@/config/env";
import { ApiError, ErrorResponse, ResponseEnvelope } from "./types";

export interface RequestOptions extends Omit<RequestInit, "body"> {
  params?: Record<string, string | number | boolean | undefined | null>;
  body?: unknown;
  token?: string | null;
  skipEnvelopeUnwrap?: boolean;
}

class ApiClient {
  private baseUrl: string;
  private tokenGetter: (() => string | null) | null = null;

  constructor(baseUrl: string = env.apiBaseUrl) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
  }

  public setTokenGetter(getter: () => string | null): void {
    this.tokenGetter = getter;
  }

  private generateRequestId(): string {
    if (typeof crypto !== "undefined" && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return `req_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
  }

  private buildUrl(path: string, params?: RequestOptions["params"]): string {
    const cleanPath = path.startsWith("/") ? path : `/${path}`;
    const fullUrl = this.baseUrl ? `${this.baseUrl}${cleanPath}` : cleanPath;

    if (!params) return fullUrl;

    const searchParams = new URLSearchParams();
    for (const [key, val] of Object.entries(params)) {
      if (val !== undefined && val !== null) {
        searchParams.append(key, String(val));
      }
    }

    const queryString = searchParams.toString();
    return queryString ? `${fullUrl}?${queryString}` : fullUrl;
  }

  public async request<T = unknown>(
    path: string,
    options: RequestOptions = {}
  ): Promise<T> {
    const {
      params,
      body,
      token,
      headers: customHeaders = {},
      skipEnvelopeUnwrap = false,
      ...fetchOptions
    } = options;

    const url = this.buildUrl(path, params);
    const headers = new Headers(customHeaders);

    // 1. Correlation tracking
    if (!headers.has("X-Request-ID")) {
      headers.set("X-Request-ID", this.generateRequestId());
    }

    // 2. Authentication header
    const resolvedToken = token ?? this.tokenGetter?.() ?? null;
    if (resolvedToken && !headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${resolvedToken}`);
    }

    // 3. Body & Content-Type
    let serializedBody: BodyInit | null | undefined = undefined;
    if (body !== undefined && body !== null) {
      if (body instanceof FormData) {
        serializedBody = body;
        // Fetch sets the boundary multipart content-type automatically
      } else {
        headers.set("Content-Type", "application/json");
        serializedBody = JSON.stringify(body);
      }
    }

    // 4. Execute fetch
    let response: Response;
    try {
      response = await fetch(url, {
        ...fetchOptions,
        headers,
        body: serializedBody,
      });
    } catch (err) {
      throw new ApiError(
        err instanceof Error ? err.message : "Network error occurred",
        0,
        "NETWORK_ERROR"
      );
    }

    // 5. Handle empty responses (e.g. 204 No Content)
    if (response.status === 204) {
      return undefined as T;
    }

    // 6. Extract payload
    const contentType = response.headers.get("content-type") || "";
    const isJson = contentType.includes("application/json");

    if (!response.ok) {
      let errorCode = "HTTP_ERROR";
      let errorMessage = `Request failed with status ${response.status}`;
      let errorRequestId: string | null = response.headers.get("X-Request-ID");
      let errorDetails: unknown = null;

      if (isJson) {
        try {
          const errorPayload = (await response.json()) as ErrorResponse;
          if (errorPayload && errorPayload.error) {
            errorCode = errorPayload.error.code || errorCode;
            errorMessage = errorPayload.error.message || errorMessage;
            errorRequestId = errorPayload.error.request_id || errorRequestId;
            errorDetails = errorPayload.error.details || null;
          }
        } catch {
          // Response body was not JSON or failed parsing
        }
      }

      throw new ApiError(
        errorMessage,
        response.status,
        errorCode,
        errorRequestId,
        errorDetails
      );
    }

    if (!isJson) {
      return (await response.text()) as unknown as T;
    }

    const json = (await response.json()) as ResponseEnvelope<T> | T;

    // 7. Standard ResponseEnvelope unwrapping
    if (!skipEnvelopeUnwrap && typeof json === "object" && json !== null && "status" in json && "data" in json) {
      return (json as ResponseEnvelope<T>).data;
    }

    return json as T;
  }

  public get<T>(path: string, options?: RequestOptions): Promise<T> {
    return this.request<T>(path, { ...options, method: "GET" });
  }

  public post<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(path, { ...options, method: "POST", body });
  }

  public put<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(path, { ...options, method: "PUT", body });
  }

  public patch<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(path, { ...options, method: "PATCH", body });
  }

  public delete<T>(path: string, options?: RequestOptions): Promise<T> {
    return this.request<T>(path, { ...options, method: "DELETE" });
  }

  // Diagnostic / Health Probes (Verified contract: GET /api/v1/health/live and /health/live)
  public async checkHealth(): Promise<{ live: boolean; details?: unknown }> {
    try {
      // Prioritize /api/v1/health/live to guarantee routing through the /api proxy
      const res = await this.get<{ status: string }>("/api/v1/health/live", {
        skipEnvelopeUnwrap: true,
      });
      return { live: res?.status === "healthy" || res?.status === "ok", details: res };
    } catch {
      try {
        const fallback = await this.get<{ status: string }>("/health/live", {
          skipEnvelopeUnwrap: true,
        });
        return { live: fallback?.status === "healthy" || fallback?.status === "ok", details: fallback };
      } catch (err) {
        return { live: false, details: err };
      }
    }
  }
}

export const apiClient = new ApiClient();
