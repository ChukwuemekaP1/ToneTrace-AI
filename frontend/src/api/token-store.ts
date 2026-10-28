/**
 * Secure Token Store
 *
 * Implements token lifecycle management adhering strictly to security policies:
 * 1. NEVER writes refresh or access tokens to localStorage.
 * 2. In-memory closure is the primary token store.
 * 3. Tab-scoped sessionStorage is used strictly for surviving page reload/navigation.
 * 4. Zero secret/token values are ever emitted to logs or console.
 */

import { TokenResponse } from "./types";

const SESSION_STORAGE_KEY = "tonetrace_auth_session";

interface SessionState {
  accessToken: string | null;
  refreshToken: string | null;
  tokenType: string;
  expiresAt: number | null; // timestamp in ms
}

class TokenStore {
  private inMemoryState: SessionState = {
    accessToken: null,
    refreshToken: null,
    tokenType: "Bearer",
    expiresAt: null,
  };

  constructor() {
    this.hydrateFromSessionStorage();
  }

  private hydrateFromSessionStorage(): void {
    if (typeof window === "undefined" || !window.sessionStorage) {
      return;
    }

    try {
      // Strictly verify localStorage is never touched
      const raw = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed.accessToken === "string" && typeof parsed.refreshToken === "string") {
          this.inMemoryState = {
            accessToken: parsed.accessToken,
            refreshToken: parsed.refreshToken,
            tokenType: parsed.tokenType || "Bearer",
            expiresAt: parsed.expiresAt ?? null,
          };
        }
      }
    } catch {
      // Fallback cleanly to in-memory state if sessionStorage is unavailable or corrupt
      this.inMemoryState = {
        accessToken: null,
        refreshToken: null,
        tokenType: "Bearer",
        expiresAt: null,
      };
    }
  }

  public setTokens(tokens: TokenResponse): void {
    const expiresAt = Date.now() + (tokens.expires_in || 900) * 1000;

    this.inMemoryState = {
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
      tokenType: tokens.token_type || "Bearer",
      expiresAt,
    };

    if (typeof window !== "undefined" && window.sessionStorage) {
      try {
        window.sessionStorage.setItem(
          SESSION_STORAGE_KEY,
          JSON.stringify(this.inMemoryState)
        );
      } catch {
        // Storage quota or disabled storage fallback - in-memory persists for SPA
      }
    }
  }

  public getAccessToken(): string | null {
    return this.inMemoryState.accessToken;
  }

  public getRefreshToken(): string | null {
    return this.inMemoryState.refreshToken;
  }

  public getTokenType(): string {
    return this.inMemoryState.tokenType;
  }

  public isAccessTokenExpired(): boolean {
    if (!this.inMemoryState.accessToken || !this.inMemoryState.expiresAt) {
      return true;
    }
    // Buffer by 30 seconds to refresh proactively before hard expiration
    return Date.now() >= this.inMemoryState.expiresAt - 30 * 1000;
  }

  public hasSession(): boolean {
    return Boolean(this.inMemoryState.refreshToken);
  }

  public clear(): void {
    this.inMemoryState = {
      accessToken: null,
      refreshToken: null,
      tokenType: "Bearer",
      expiresAt: null,
    };

    if (typeof window !== "undefined" && window.sessionStorage) {
      try {
        window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
      } catch {
        // Ignore removal error
      }
    }
  }
}

export const tokenStore = new TokenStore();
