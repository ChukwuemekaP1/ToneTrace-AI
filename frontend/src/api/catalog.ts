/**
 * Catalog and Product Discovery API Service
 *
 * Provides typed, validated access to:
 * - Product discovery & search (/api/v1/discovery/products)
 * - Canonical product details with rule evaluation (/api/v1/discovery/products/{product_id})
 * - Ingredient evidence and research retrieval (/api/v1/ingredients/{ingredient_id}/evidence)
 */

import { apiClient } from "./client";
import {
  ApiError,
  DiscoveryFilterParams,
  DiscoveryProductDetailResponse,
  DiscoveryProductListResponse,
  IngredientEvidenceListResponse,
} from "./types";

// Standard canonical UUID regex (hyphenated 8-4-4-4-12 or 32-hex)
const UUID_REGEX = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;
const HEX_32_REGEX = /^[0-9a-fA-F]{32}$/;

export function isValidUuid(id: string): boolean {
  if (!id) return false;
  const trimmed = id.trim();
  return UUID_REGEX.test(trimmed) || HEX_32_REGEX.test(trimmed);
}

export class CatalogService {
  /**
   * Search catalogue products with debounced queries, category/brand filters,
   * sensitivity exclusions, and deterministic sorting.
   */
  public async discoverProducts(
    params: DiscoveryFilterParams = {}
  ): Promise<DiscoveryProductListResponse> {
    const queryParams: Record<string, string | number | boolean | undefined | null> = {
      page: params.page ?? 1,
      page_size: params.page_size ?? 20,
      sort_by: params.sort_by ?? "suitability_desc",
    };

    if (params.q && params.q.trim()) {
      queryParams.q = params.q.trim();
    }
    if (params.category && params.category !== "all") {
      queryParams.category = params.category;
    }
    if (params.brand && params.brand !== "all") {
      queryParams.brand = params.brand;
    }
    if (params.goal && params.goal !== "all") {
      queryParams.goal = params.goal;
    }
    if (params.exclude_user_sensitivities !== undefined) {
      queryParams.exclude_user_sensitivities = params.exclude_user_sensitivities;
    }
    if (params.require_complete_ingredients !== undefined) {
      queryParams.require_complete_ingredients = params.require_complete_ingredients;
    }

    return apiClient.get<DiscoveryProductListResponse>("/api/v1/discovery/products", {
      params: queryParams,
    });
  }

  /**
   * Retrieve canonical product detail by UUID. Throws validation error if non-UUID is supplied.
   */
  public async getProductDetail(
    productId: string,
    goal?: string
  ): Promise<DiscoveryProductDetailResponse> {
    const trimmedId = productId?.trim();
    if (!isValidUuid(trimmedId)) {
      throw new ApiError(
        "Invalid product identifier. Expected canonical UUID.",
        400,
        "INVALID_UUID"
      );
    }

    const queryParams: Record<string, string | undefined> = {};
    if (goal && goal !== "all") {
      queryParams.goal = goal;
    }

    return apiClient.get<DiscoveryProductDetailResponse>(
      `/api/v1/discovery/products/${trimmedId}`,
      { params: queryParams }
    );
  }

  /**
   * Retrieve evidence, CosIng regulatory listings, and PubMed research citations
   * for a specific cosmetic ingredient.
   */
  public async getIngredientEvidence(
    ingredientId: string,
    page = 1,
    pageSize = 10
  ): Promise<IngredientEvidenceListResponse> {
    const trimmedId = ingredientId?.trim();
    if (!isValidUuid(trimmedId)) {
      throw new ApiError(
        "Invalid ingredient identifier. Expected canonical UUID.",
        400,
        "INVALID_UUID"
      );
    }

    return apiClient.get<IngredientEvidenceListResponse>(
      `/api/v1/ingredients/${trimmedId}/evidence`,
      {
        params: { page, page_size: pageSize },
      }
    );
  }
}

export const catalogService = new CatalogService();
