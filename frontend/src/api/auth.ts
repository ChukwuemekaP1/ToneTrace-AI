/**
 * Authentication Service
 *
 * Implements the verified contract for ToneTrace FastAPI backend:
 * - POST /api/v1/auth/register
 * - POST /api/v1/auth/login
 * - POST /api/v1/auth/refresh
 * - POST /api/v1/auth/logout
 * - POST /api/v1/auth/logout-all
 * - GET  /api/v1/me
 *
 * Enforces zero secret leakage to logs and strictly matches verified payload contracts.
 */

import { apiClient } from "./client";
import { tokenStore } from "./token-store";
import {
  AuthSuccessResponse,
  MeSummaryResponse,
  RefreshTokenRequest,
  TokenResponse,
  UserLoginRequest,
  UserRegisterRequest,
} from "./types";

export class AuthService {
  /**
   * Register a new user account with display name and initial session.
   */
  public async register(payload: UserRegisterRequest): Promise<AuthSuccessResponse> {
    const sanitizedPayload: UserRegisterRequest = {
      email: payload.email.trim().toLowerCase(),
      password: payload.password,
      display_name: payload.display_name.trim(),
    };

    const result = await apiClient.post<AuthSuccessResponse>(
      "/api/v1/auth/register",
      sanitizedPayload
    );

    if (result && result.tokens) {
      tokenStore.setTokens(result.tokens);
    }

    return result;
  }

  /**
   * Authenticate user with email and password.
   */
  public async login(payload: UserLoginRequest): Promise<AuthSuccessResponse> {
    const sanitizedPayload: UserLoginRequest = {
      email: payload.email.trim().toLowerCase(),
      password: payload.password,
      device_label: payload.device_label || "Mobile Web",
    };

    const result = await apiClient.post<AuthSuccessResponse>(
      "/api/v1/auth/login",
      sanitizedPayload
    );

    if (result && result.tokens) {
      tokenStore.setTokens(result.tokens);
    }

    return result;
  }

  /**
   * Rotate refresh token to obtain a fresh access token and single-use refresh token.
   */
  public async refresh(refreshToken?: string): Promise<TokenResponse> {
    const token = refreshToken || tokenStore.getRefreshToken();
    if (!token) {
      tokenStore.clear();
      throw new Error("No refresh token available to rotate.");
    }

    const payload: RefreshTokenRequest = {
      refresh_token: token,
      device_label: "Mobile Web Session",
    };

    try {
      const result = await apiClient.post<TokenResponse>(
        "/api/v1/auth/refresh",
        payload
      );

      if (result && result.access_token && result.refresh_token) {
        tokenStore.setTokens(result);
      }

      return result;
    } catch (err) {
      // Rotation failed or token family revoked due to replay attack
      tokenStore.clear();
      throw err;
    }
  }

  /**
   * Revoke single active session.
   */
  public async logout(refreshToken?: string): Promise<{ message: string }> {
    const token = refreshToken || tokenStore.getRefreshToken();
    try {
      if (token) {
        const payload: RefreshTokenRequest = { refresh_token: token };
        return await apiClient.post<{ message: string }>("/api/v1/auth/logout", payload);
      }
      return { message: "Session already cleared." };
    } finally {
      tokenStore.clear();
    }
  }

  /**
   * Revoke all active sessions belonging to the caller across all devices.
   */
  public async logoutAll(): Promise<{ message: string; sessions_revoked: number }> {
    try {
      const result = await apiClient.post<{ message: string; sessions_revoked: number }>(
        "/api/v1/auth/logout-all"
      );
      return result;
    } finally {
      tokenStore.clear();
    }
  }

  /**
   * Fetch current authenticated user's aggregate profile, sensitivities, and skin profile.
   */
  public async getMe(): Promise<MeSummaryResponse> {
    return apiClient.get<MeSummaryResponse>("/api/v1/me");
  }
}

export const authService = new AuthService();
