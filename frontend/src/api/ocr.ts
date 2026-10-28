/**
 * OCR & Product Label Scanning API Service.
 *
 * Enforces:
 * - Client-side validation of image format (JPEG, PNG, WebP) and size (<= 5 MB).
 * - Exact FormData payload mapping without manually setting multipart headers.
 * - Privacy-preserving execution (no raw bytes or extracted formulation logged).
 * - Human-in-the-loop candidate review and confirmation endpoints.
 * - Private asset deletion and My Shelf linking.
 */

import { apiClient } from "./client";
import {
  ConfirmIngredientItem,
  ConfirmScanRequest,
  ConfirmScanResponse,
  MediaAssetDeleteResponse,
  OCRScanResponse,
  ResponseEnvelope,
  ShelfItemCreateRequest,
  ShelfItemResponse,
} from "./types";

export const OCR_MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024; // 5 MB verified against backend UPLOAD_MAX_FILE_SIZE_BYTES
export const OCR_ALLOWED_MIME_TYPES = ["image/jpeg", "image/png", "image/webp"];
export const OCR_ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"];

export interface FileValidationResult {
  valid: boolean;
  error?: string;
}

export function validateImageFile(file: File): FileValidationResult {
  if (!file) {
    return { valid: false, error: "Please select an image file to scan." };
  }

  if (file.size === 0) {
    return { valid: false, error: "The selected file is empty." };
  }

  if (file.size > OCR_MAX_FILE_SIZE_BYTES) {
    return {
      valid: false,
      error: `File size exceeds the 5 MB limit (${(file.size / (1024 * 1024)).toFixed(1)} MB). Please select a smaller or compressed photo.`,
    };
  }

  // Validate MIME type
  const isMimeAllowed = OCR_ALLOWED_MIME_TYPES.includes(file.type.toLowerCase());
  // Fallback to extension check if MIME is generic (e.g. application/octet-stream)
  const lowerName = file.name.toLowerCase();
  const hasAllowedExt = OCR_ALLOWED_EXTENSIONS.some((ext) => lowerName.endsWith(ext));

  if (!isMimeAllowed && !hasAllowedExt) {
    return {
      valid: false,
      error: "Unsupported image format. Allowed formats: JPEG, PNG, or WebP.",
    };
  }

  return { valid: true };
}

export class OCRService {
  /**
   * Upload product label image and trigger OCR ingredient segmentation.
   * Uses multipart FormData with the exact "file" field expected by FastAPI.
   * Does NOT manually override Content-Type header so the browser sets boundary.
   */
  public async uploadScan(
    file: File,
    idempotencyKey?: string,
    signal?: AbortSignal
  ): Promise<OCRScanResponse> {
    const formData = new FormData();
    formData.append("file", file, file.name);

    if (idempotencyKey) {
      formData.append("idempotency_key", idempotencyKey);
    }

    const envelope = await apiClient.request<ResponseEnvelope<OCRScanResponse>>("/ocr/scans", {
      method: "POST",
      body: formData,
      signal,
    });

    return envelope.data;
  }

  /**
   * Retrieve OCR scan status, raw text, and candidate ingredients.
   */
  public async getScan(scanId: string, signal?: AbortSignal): Promise<OCRScanResponse> {
    const envelope = await apiClient.request<ResponseEnvelope<OCRScanResponse>>(
      `/ocr/scans/${scanId}`,
      {
        method: "GET",
        signal,
      }
    );
    return envelope.data;
  }

  /**
   * Poll scan status if asynchronous processing is active, with exponential backoff and timeout.
   */
  public async pollScanStatus(
    scanId: string,
    options: {
      maxWaitMs?: number;
      initialIntervalMs?: number;
      signal?: AbortSignal;
    } = {}
  ): Promise<OCRScanResponse> {
    const maxWaitMs = options.maxWaitMs ?? 20000;
    const initialIntervalMs = options.initialIntervalMs ?? 1000;
    const startTime = Date.now();
    let currentInterval = initialIntervalMs;

    while (Date.now() - startTime < maxWaitMs) {
      if (options.signal?.aborted) {
        throw new DOMException("Scan polling was aborted.", "AbortError");
      }

      const scan = await this.getScan(scanId, options.signal);
      if (scan.status === "succeeded" || scan.status === "failed") {
        return scan;
      }

      await new Promise<void>((resolve, reject) => {
        const timer = setTimeout(resolve, currentInterval);
        if (options.signal) {
          options.signal.addEventListener(
            "abort",
            () => {
              clearTimeout(timer);
              reject(new DOMException("Scan polling was aborted.", "AbortError"));
            },
            { once: true }
          );
        }
      });

      // Exponential backoff capped at 4s
      currentInterval = Math.min(currentInterval * 1.5, 4000);
    }

    throw new Error("OCR scan processing timed out. Please retry with a clearer photo.");
  }

  /**
   * Review, edit, and confirm candidate ingredients from OCR scan.
   */
  public async confirmScan(
    scanId: string,
    ingredients: ConfirmIngredientItem[]
  ): Promise<ConfirmScanResponse> {
    const payload: ConfirmScanRequest = { ingredients };
    const envelope = await apiClient.request<ResponseEnvelope<ConfirmScanResponse>>(
      `/ocr/scans/${scanId}/confirm`,
      {
        method: "POST",
        body: payload,
      }
    );
    return envelope.data;
  }

  /**
   * Delete owned private image asset bytes from backend storage.
   */
  public async deleteOwnedAsset(assetId: string): Promise<MediaAssetDeleteResponse> {
    const envelope = await apiClient.request<ResponseEnvelope<MediaAssetDeleteResponse>>(
      `/ocr/assets/by-id/${assetId}`,
      {
        method: "DELETE",
      }
    );
    return envelope.data;
  }

  /**
   * Add a confirmed custom scanned product to the user's shelf.
   */
  public async addScannedProductToShelf(
    payload: ShelfItemCreateRequest
  ): Promise<ShelfItemResponse> {
    const envelope = await apiClient.request<ResponseEnvelope<ShelfItemResponse>>("/me/shelf", {
      method: "POST",
      body: payload,
    });
    return envelope.data;
  }
}

export const ocrService = new OCRService();
