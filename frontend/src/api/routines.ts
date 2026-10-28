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
  ReminderPreferenceResponse,
  ReminderPreferenceUpdateRequest,
  ResponseEnvelope,
  RoutineCompletionCreateRequest,
  RoutineCompletionListResponse,
  RoutineCompletionResponse,
  RoutineCreateRequest,
  RoutineListResponse,
  RoutineResponse,
  RoutineUpdateRequest,
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

    const envelope = await apiClient.request<ResponseEnvelope<RoutineListResponse>>(
      "/me/routines",
      {
        method: "GET",
        params: queryParams,
        signal,
      }
    );
    return envelope.data;
  }

  /**
   * Retrieve a specific routine owned by the user.
   */
  public async getRoutine(routineId: string, signal?: AbortSignal): Promise<RoutineResponse> {
    if (!isValidUuid(routineId)) {
      throw new Error(`Invalid routine identifier: '${routineId}'. Expected canonical UUID.`);
    }

    const envelope = await apiClient.request<ResponseEnvelope<RoutineResponse>>(
      `/me/routines/${routineId}`,
      {
        method: "GET",
        signal,
      }
    );
    return envelope.data;
  }

  /**
   * Create a new skincare routine with ordered steps.
   */
  public async createRoutine(
    payload: RoutineCreateRequest,
    signal?: AbortSignal
  ): Promise<RoutineResponse> {
    const envelope = await apiClient.request<ResponseEnvelope<RoutineResponse>>(
      "/me/routines",
      {
        method: "POST",
        body: payload,
        signal,
      }
    );
    return envelope.data;
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

    const envelope = await apiClient.request<ResponseEnvelope<RoutineResponse>>(
      `/me/routines/${routineId}`,
      {
        method: "PATCH",
        body: payload,
        signal,
      }
    );
    return envelope.data;
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

    const envelope = await apiClient.request<ResponseEnvelope<{ status: string; routine_id: string }>>(
      `/me/routines/${routineId}`,
      {
        method: "DELETE",
        signal,
      }
    );
    return envelope.data;
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

    const envelope = await apiClient.request<ResponseEnvelope<RoutineCompletionResponse>>(
      `/me/routines/${routineId}/completions`,
      {
        method: "POST",
        body: payload,
        signal,
      }
    );
    return envelope.data;
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

    const envelope = await apiClient.request<ResponseEnvelope<RoutineCompletionListResponse>>(
      `/me/routines/${routineId}/completions`,
      {
        method: "GET",
        params: { page, page_size: pageSize },
        signal,
      }
    );
    return envelope.data;
  }

  /**
   * Get the user's reminder preferences and timezone configuration.
   */
  public async getReminders(signal?: AbortSignal): Promise<ReminderPreferenceResponse> {
    const envelope = await apiClient.request<ResponseEnvelope<ReminderPreferenceResponse>>(
      "/me/reminders",
      {
        method: "GET",
        signal,
      }
    );
    return envelope.data;
  }

  /**
   * Update reminder preferences, quiet hours, and timezone.
   */
  public async updateReminders(
    payload: ReminderPreferenceUpdateRequest,
    signal?: AbortSignal
  ): Promise<ReminderPreferenceResponse> {
    const envelope = await apiClient.request<ResponseEnvelope<ReminderPreferenceResponse>>(
      "/me/reminders",
      {
        method: "PUT",
        body: payload,
        signal,
      }
    );
    return envelope.data;
  }
}

export const routineService = new RoutineApiService();
