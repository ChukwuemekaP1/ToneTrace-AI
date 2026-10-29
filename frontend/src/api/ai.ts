/**
 * Grounded AI Explanation API Service (Phase 7 & 9)
 *
 * Provides typed, validated access to POST /api/v1/ai/explanations.
 * Sends strictly expected fields and handles ResponseEnvelope unwrapping.
 */

import { apiClient } from "./client";
import {
  ApiError,
  ExplanationRequest,
  ExplanationResponse,
} from "./types";

export class AiExplanationService {
  /**
   * Request a grounded skincare explanation backed by retrieved evidence.
   */
  public async createExplanation(
    request: ExplanationRequest
  ): Promise<ExplanationResponse> {
    const cleanedQuestion = request.question?.trim() || "";
    if (cleanedQuestion.length < 3) {
      throw new ApiError(
        "Question must contain at least 3 characters.",
        422,
        "VALIDATION_ERROR"
      );
    }
    if (cleanedQuestion.length > 1500) {
      throw new ApiError(
        "Question must not exceed 1500 characters.",
        422,
        "VALIDATION_ERROR"
      );
    }

    const payload: ExplanationRequest = {
      schema_version: "1.0",
      question: cleanedQuestion,
      include_user_skin_profile: request.include_user_skin_profile ?? true,
    };

    if (request.product_ids && request.product_ids.length > 0) {
      payload.product_ids = request.product_ids.slice(0, 5);
    }
    if (request.ingredient_ids && request.ingredient_ids.length > 0) {
      payload.ingredient_ids = request.ingredient_ids.slice(0, 15);
    }
    if (request.ocr_job_id) {
      payload.ocr_job_id = request.ocr_job_id;
    }
    if (request.search_query && request.search_query.trim()) {
      payload.search_query = request.search_query.trim().slice(0, 200);
    }

    return await apiClient.post<ExplanationResponse>(
      "/api/v1/ai/explanations",
      payload
    );
  }
}

export const aiService = new AiExplanationService();
