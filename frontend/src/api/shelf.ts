/**
 * My Shelf API Service.
 *
 * Implements:
 * - GET /api/v1/me/shelf (paginated listing with status, category, custom filters)
 * - POST /api/v1/me/shelf (add catalogue-linked or custom product, optional ocr_job_id)
 * - GET /api/v1/me/shelf/{item_id} (single item details, sensitivities, reactions)
 * - PATCH /api/v1/me/shelf/{item_id} (update status, opened date, notes, custom fields)
 * - DELETE /api/v1/me/shelf/{item_id} (remove item from shelf)
 */

import { apiClient } from "./client";
import {
  ResponseEnvelope,
  ShelfFilterParams,
  ShelfItemCreateRequest,
  ShelfItemResponse,
  ShelfItemUpdateRequest,
  ShelfListResponse,
  ShelfStatus,
} from "./types";

export const SUPPORTED_SHELF_STATUSES: { value: ShelfStatus; label: string }[] = [
  { value: "in_use", label: "In Use" },
  { value: "wishlist", label: "Wishlist" },
  { value: "finished", label: "Finished" },
  { value: "paused", label: "Paused" },
  { value: "discontinued", label: "Discontinued" },
  { value: "avoided", label: "Avoided" },
];

export const UUID_REGEX =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;
export const HEX_32_REGEX = /^[0-9a-fA-F]{32}$/;

export function isValidUuid(id: string): boolean {
  if (!id) return false;
  const trimmed = id.trim();
  return UUID_REGEX.test(trimmed) || HEX_32_REGEX.test(trimmed);
}

export class ShelfService {
  /**
   * List authenticated user's personal product shelf.
   */
  public async listShelfItems(
    params: ShelfFilterParams = {},
    signal?: AbortSignal
  ): Promise<ShelfListResponse> {
    const queryParams: Record<string, string | number | boolean | undefined> = {};
    if (params.status) queryParams.status = params.status;
    if (params.category && params.category !== "all") queryParams.category = params.category;
    if (params.is_custom !== undefined) queryParams.is_custom = params.is_custom;
    if (params.sort_by) queryParams.sort_by = params.sort_by;
    if (params.page) queryParams.page = params.page;
    if (params.page_size) queryParams.page_size = params.page_size;

    const envelope = await apiClient.request<ResponseEnvelope<ShelfListResponse>>(
      "/me/shelf",
      {
        method: "GET",
        params: queryParams,
        signal,
      }
    );
    return envelope.data;
  }

  /**
   * Retrieve a single shelf item owned by current user.
   */
  public async getShelfItem(itemId: string, signal?: AbortSignal): Promise<ShelfItemResponse> {
    if (!isValidUuid(itemId)) {
      throw new Error(`Invalid shelf item identifier: '${itemId}'. Expected canonical UUID.`);
    }

    const envelope = await apiClient.request<ResponseEnvelope<ShelfItemResponse>>(
      `/me/shelf/${itemId}`,
      {
        method: "GET",
        signal,
      }
    );
    return envelope.data;
  }

  /**
   * Add a catalogue-linked or custom product to My Shelf.
   */
  public async addShelfItem(
    payload: ShelfItemCreateRequest,
    signal?: AbortSignal
  ): Promise<ShelfItemResponse> {
    const envelope = await apiClient.request<ResponseEnvelope<ShelfItemResponse>>(
      "/me/shelf",
      {
        method: "POST",
        body: payload,
        signal,
      }
    );
    return envelope.data;
  }

  /**
   * Update shelf item status, dates, notes, or custom formulation details.
   */
  public async updateShelfItem(
    itemId: string,
    payload: ShelfItemUpdateRequest,
    signal?: AbortSignal
  ): Promise<ShelfItemResponse> {
    if (!isValidUuid(itemId)) {
      throw new Error(`Invalid shelf item identifier: '${itemId}'. Expected canonical UUID.`);
    }

    const envelope = await apiClient.request<ResponseEnvelope<ShelfItemResponse>>(
      `/me/shelf/${itemId}`,
      {
        method: "PATCH",
        body: payload,
        signal,
      }
    );
    return envelope.data;
  }

  /**
   * Remove an item from My Shelf.
   */
  public async deleteShelfItem(
    itemId: string,
    signal?: AbortSignal
  ): Promise<{ message: string; deleted_id: string }> {
    if (!isValidUuid(itemId)) {
      throw new Error(`Invalid shelf item identifier: '${itemId}'. Expected canonical UUID.`);
    }

    const envelope = await apiClient.request<ResponseEnvelope<{ message: string; deleted_id: string }>>(
      `/me/shelf/${itemId}`,
      {
        method: "DELETE",
        signal,
      }
    );
    return envelope.data;
  }
}

export const shelfService = new ShelfService();
