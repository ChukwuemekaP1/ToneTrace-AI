import { describe, it, expect, beforeEach, vi } from "vitest";
import { tokenStore } from "../api/token-store";
import { TokenResponse } from "../api/types";

describe("TokenStore Security & Session Recovery", () => {
  beforeEach(() => {
    tokenStore.clear();
    window.sessionStorage.clear();
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it("never writes refresh tokens or access tokens to localStorage", () => {
    const localSetItemSpy = vi.spyOn(Storage.prototype, "setItem");

    const tokens: TokenResponse = {
      access_token: "secret_access_jwt_value_123",
      refresh_token: "secret_refresh_token_value_456",
      token_type: "Bearer",
      expires_in: 900,
    };

    tokenStore.setTokens(tokens);

    // Verify localStorage was NEVER called
    const localStorageCalls = localSetItemSpy.mock.instances.filter(
      (inst) => (inst as unknown) === window.localStorage
    );
    expect(localStorageCalls.length).toBe(0);

    expect(window.localStorage.getItem("tonetrace_auth_session")).toBeNull();
    expect(window.localStorage.getItem("refresh_token")).toBeNull();
    expect(window.localStorage.getItem("access_token")).toBeNull();
  });

  it("persists session in tab-scoped sessionStorage and recovers on reload", () => {
    const tokens: TokenResponse = {
      access_token: "tab_access_token_abc",
      refresh_token: "tab_refresh_token_xyz",
      token_type: "Bearer",
      expires_in: 900,
    };

    tokenStore.setTokens(tokens);

    expect(tokenStore.getAccessToken()).toBe("tab_access_token_abc");
    expect(tokenStore.getRefreshToken()).toBe("tab_refresh_token_xyz");
    expect(tokenStore.hasSession()).toBe(true);

    // Raw sessionStorage check
    const raw = window.sessionStorage.getItem("tonetrace_auth_session");
    expect(raw).toBeTruthy();
    const parsed = JSON.parse(raw!);
    expect(parsed.accessToken).toBe("tab_access_token_abc");
    expect(parsed.refreshToken).toBe("tab_refresh_token_xyz");
  });

  it("clears both in-memory and sessionStorage on clear()", () => {
    tokenStore.setTokens({
      access_token: "to_clear_acc",
      refresh_token: "to_clear_ref",
      token_type: "Bearer",
      expires_in: 900,
    });

    tokenStore.clear();

    expect(tokenStore.getAccessToken()).toBeNull();
    expect(tokenStore.getRefreshToken()).toBeNull();
    expect(tokenStore.hasSession()).toBe(false);
    expect(window.sessionStorage.getItem("tonetrace_auth_session")).toBeNull();
  });

  it("confirms no secret or token values are written to console or logs", () => {
    const consoleLogSpy = vi.spyOn(console, "log");
    const consoleWarnSpy = vi.spyOn(console, "warn");
    const consoleErrorSpy = vi.spyOn(console, "error");
    const consoleInfoSpy = vi.spyOn(console, "info");

    const secretAccessToken = "TOP_SECRET_JWT_ACCESS_ABC123";
    const secretRefreshToken = "TOP_SECRET_REFRESH_TOKEN_XYZ789";

    tokenStore.setTokens({
      access_token: secretAccessToken,
      refresh_token: secretRefreshToken,
      token_type: "Bearer",
      expires_in: 900,
    });

    tokenStore.getAccessToken();
    tokenStore.getRefreshToken();
    tokenStore.isAccessTokenExpired();
    tokenStore.clear();

    const allCalls = [
      ...consoleLogSpy.mock.calls,
      ...consoleWarnSpy.mock.calls,
      ...consoleErrorSpy.mock.calls,
      ...consoleInfoSpy.mock.calls,
    ].flat();

    const leakedSecrets = allCalls.filter(
      (arg) =>
        typeof arg === "string" &&
        (arg.includes(secretAccessToken) || arg.includes(secretRefreshToken))
    );

    expect(leakedSecrets).toEqual([]);
  });
});
