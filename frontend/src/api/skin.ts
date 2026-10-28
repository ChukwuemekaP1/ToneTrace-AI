/**
 * Skin Analysis & Longitudinal Skin Story Service (Phase 8).
 *
 * Implements:
 * - POST   /api/v1/skin/scans
 * - GET    /api/v1/skin/scans
 * - GET    /api/v1/skin/scans/{scan_id}
 * - POST   /api/v1/skin/scans/{scan_id}/poll
 * - DELETE /api/v1/skin/scans/{scan_id}
 * - GET    /api/v1/skin/story
 * - POST   /api/v1/skin/journal
 * - GET    /api/v1/skin/journal
 */

import { apiClient } from "./client";
import {
  CreateSkinJournalEntryRequest,
  ResponseEnvelope,
  SkinJournalEntryResponse,
  SkinJournalListResponse,
  SkinScanDeleteResponse,
  SkinScanListResponse,
  SkinScanResponse,
  SkinStoryResponse,
} from "./types";

export const UUID_REGEX =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

export function isValidUuid(id: string): boolean {
  if (!id) return false;
  return UUID_REGEX.test(id.trim());
}

export class SkinApiService {
  /**
   * Submit a facial photograph for provider-backed skin analysis.
   * Requires explicit active consent for 'skin_data_processing'.
   */
  public async createScan(formData: FormData): Promise<SkinScanResponse> {
    const envelope = await apiClient.request<ResponseEnvelope<SkinScanResponse>>("/skin/scans", {
      method: "POST",
      body: formData,
    });
    return envelope.data;
  }

  /**
   * List paginated skin scans for the authenticated user.
   */
  public async listScans(
    params: {
      limit?: number;
      offset?: number;
      status?: string;
    } = {}
  ): Promise<SkinScanListResponse> {
    const searchParams = new URLSearchParams();
    if (params.limit !== undefined) searchParams.set("limit", String(params.limit));
    if (params.offset !== undefined) searchParams.set("offset", String(params.offset));
    if (params.status) searchParams.set("status", params.status);

    const qs = searchParams.toString();
    const endpoint = `/skin/scans${qs ? `?${qs}` : ""}`;
    const envelope = await apiClient.request<ResponseEnvelope<SkinScanListResponse>>(endpoint, {
      method: "GET",
    });
    return envelope.data;
  }

  /**
   * Retrieve a single skin scan by UUID, with optional polling.
   */
  public async getScan(
    scanId: string,
    pollIfProcessing: boolean = false
  ): Promise<SkinScanResponse> {
    const endpoint = `/skin/scans/${encodeURIComponent(scanId)}?poll_if_processing=${pollIfProcessing}`;
    const envelope = await apiClient.request<ResponseEnvelope<SkinScanResponse>>(endpoint, {
      method: "GET",
    });
    return envelope.data;
  }

  /**
   * Explicitly poll the external skin analysis provider for a processing scan.
   */
  public async pollScan(scanId: string): Promise<SkinScanResponse> {
    const envelope = await apiClient.request<ResponseEnvelope<SkinScanResponse>>(
      `/skin/scans/${encodeURIComponent(scanId)}/poll`,
      {
        method: "POST",
        body: JSON.stringify({}),
      }
    );
    return envelope.data;
  }

  /**
   * Delete a skin scan, all associated visual observations, and purge stored private photos.
   */
  public async deleteScan(scanId: string): Promise<SkinScanDeleteResponse> {
    const envelope = await apiClient.request<ResponseEnvelope<SkinScanDeleteResponse>>(
      `/skin/scans/${encodeURIComponent(scanId)}`,
      {
        method: "DELETE",
      }
    );
    return envelope.data;
  }

  /**
   * Retrieve the longitudinal Skin Story: compatibility-checked metric timelines and journal entries.
   */
  public async getSkinStory(
    params: {
      metric?: string;
      journalLimit?: number;
    } = {}
  ): Promise<SkinStoryResponse> {
    const searchParams = new URLSearchParams();
    if (params.metric) searchParams.set("metric", params.metric);
    if (params.journalLimit !== undefined)
      searchParams.set("journal_limit", String(params.journalLimit));

    const qs = searchParams.toString();
    const endpoint = `/skin/story${qs ? `?${qs}` : ""}`;
    const envelope = await apiClient.request<ResponseEnvelope<SkinStoryResponse>>(endpoint, {
      method: "GET",
    });
    return envelope.data;
  }

  /**
   * Record a self-reported Skin Story journal reflection.
   */
  public async createJournalEntry(
    payload: CreateSkinJournalEntryRequest
  ): Promise<SkinJournalEntryResponse> {
    const envelope = await apiClient.request<ResponseEnvelope<SkinJournalEntryResponse>>(
      "/skin/journal",
      {
        method: "POST",
        body: JSON.stringify(payload),
      }
    );
    return envelope.data;
  }

  /**
   * List paginated Skin Story journal reflections.
   */
  public async listJournalEntries(
    params: {
      limit?: number;
      offset?: number;
    } = {}
  ): Promise<SkinJournalListResponse> {
    const searchParams = new URLSearchParams();
    if (params.limit !== undefined) searchParams.set("limit", String(params.limit));
    if (params.offset !== undefined) searchParams.set("offset", String(params.offset));

    const qs = searchParams.toString();
    const endpoint = `/skin/journal${qs ? `?${qs}` : ""}`;
    const envelope = await apiClient.request<ResponseEnvelope<SkinJournalListResponse>>(endpoint, {
      method: "GET",
    });
    return envelope.data;
  }
}

export const skinService = new SkinApiService();
