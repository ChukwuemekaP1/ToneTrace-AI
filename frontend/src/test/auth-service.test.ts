import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { apiClient } from "../api/client";
import { authService } from "../api/auth";
import { tokenStore } from "../api/token-store";
import { ApiError } from "../api/types";

describe("AuthService Contract & Request Shaping", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    tokenStore.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("successful registration: calls /api/v1/auth/register with exact request shape", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({
        status: "success",
        data: {
          user: {
            id: "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            email: "new_skincare_fan@example.com",
            account_status: "active",
            is_email_verified: false,
            created_at: "2026-10-28T09:00:00Z",
            updated_at: "2026-10-28T09:00:00Z",
          },
          tokens: {
            access_token: "jwt_access_new_user",
            refresh_token: "refresh_tok_new_user",
            token_type: "Bearer",
            expires_in: 900,
          },
        },
      }),
    });
    globalThis.fetch = fetchMock;

    const res = await authService.register({
      display_name: "Maya Scientist",
      email: "NEW_SKINCARE_FAN@example.com",
      password: "StrongPassword123!",
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [calledUrl, calledInit] = fetchMock.mock.calls[0];
    expect(calledUrl).toBe("/api/v1/auth/register");
    expect(calledInit.method).toBe("POST");
    expect(calledInit.headers.get("Content-Type")).toBe("application/json");

    // Exact request body verification (display_name, email normalized to lowercase, password)
    const parsedBody = JSON.parse(calledInit.body as string);
    expect(parsedBody).toEqual({
      display_name: "Maya Scientist",
      email: "new_skincare_fan@example.com",
      password: "StrongPassword123!",
    });

    // Returned shape
    expect(res.user.email).toBe("new_skincare_fan@example.com");
    expect(res.tokens.access_token).toBe("jwt_access_new_user");

    // Token store populated
    expect(tokenStore.getAccessToken()).toBe("jwt_access_new_user");
    expect(tokenStore.getRefreshToken()).toBe("refresh_tok_new_user");
  });

  it("successful login: calls /api/v1/auth/login with exact payload shape", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({
        status: "success",
        data: {
          user: {
            id: "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            email: "login_user@example.com",
            account_status: "active",
            is_email_verified: true,
            created_at: "2026-10-28T09:00:00Z",
            updated_at: "2026-10-28T09:00:00Z",
          },
          tokens: {
            access_token: "jwt_login_success",
            refresh_token: "refresh_login_success",
            token_type: "Bearer",
            expires_in: 900,
          },
        },
      }),
    });
    globalThis.fetch = fetchMock;

    const res = await authService.login({
      email: "LOGIN_USER@example.com",
      password: "CorrectPassword123!",
      device_label: "Pixel 9 Pro",
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [calledUrl, calledInit] = fetchMock.mock.calls[0];
    expect(calledUrl).toBe("/api/v1/auth/login");
    const parsedBody = JSON.parse(calledInit.body as string);
    expect(parsedBody).toEqual({
      email: "login_user@example.com",
      password: "CorrectPassword123!",
      device_label: "Pixel 9 Pro",
    });

    expect(res.tokens.access_token).toBe("jwt_login_success");
    expect(tokenStore.getAccessToken()).toBe("jwt_login_success");
  });

  it("wrong credentials: returns 401 with generic error envelope", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({
        error: {
          code: "AUTHENTICATION_ERROR",
          message: "Invalid email or password.",
          request_id: "req_fail_401",
          details: null,
        },
      }),
    });
    globalThis.fetch = fetchMock;

    await expect(
      authService.login({
        email: "unknown@example.com",
        password: "BadPassword123!",
      })
    ).rejects.toThrowError(ApiError);

    try {
      await authService.login({
        email: "unknown@example.com",
        password: "BadPassword123!",
      });
    } catch (err) {
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(401);
      expect(apiErr.code).toBe("AUTHENTICATION_ERROR");
      expect(apiErr.message).toBe("Invalid email or password.");
    }
  });

  it("server validation error: handles 422 with validation details", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({
        error: {
          code: "VALIDATION_ERROR",
          message: "Password must be at least 8 characters long.",
          request_id: "req_fail_422",
          details: [
            {
              field: "password",
              message: "String should have at least 8 characters",
              type: "string_too_short",
            },
          ],
        },
      }),
    });
    globalThis.fetch = fetchMock;

    try {
      await authService.register({
        display_name: "Test",
        email: "test@example.com",
        password: "short",
      });
      expect.unreachable("Should have thrown 422");
    } catch (err) {
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(422);
      expect(apiErr.code).toBe("VALIDATION_ERROR");
      expect(Array.isArray(apiErr.details)).toBe(true);
    }
  });

  it("network failure: gracefully transforms into ApiError with NETWORK_ERROR code", async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error("Failed to fetch"));

    await expect(
      authService.login({
        email: "netfail@example.com",
        password: "Password123!",
      })
    ).rejects.toMatchObject({
      code: "NETWORK_ERROR",
      status: 0,
    });
  });

  it("refresh success: calls /api/v1/auth/refresh with refresh token and rotates store", async () => {
    tokenStore.setTokens({
      access_token: "old_access",
      refresh_token: "old_refresh_token_to_rotate",
      token_type: "Bearer",
      expires_in: 900,
    });

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({
        status: "success",
        data: {
          access_token: "new_rotated_jwt",
          refresh_token: "new_rotated_refresh",
          token_type: "Bearer",
          expires_in: 900,
        },
      }),
    });
    globalThis.fetch = fetchMock;

    const rotated = await authService.refresh();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [calledUrl, calledInit] = fetchMock.mock.calls[0];
    expect(calledUrl).toBe("/api/v1/auth/refresh");
    const parsedBody = JSON.parse(calledInit.body as string);
    expect(parsedBody.refresh_token).toBe("old_refresh_token_to_rotate");

    expect(rotated.access_token).toBe("new_rotated_jwt");
    expect(tokenStore.getAccessToken()).toBe("new_rotated_jwt");
    expect(tokenStore.getRefreshToken()).toBe("new_rotated_refresh");
  });

  it("refresh failure: clears tokenStore immediately upon 401 rotation failure", async () => {
    tokenStore.setTokens({
      access_token: "expired_access",
      refresh_token: "compromised_or_expired_refresh",
      token_type: "Bearer",
      expires_in: 900,
    });

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({
        error: {
          code: "AUTHENTICATION_ERROR",
          message: "Invalid or revoked refresh token.",
        },
      }),
    });

    await expect(authService.refresh()).rejects.toThrow();
    expect(tokenStore.getAccessToken()).toBeNull();
    expect(tokenStore.getRefreshToken()).toBeNull();
    expect(tokenStore.hasSession()).toBe(false);
  });

  it("logout: calls /api/v1/auth/logout with refresh_token and clears store", async () => {
    tokenStore.setTokens({
      access_token: "active_access",
      refresh_token: "active_refresh_to_revoke",
      token_type: "Bearer",
      expires_in: 900,
    });

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({
        status: "success",
        data: { message: "Logged out successfully." },
      }),
    });
    globalThis.fetch = fetchMock;

    const res = await authService.logout();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [calledUrl, calledInit] = fetchMock.mock.calls[0];
    expect(calledUrl).toBe("/api/v1/auth/logout");
    const parsedBody = JSON.parse(calledInit.body as string);
    expect(parsedBody.refresh_token).toBe("active_refresh_to_revoke");

    expect(res.message).toBe("Logged out successfully.");
    expect(tokenStore.hasSession()).toBe(false);
  });

  it("logout-all: calls /api/v1/auth/logout-all with Authorization Bearer header", async () => {
    tokenStore.setTokens({
      access_token: "my_valid_access_jwt",
      refresh_token: "my_refresh_token",
      token_type: "Bearer",
      expires_in: 900,
    });

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({
        status: "success",
        data: {
          message: "All sessions terminated successfully.",
          sessions_revoked: 3,
        },
      }),
    });
    globalThis.fetch = fetchMock;

    const res = await authService.logoutAll();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [calledUrl, calledInit] = fetchMock.mock.calls[0];
    expect(calledUrl).toBe("/api/v1/auth/logout-all");
    expect(calledInit.headers.get("Authorization")).toBe("Bearer my_valid_access_jwt");

    expect(res.sessions_revoked).toBe(3);
    expect(tokenStore.hasSession()).toBe(false);
  });

  it("no refresh retry loop: retries failed business request once after refresh, and never loops on repeated 401", async () => {
    tokenStore.setTokens({
      access_token: "initial_expired_token",
      refresh_token: "valid_refresh_token",
      token_type: "Bearer",
      expires_in: 900,
    });

    let calls = 0;
    const fetchMock = vi.fn().mockImplementation(async (url: string) => {
      calls++;
      if (url === "/api/v1/auth/refresh") {
        return {
          ok: true,
          status: 200,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            status: "success",
            data: {
              access_token: "fresh_access_token_v2",
              refresh_token: "fresh_refresh_token_v2",
              token_type: "Bearer",
              expires_in: 900,
            },
          }),
        };
      }

      // If business request: simulate persistent 401 (e.g. account suspended mid-session)
      return {
        ok: false,
        status: 401,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          error: { code: "AUTHENTICATION_ERROR", message: "Account inactive" },
        }),
      };
    });

    globalThis.fetch = fetchMock;

    apiClient.setRefreshHandler(async () => {
      const rotated = await authService.refresh();
      return rotated.access_token;
    });

    // Make business call to /api/v1/me/shelf
    await expect(apiClient.get("/api/v1/me/shelf")).rejects.toThrowError();

    // Call count analysis:
    // 1st call: GET /api/v1/me/shelf -> 401
    // 2nd call: POST /api/v1/auth/refresh -> 200 (fresh token obtained)
    // 3rd call: GET /api/v1/me/shelf with _retry: true -> 401
    // Must STOP and throw, NEVER attempting a second refresh or loop!
    expect(calls).toBe(3);
  });
});
