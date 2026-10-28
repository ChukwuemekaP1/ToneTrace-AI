/**
 * Profile & Settings API Client
 *
 * Implements verified /me endpoints:
 * - GET    /api/v1/me
 * - PATCH  /api/v1/me
 * - GET    /api/v1/me/skin-profile
 * - PUT    /api/v1/me/skin-profile
 * - GET    /api/v1/me/sensitivities
 * - POST   /api/v1/me/sensitivities
 * - DELETE /api/v1/me/sensitivities/{sensitivity_id}
 * - GET    /api/v1/me/consents
 * - PUT    /api/v1/me/consents/{purpose}
 */

import { apiClient } from "./client";
import {
  MeSummaryResponse,
  SkinProfileResponse,
  SkinProfileUpdateRequest,
  UserConsentResponse,
  UserConsentUpdateRequest,
  UserProfileResponse,
  UserProfileUpdateRequest,
  UserSensitivityCreateRequest,
  UserSensitivityItem,
} from "./types";

export class ProfileService {
  /**
   * Retrieve aggregate account and profile summary.
   */
  public async getMe(): Promise<MeSummaryResponse> {
    return apiClient.get<MeSummaryResponse>("/api/v1/me");
  }

  /**
   * Update profile display name or timezone.
   */
  public async updateProfile(
    payload: UserProfileUpdateRequest
  ): Promise<UserProfileResponse> {
    const sanitized: UserProfileUpdateRequest = {};
    if (payload.display_name !== undefined && payload.display_name !== null) {
      sanitized.display_name = payload.display_name.trim();
    }
    if (payload.timezone !== undefined && payload.timezone !== null) {
      sanitized.timezone = payload.timezone.trim();
    }
    return apiClient.patch<UserProfileResponse>("/api/v1/me", sanitized);
  }

  /**
   * Retrieve current self-reported skin profile attributes.
   */
  public async getSkinProfile(): Promise<SkinProfileResponse> {
    return apiClient.get<SkinProfileResponse>("/api/v1/me/skin-profile");
  }

  /**
   * Update or set self-reported skin type, concerns, and goals.
   */
  public async updateSkinProfile(
    payload: SkinProfileUpdateRequest
  ): Promise<SkinProfileResponse> {
    const sanitized: SkinProfileUpdateRequest = {
      skin_type: payload.skin_type ? payload.skin_type.trim().toLowerCase() : null,
      skin_concerns: (payload.skin_concerns || []).map((c) => c.trim().toLowerCase()),
      skin_goals: (payload.skin_goals || []).map((g) => g.trim().toLowerCase()),
    };
    return apiClient.put<SkinProfileResponse>("/api/v1/me/skin-profile", sanitized);
  }

  /**
   * List all reported ingredient sensitivities.
   */
  public async listSensitivities(): Promise<UserSensitivityItem[]> {
    return apiClient.get<UserSensitivityItem[]>("/api/v1/me/sensitivities");
  }

  /**
   * Record a new ingredient sensitivity/allergen.
   */
  public async addSensitivity(
    payload: UserSensitivityCreateRequest
  ): Promise<UserSensitivityItem> {
    const sanitized: UserSensitivityCreateRequest = {
      ingredient_name: payload.ingredient_name.trim(),
      severity: payload.severity || "moderate",
      notes: payload.notes ? payload.notes.trim() : null,
    };
    return apiClient.post<UserSensitivityItem>("/api/v1/me/sensitivities", sanitized);
  }

  /**
   * Delete an existing sensitivity record.
   */
  public async deleteSensitivity(
    sensitivityId: string
  ): Promise<{ message: string }> {
    return apiClient.delete<{ message: string }>(
      `/api/v1/me/sensitivities/${encodeURIComponent(sensitivityId)}`
    );
  }

  /**
   * List all privacy and data processing consents.
   */
  public async listConsents(): Promise<UserConsentResponse[]> {
    return apiClient.get<UserConsentResponse[]>("/api/v1/me/consents");
  }

  /**
   * Update or record explicit consent for a given purpose.
   */
  public async updateConsent(
    purpose: string,
    payload: UserConsentUpdateRequest
  ): Promise<UserConsentResponse> {
    const normalizedPurpose = purpose.trim().toLowerCase();
    const body: UserConsentUpdateRequest = {
      is_granted: Boolean(payload.is_granted),
      policy_version: payload.policy_version || "1.0",
    };
    return apiClient.put<UserConsentResponse>(
      `/api/v1/me/consents/${encodeURIComponent(normalizedPurpose)}`,
      body
    );
  }

  /**
   * Permanently delete user account, private storage assets, and all health data.
   */
  public async deleteAccount(): Promise<{ status: string; user_id: string; purged_storage_objects: number }> {
    return apiClient.delete<{ status: string; user_id: string; purged_storage_objects: number }>("/api/v1/me");
  }
}

export const profileService = new ProfileService();
