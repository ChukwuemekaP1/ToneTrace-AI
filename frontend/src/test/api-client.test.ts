import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiClient } from "@/api/client";
import { ApiError } from "@/api/types";

describe("ToneTrace ApiClient", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("unwraps standard ResponseEnvelope data successfully", async () => {
    const mockEnvelope = {
      status: "success",
      data: { id: "user_123", email: "tester@tonetrace.app" },
      meta: { request_id: "req_xyz", timestamp: "2026-10-28T07:00:00Z" },
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockEnvelope,
    } as Response);

    const result = await apiClient.get<{ id: string; email: string }>("/api/v1/me");
    expect(result).toEqual({ id: "user_123", email: "tester@tonetrace.app" });
  });

  it("normalizes backend error envelope into typed ApiError", async () => {
    const errorEnvelope = {
      error: {
        code: "NOT_FOUND",
        message: "Product record does not exist",
        request_id: "req_err_999",
        details: null,
      },
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      headers: new Headers({
        "content-type": "application/json",
        "X-Request-ID": "req_err_999",
      }),
      json: async () => errorEnvelope,
    } as Response);

    await expect(apiClient.get("/api/v1/products/unknown-uuid")).rejects.toThrow(
      "Product record does not exist"
    );

    try {
      await apiClient.get("/api/v1/products/unknown-uuid");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.code).toBe("NOT_FOUND");
      expect(apiErr.status).toBe(404);
      expect(apiErr.requestId).toBe("req_err_999");
    }
  });

  it("attaches X-Request-ID correlation ID to outbound requests", async () => {
    let capturedHeaders: Headers | undefined;

    globalThis.fetch = vi.fn().mockImplementation((_url, init) => {
      capturedHeaders = new Headers(init?.headers);
      return Promise.resolve({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ status: "success", data: "ok" }),
      } as Response);
    });

    await apiClient.get("/health/live");
    expect(capturedHeaders?.has("X-Request-ID")).toBe(true);
    expect(capturedHeaders?.get("X-Request-ID")).toBeTruthy();
  });
});
