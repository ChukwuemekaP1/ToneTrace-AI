/**
 * Routines & Reminders API Service.
 *
 * Implements:
 * - GET /api/v1/me/routines
 * - POST /api/v1/me/routines
 * - GET /api/v1/me/routines/{routine_id}
 * - PATCH /api/v1/me/routines/{routine_id}
 * - DELETE /api/v1/me/routines/{routine_id}
 * - POST /api/v1/me/routines/{routine_id}/completions
 * - GET /api/v1/me/routines/{routine_id}/completions
 * - GET /api/v1/me/reminders
 * - PUT /api/v1/me/reminders
 */

import { apiClient } from "./client";
import {
  ReactionListResponse,
  ReminderPreferenceResponse,
  ReminderPreferenceUpdateRequest,
  RoutineCompletionCreateRequest,
  RoutineCompletionListResponse,
  RoutineCompletionResponse,
  RoutineCreateRequest,
  RoutineListResponse,
  RoutineResponse,
  RoutineUpdateRequest,
  SafetyAwareReactionResponse,
  StandaloneReactionCreateRequest,
} from "./types";

export const UUID_REGEX =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;
export const HEX_32_REGEX = /^[0-9a-fA-F]{32}$/;

export function isValidUuid(id: string): boolean {
  if (!id) return false;
  const trimmed = id.trim();
  return UUID_REGEX.test(trimmed) || HEX_32_REGEX.test(trimmed);
}

export class RoutineApiService {
  /**
   * List the authenticated user's skincare routines.
   */
  public async listRoutines(
    params: {
      time_of_day?: string;
      is_active?: boolean;
      page?: number;
      page_size?: number;
    } = {},
    signal?: AbortSignal
  ): Promise<RoutineListResponse> {
    const queryParams: Record<string, string | number | boolean | undefined> = {};
    if (params.time_of_day && params.time_of_day !== "all") {
      queryParams.time_of_day = params.time_of_day;
    }
    if (params.is_active !== undefined) queryParams.is_active = params.is_active;
    if (params.page) queryParams.page = params.page;
    if (params.page_size) queryParams.page_size = params.page_size;

    return await apiClient.get<RoutineListResponse>("/api/v1/me/routines", {
      params: queryParams,
      signal,
    });
  }

  /**
   * Retrieve a specific routine owned by the user.
   */
  public async getRoutine(routineId: string, signal?: AbortSignal): Promise<RoutineResponse> {
    if (!isValidUuid(routineId)) {
      throw new Error(`Invalid routine identifier: '${routineId}'. Expected canonical UUID.`);
    }

    return await apiClient.get<RoutineResponse>(`/api/v1/me/routines/${routineId}`, { signal });
  }

  /**
   * Create a new skincare routine with ordered steps.
   */
  public async createRoutine(
    payload: RoutineCreateRequest,
    signal?: AbortSignal
  ): Promise<RoutineResponse> {
    return await apiClient.post<RoutineResponse>("/api/v1/me/routines", payload, { signal });
  }

  /**
   * Update a routine or its steps.
   */
  public async updateRoutine(
    routineId: string,
    payload: RoutineUpdateRequest,
    signal?: AbortSignal
  ): Promise<RoutineResponse> {
    if (!isValidUuid(routineId)) {
      throw new Error(`Invalid routine identifier: '${routineId}'. Expected canonical UUID.`);
    }

    return await apiClient.patch<RoutineResponse>(`/api/v1/me/routines/${routineId}`, payload, {
      signal,
    });
  }

  /**
   * Delete a routine.
   */
  public async deleteRoutine(
    routineId: string,
    signal?: AbortSignal
  ): Promise<{ status: string; routine_id: string }> {
    if (!isValidUuid(routineId)) {
      throw new Error(`Invalid routine identifier: '${routineId}'. Expected canonical UUID.`);
    }

    return await apiClient.delete<{ status: string; routine_id: string }>(
      `/api/v1/me/routines/${routineId}`,
      { signal }
    );
  }

  /**
   * Record a routine completion.
   */
  public async recordCompletion(
    routineId: string,
    payload: RoutineCompletionCreateRequest = {},
    signal?: AbortSignal
  ): Promise<RoutineCompletionResponse> {
    if (!isValidUuid(routineId)) {
      throw new Error(`Invalid routine identifier: '${routineId}'. Expected canonical UUID.`);
    }

    return await apiClient.post<RoutineCompletionResponse>(
      `/api/v1/me/routines/${routineId}/completions`,
      payload,
      { signal }
    );
  }

  /**
   * List historical completions for a routine.
   */
  public async listCompletions(
    routineId: string,
    page = 1,
    pageSize = 20,
    signal?: AbortSignal
  ): Promise<RoutineCompletionListResponse> {
    if (!isValidUuid(routineId)) {
      throw new Error(`Invalid routine identifier: '${routineId}'. Expected canonical UUID.`);
    }

    return await apiClient.get<RoutineCompletionListResponse>(
      `/api/v1/me/routines/${routineId}/completions`,
      {
        params: { page, page_size: pageSize },
        signal,
      }
    );
  }

  /**
   * Get the user's reminder preferences and timezone configuration.
   */
  public async getReminders(signal?: AbortSignal): Promise<ReminderPreferenceResponse> {
    return await apiClient.get<ReminderPreferenceResponse>("/api/v1/me/reminders", { signal });
  }

  /**
   * Update reminder preferences, quiet hours, and timezone.
   */
  public async updateReminders(
    payload: ReminderPreferenceUpdateRequest,
    signal?: AbortSignal
  ): Promise<ReminderPreferenceResponse> {
    return await apiClient.put<ReminderPreferenceResponse>("/api/v1/me/reminders", payload, {
      signal,
    });
  }

  /**
   * Record a user-reported product reaction with safety & urgent-care evaluation.
   */
  public async createReaction(
    payload: StandaloneReactionCreateRequest,
    signal?: AbortSignal
  ): Promise<SafetyAwareReactionResponse> {
    return await apiClient.post<SafetyAwareReactionResponse>(
      "/api/v1/me/product-reactions",
      payload,
      { signal }
    );
  }

  /**
   * List user-reported product reactions with pagination and optional filters.
   */
  public async listReactions(
    params: {
      reaction_type?: string;
      severity?: string;
      page?: number;
      page_size?: number;
    } = {},
    signal?: AbortSignal
  ): Promise<ReactionListResponse> {
    const queryParams: Record<string, string | number | undefined> = {};
    if (params.reaction_type && params.reaction_type !== "all") {
      queryParams.reaction_type = params.reaction_type;
    }
    if (params.severity && params.severity !== "all") {
      queryParams.severity = params.severity;
    }
    if (params.page) queryParams.page = params.page;
    if (params.page_size) queryParams.page_size = params.page_size;

    return await apiClient.get<ReactionListResponse>("/api/v1/me/product-reactions", {
      params: queryParams,
      signal,
    });
  }
}

export const routineService = new RoutineApiService();
