/**
 * ToneTrace API Client
 *
 * Implements strict envelope unwrapping, correlation ID headers,
 * authentication token injection, typed error normalization, and
 * safe 401 token refresh queue with loop prevention.
 */

import { env } from "@/config/env";
import { tokenStore } from "./token-store";
import { ApiError, ErrorResponse, ResponseEnvelope } from "./types";

export interface RequestOptions extends Omit<RequestInit, "body"> {
  params?: Record<string, string | number | boolean | undefined | null>;
  body?: unknown;
  token?: string | null;
  skipEnvelopeUnwrap?: boolean;
  _retry?: boolean;
}

class ApiClient {
  private baseUrl: string;
  private tokenGetter: (() => string | null) | null = null;
  private refreshHandler: (() => Promise<string | null>) | null = null;
  private isRefreshing = false;
  private refreshSubscribers: Array<(token: string | null) => void> = [];

  constructor(baseUrl: string = env.apiBaseUrl) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.tokenGetter = () => tokenStore.getAccessToken();
  }

  public setTokenGetter(getter: () => string | null): void {
    this.tokenGetter = getter;
  }

  public setRefreshHandler(handler: () => Promise<string | null>): void {
    this.refreshHandler = handler;
  }

  private onRefreshed(token: string | null): void {
    this.refreshSubscribers.forEach((cb) => cb(token));
    this.refreshSubscribers = [];
  }

  private addRefreshSubscriber(cb: (token: string | null) => void): void {
    this.refreshSubscribers.push(cb);
  }

  private generateRequestId(): string {
    if (typeof crypto !== "undefined" && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return `req_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
  }

  private buildUrl(path: string, params?: RequestOptions["params"]): string {
    let cleanPath = path.startsWith("/") ? path : `/${path}`;
    // Normalize path to ensure /api/v1 prefix if missing and not a root/health probe
    if (
      !cleanPath.startsWith("/api/") &&
      !cleanPath.startsWith("/health/") &&
      cleanPath !== "/health" &&
      cleanPath !== "/"
    ) {
      cleanPath = `/api/v1${cleanPath}`;
    }
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
      _retry = false,
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
      } else if (typeof body === "string") {
        headers.set("Content-Type", "application/json");
        serializedBody = body;
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

      // Check if this is an expired session that can be recovered via refresh rotation
      const isAuthRoute = path.includes("/auth/");
      if (response.status === 401 && !_retry && !isAuthRoute && this.refreshHandler) {
        if (this.isRefreshing) {
          // Concurrency queue: wait for active refresh operation
          return new Promise<T>((resolve, reject) => {
            this.addRefreshSubscriber(async (newToken) => {
              if (!newToken) {
                reject(
                  new ApiError(
                    errorMessage,
                    response.status,
                    errorCode,
                    errorRequestId,
                    errorDetails
                  )
                );
                return;
              }
              try {
                const res = await this.request<T>(path, {
                  ...options,
                  _retry: true,
                  token: newToken,
                });
                resolve(res);
              } catch (retryErr) {
                reject(retryErr);
              }
            });
          });
        }

        // Initiate refresh rotation
        this.isRefreshing = true;
        try {
          const newToken = await this.refreshHandler();
          this.onRefreshed(newToken);
          if (newToken) {
            return await this.request<T>(path, {
              ...options,
              _retry: true,
              token: newToken,
            });
          }
        } catch (refreshErr) {
          this.onRefreshed(null);
          throw new ApiError(
            errorMessage,
            response.status,
            errorCode,
            errorRequestId,
            errorDetails
          );
        } finally {
          this.isRefreshing = false;
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
