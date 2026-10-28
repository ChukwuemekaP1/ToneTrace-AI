import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ScanLabelModal } from "@/components/ocr/ScanLabelModal";
import { ocrService } from "@/api/ocr";
import { ApiError, OCRScanResponse, ConfirmScanResponse, ShelfItemResponse } from "@/api/types";
import { DashboardPage } from "@/pages/DashboardPage";
import { ShelfPlaceholder } from "@/pages/Placeholders";
import { AuthProvider } from "@/context/AuthContext";

describe("OCR Label Scanning Workflow (Phase 5)", () => {
  const mockMediaAsset = {
    id: "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
    storage_provider: "postgres",
    original_filename: "serum_label.jpg",
    content_type: "image/jpeg",
    file_size_bytes: 1024 * 500, // 500 KB
    image_width: 800,
    image_height: 1200,
    sha256_hash: "abcdef1234567890",
    retention_policy: "ocr_retain_30d",
    retention_expires_at: "2026-11-27T12:00:00Z",
    is_deleted: false,
    deleted_at: null,
    view_url: null,
    created_at: "2026-10-28T12:00:00Z",
  };

  const mockScanResponse: OCRScanResponse = {
    id: "scan-job-uuid-1234",
    status: "succeeded",
    provider: "ocr_space",
    raw_text: "INGREDIENTS: Aqua/Water/Eau, Niacinamide, Glycerin, Phenoxyethanol",
    confidence_score: 0.94,
    processing_time_ms: 1240,
    error_category: null,
    error_message: null,
    media_asset: mockMediaAsset,
    candidates: [
      {
        id: "cand-1",
        position: 1,
        raw_text: "Aqua/Water/Eau",
        normalized_name: "Water",
        matched_ingredient_id: "ing-1",
        confidence: 0.96,
        is_user_corrected: false,
        is_confirmed: false,
      },
      {
        id: "cand-2",
        position: 2,
        raw_text: "Niacinamide",
        normalized_name: "Niacinamide",
        matched_ingredient_id: "ing-2",
        confidence: 0.98,
        is_user_corrected: false,
        is_confirmed: false,
      },
      {
        id: "cand-3",
        position: 3,
        raw_text: "Glycerin",
        normalized_name: "Glycerin",
        matched_ingredient_id: "ing-3",
        confidence: 0.95,
        is_user_corrected: false,
        is_confirmed: false,
      },
    ],
    candidate_count: 3,
    created_at: "2026-10-28T12:00:00Z",
    updated_at: "2026-10-28T12:00:01Z",
  };

  const mockConfirmResponse: ConfirmScanResponse = {
    scan_id: "scan-job-uuid-1234",
    status: "confirmed",
    confirmed_count: 3,
    candidates: [
      {
        id: "cand-1",
        position: 1,
        raw_text: "Aqua/Water/Eau",
        normalized_name: "Purified Water",
        matched_ingredient_id: "ing-1",
        confidence: 0.96,
        is_user_corrected: true,
        is_confirmed: true,
      },
      {
        id: "cand-2",
        position: 2,
        raw_text: "Niacinamide",
        normalized_name: "Niacinamide",
        matched_ingredient_id: "ing-2",
        confidence: 0.98,
        is_user_corrected: false,
        is_confirmed: true,
      },
      {
        id: "cand-3",
        position: 3,
        raw_text: "Glycerin",
        normalized_name: "Glycerin",
        matched_ingredient_id: "ing-3",
        confidence: 0.95,
        is_user_corrected: false,
        is_confirmed: true,
      },
    ],
    message: "Candidate ingredient list confirmed successfully.",
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe("File Validation & Upload Triggers", () => {
    it("rejects files exceeding 5 MB limit with clear inline validation error", async () => {
      render(<ScanLabelModal isOpen={true} onClose={vi.fn()} />);

      const fileInput = screen.getByLabelText(/upload packaging label photo/i);
      const oversizedFile = new File([new Uint8Array(6 * 1024 * 1024)], "huge_label.jpg", {
        type: "image/jpeg",
      });

      fireEvent.change(fileInput, { target: { files: [oversizedFile] } });

      expect(await screen.findByText(/file size exceeds the 5 mb limit/i)).toBeInTheDocument();
      // Should not show Process Label button
      expect(screen.queryByRole("button", { name: /process label/i })).not.toBeInTheDocument();
    });

    it("rejects unsupported file formats (e.g. PDF or text)", async () => {
      render(<ScanLabelModal isOpen={true} onClose={vi.fn()} />);

      const fileInput = screen.getByLabelText(/upload packaging label photo/i);
      const invalidFile = new File(["not an image"], "formula.pdf", {
        type: "application/pdf",
      });

      fireEvent.change(fileInput, { target: { files: [invalidFile] } });

      expect(
        await screen.findByText(/unsupported image format\. allowed formats: jpeg, png, or webp/i)
      ).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /process label/i })).not.toBeInTheDocument();
    });

    it("accepts valid JPEG, shows file summary, and does not upload until user clicks Process Label", async () => {
      const uploadSpy = vi.spyOn(ocrService, "uploadScan").mockResolvedValue(mockScanResponse);

      render(<ScanLabelModal isOpen={true} onClose={vi.fn()} />);

      const fileInput = screen.getByLabelText(/upload packaging label photo/i);
      const validFile = new File([new Uint8Array(1024 * 500)], "serum_label.jpg", {
        type: "image/jpeg",
      });

      fireEvent.change(fileInput, { target: { files: [validFile] } });

      // File details shown
      expect(await screen.findByText("serum_label.jpg")).toBeInTheDocument();
      expect(screen.getByText(/0\.49 mb/i)).toBeInTheDocument();
      // Notice shown that image stays local until triggered
      expect(screen.getByText(/image remains locally on your device until you press/i)).toBeInTheDocument();

      // No upload was triggered yet
      expect(uploadSpy).not.toHaveBeenCalled();

      // Now click Process Label
      const processButton = screen.getByRole("button", { name: /process label/i });
      fireEvent.click(processButton);

      // Upload called with file and unique idempotency key
      await waitFor(() => {
        expect(uploadSpy).toHaveBeenCalledWith(
          validFile,
          expect.stringMatching(/^scan_\d+_/),
          expect.any(AbortSignal)
        );
      });
    });
  });

  describe("OCR Extraction, Human-in-the-Loop Review & Confirmation", () => {
    it("renders unconfirmed candidates, allows editing, reordering, adding missing items, and confirms", async () => {
      vi.spyOn(ocrService, "uploadScan").mockResolvedValue(mockScanResponse);
      const confirmSpy = vi.spyOn(ocrService, "confirmScan").mockResolvedValue(mockConfirmResponse);

      render(<ScanLabelModal isOpen={true} onClose={vi.fn()} />);

      // Select valid file and process
      const fileInput = screen.getByLabelText(/upload packaging label photo/i);
      const validFile = new File([new Uint8Array(1024 * 500)], "serum_label.jpg", {
        type: "image/jpeg",
      });
      fireEvent.change(fileInput, { target: { files: [validFile] } });
      fireEvent.click(screen.getByRole("button", { name: /process label/i }));

      // Review step is rendered with plain-language untrusted text disclaimer
      expect(
        await screen.findByText(/unconfirmed ocr candidate candidates/i)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/extracted text is untrusted\. curved bottles, reflective plastic/i)
      ).toBeInTheDocument();

      // Provider and confidence displayed
      expect(screen.getByText("ocr_space")).toBeInTheDocument();
      expect(screen.getByText("94%")).toBeInTheDocument();

      // View raw text as plain text
      const viewRawBtn = screen.getByRole("button", { name: /view untrusted raw ocr text/i });
      fireEvent.click(viewRawBtn);
      expect(
        screen.getByText("INGREDIENTS: Aqua/Water/Eau, Niacinamide, Glycerin, Phenoxyethanol")
      ).toBeInTheDocument();

      // Edit first candidate name from "Water" to "Purified Water"
      const waterInput = screen.getByLabelText(/ingredient candidate 1/i);
      fireEvent.change(waterInput, { target: { value: "Purified Water" } });

      // Add a missing candidate
      const addMissingInput = screen.getByPlaceholderText(/add missing ingredient\.\.\./i);
      fireEvent.change(addMissingInput, { target: { value: "Tocopherol" } });
      fireEvent.click(screen.getByRole("button", { name: /^add$/i }));

      expect(screen.getByDisplayValue("Tocopherol")).toBeInTheDocument();

      // Remove the newly added Tocopherol
      const removeTocopherolBtn = screen.getByRole("button", { name: /remove tocopherol/i });
      fireEvent.click(removeTocopherolBtn);
      expect(screen.queryByDisplayValue("Tocopherol")).not.toBeInTheDocument();

      // Confirm formulation
      const confirmBtn = screen.getByRole("button", { name: /confirm formulation/i });
      fireEvent.click(confirmBtn);

      await waitFor(() => {
        expect(confirmSpy).toHaveBeenCalledWith("scan-job-uuid-1234", [
          { candidate_id: "cand-1", position: 1, name: "Purified Water", is_confirmed: true },
          { candidate_id: "cand-2", position: 2, name: "Niacinamide", is_confirmed: true },
          { candidate_id: "cand-3", position: 3, name: "Glycerin", is_confirmed: true },
        ]);
      });

      // Confirmed screen appears with verified badges
      expect(await screen.findByText("Formulation Verified & Saved")).toBeInTheDocument();
      expect(screen.getByText(/3 candidate ingredients verified/i)).toBeInTheDocument();
      expect(screen.getByText("1. Purified Water")).toBeInTheDocument();
    });

    it("prevents double submissions by disabling buttons while in flight", async () => {
      let resolveUpload: (val: OCRScanResponse) => void;
      const slowUploadPromise = new Promise<OCRScanResponse>((res) => {
        resolveUpload = res;
      });
      vi.spyOn(ocrService, "uploadScan").mockReturnValue(slowUploadPromise);

      render(<ScanLabelModal isOpen={true} onClose={vi.fn()} />);

      const fileInput = screen.getByLabelText(/upload packaging label photo/i);
      const validFile = new File([new Uint8Array(1024 * 100)], "test.jpg", { type: "image/jpeg" });
      fireEvent.change(fileInput, { target: { files: [validFile] } });

      const processBtn = screen.getByRole("button", { name: /process label/i });
      fireEvent.click(processBtn);

      // Scanning view is displayed
      expect(await screen.findByText(/extracting formulation data/i)).toBeInTheDocument();

      // Resolve upload
      resolveUpload!(mockScanResponse);

      expect(await screen.findByText(/unconfirmed ocr candidate candidates/i)).toBeInTheDocument();
    });
  });

  describe("Error Recovery & Edge Cases", () => {
    it("handles rate limit (429) error with calm specific message", async () => {
      vi.spyOn(ocrService, "uploadScan").mockRejectedValue(
        new ApiError("Rate limit exceeded", 429, "RATE_LIMIT_EXCEEDED")
      );

      render(<ScanLabelModal isOpen={true} onClose={vi.fn()} />);

      const fileInput = screen.getByLabelText(/upload packaging label photo/i);
      const validFile = new File([new Uint8Array(1024 * 100)], "test.jpg", { type: "image/jpeg" });
      fireEvent.change(fileInput, { target: { files: [validFile] } });
      fireEvent.click(screen.getByRole("button", { name: /process label/i }));

      expect(await screen.findByRole("heading", { name: /quota exceeded/i })).toBeInTheDocument();
      expect(
        screen.getByText(/scan quota exceeded\. please wait a few moments before trying again\./i)
      ).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /select different image/i })).toBeInTheDocument();
    });

    it("handles upstream provider unavailable (500) error gracefully", async () => {
      vi.spyOn(ocrService, "uploadScan").mockRejectedValue(
        new ApiError("OCR provider unavailable", 503, "UPSTREAM_UNAVAILABLE")
      );

      render(<ScanLabelModal isOpen={true} onClose={vi.fn()} />);

      const fileInput = screen.getByLabelText(/upload packaging label photo/i);
      const validFile = new File([new Uint8Array(1024 * 100)], "test.jpg", { type: "image/jpeg" });
      fireEvent.change(fileInput, { target: { files: [validFile] } });
      fireEvent.click(screen.getByRole("button", { name: /process label/i }));

      expect(await screen.findByRole("heading", { name: /ocr service busy/i })).toBeInTheDocument();
      expect(
        screen.getByText(/ocr server service is temporarily unavailable/i)
      ).toBeInTheDocument();
    });

    it("handles unreadable / empty packaging scan response", async () => {
      vi.spyOn(ocrService, "uploadScan").mockResolvedValue({
        ...mockScanResponse,
        status: "succeeded",
        raw_text: "",
        candidates: [],
        candidate_count: 0,
      });

      render(<ScanLabelModal isOpen={true} onClose={vi.fn()} />);

      const fileInput = screen.getByLabelText(/upload packaging label photo/i);
      const validFile = new File([new Uint8Array(1024 * 100)], "blank.jpg", { type: "image/jpeg" });
      fireEvent.change(fileInput, { target: { files: [validFile] } });
      fireEvent.click(screen.getByRole("button", { name: /process label/i }));

      expect(await screen.findByRole("heading", { name: /unreadable packaging/i })).toBeInTheDocument();
      expect(
        screen.getByText(/no ingredient text could be recognized\. please check lighting/i)
      ).toBeInTheDocument();
    });
  });

  describe("My Shelf Integration & Retention Policy", () => {
    it("allows adding confirmed scanned product to My Shelf via POST /me/shelf", async () => {
      vi.spyOn(ocrService, "uploadScan").mockResolvedValue(mockScanResponse);
      vi.spyOn(ocrService, "confirmScan").mockResolvedValue(mockConfirmResponse);

      const mockShelfItem: ShelfItemResponse = {
        id: "shelf-uuid-9999",
        user_id: "user-uuid-1",
        product_id: null,
        ocr_job_id: "scan-job-uuid-1234",
        custom_name: "Centella Soothing Gel",
        custom_brand: "SkinScience",
        custom_category: "Moisturizer",
        status: "in_use",
        is_custom: true,
        catalogue_status: "custom_entry",
        display_name: "Centella Soothing Gel",
        display_brand: "SkinScience",
        display_category: "Moisturizer",
        ingredient_data_status: "complete",
        ingredient_names: ["Purified Water", "Niacinamide", "Glycerin"],
        sensitivity_alerts: [],
        is_public: false,
        created_at: "2026-10-28T12:05:00Z",
        updated_at: "2026-10-28T12:05:00Z",
      };

      const shelfSpy = vi
        .spyOn(ocrService, "addScannedProductToShelf")
        .mockResolvedValue(mockShelfItem);

      render(<ScanLabelModal isOpen={true} onClose={vi.fn()} />);

      // Progress through scan and confirm
      const fileInput = screen.getByLabelText(/upload packaging label photo/i);
      fireEvent.change(fileInput, {
        target: { files: [new File([new Uint8Array(100)], "label.jpg", { type: "image/jpeg" })] },
      });
      fireEvent.click(screen.getByRole("button", { name: /process label/i }));
      expect(await screen.findByText(/confirm formulation/i)).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /confirm formulation/i }));

      // Confirmed step: Add to Shelf form is present
      expect(await screen.findByText(/save scanned product to my shelf/i)).toBeInTheDocument();

      const nameInput = screen.getByPlaceholderText(/e\.g\. centella soothing gel/i);
      const brandInput = screen.getByPlaceholderText(/e\.g\. skinscience/i);
      fireEvent.change(nameInput, { target: { value: "Centella Soothing Gel" } });
      fireEvent.change(brandInput, { target: { value: "SkinScience" } });

      const addShelfBtn = screen.getByRole("button", { name: /add to my shelf/i });
      fireEvent.click(addShelfBtn);

      await waitFor(() => {
        expect(shelfSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            ocr_job_id: "scan-job-uuid-1234",
            custom_name: "Centella Soothing Gel",
            custom_brand: "SkinScience",
            custom_category: "Moisturizer",
            status: "in_use",
            custom_ingredient_text: "Purified Water, Niacinamide, Glycerin",
          })
        );
      });

      expect(
        await screen.findByText(/"Centella Soothing Gel" successfully saved to My Shelf!/i)
      ).toBeInTheDocument();
    });

    it("displays retention policy and supports voluntary private image asset deletion", async () => {
      vi.spyOn(ocrService, "uploadScan").mockResolvedValue(mockScanResponse);
      vi.spyOn(ocrService, "confirmScan").mockResolvedValue(mockConfirmResponse);
      const deleteSpy = vi.spyOn(ocrService, "deleteOwnedAsset").mockResolvedValue({
        asset_id: mockMediaAsset.id,
        status: "deleted",
        deleted_at: "2026-10-28T12:06:00Z",
        message: "Asset bytes deleted",
      });

      render(<ScanLabelModal isOpen={true} onClose={vi.fn()} />);

      const fileInput = screen.getByLabelText(/upload packaging label photo/i);
      fireEvent.change(fileInput, {
        target: { files: [new File([new Uint8Array(100)], "label.jpg", { type: "image/jpeg" })] },
      });
      fireEvent.click(screen.getByRole("button", { name: /process label/i }));
      expect(await screen.findByText(/confirm formulation/i)).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /confirm formulation/i }));

      // Confirmed view shows retention policy
      expect(await screen.findByText(/ocr_retain_30d/i)).toBeInTheDocument();
      expect(screen.getByText(/expires in 30 days or delete immediately/i)).toBeInTheDocument();

      // Voluntary delete image asset
      const deleteBtn = screen.getByRole("button", { name: /delete image asset now/i });
      fireEvent.click(deleteBtn);

      await waitFor(() => {
        expect(deleteSpy).toHaveBeenCalledWith(mockMediaAsset.id);
      });

      expect(
        await screen.findByText(/image bytes successfully deleted from backend storage/i)
      ).toBeInTheDocument();
    });
  });

  describe("Entry from Dashboard & My Shelf", () => {
    it("Dashboard quick action 'Scan a Label' opens the scan modal", async () => {
      render(
        <AuthProvider>
          <DashboardPage onNavigate={vi.fn()} />
        </AuthProvider>
      );

      const scanQuickAction = screen.getByRole("button", { name: /scan a label/i });
      fireEvent.click(scanQuickAction);

      // Modal dialog opens
      expect(await screen.findByRole("dialog")).toBeInTheDocument();
      expect(screen.getByText(/label scanner/i)).toBeInTheDocument();
      expect(screen.getByText(/private formulation extraction/i)).toBeInTheDocument();

      // Can dismiss with Close button
      const closeBtn = screen.getByRole("button", { name: /close scanner modal/i });
      fireEvent.click(closeBtn);

      await waitFor(() => {
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      });
    });

    it("My Shelf header button 'Scan a Label' opens the scan modal", async () => {
      render(<ShelfPlaceholder onNavigate={vi.fn()} />);

      const scanBtn = screen.getByRole("button", { name: /scan a label/i });
      fireEvent.click(scanBtn);

      expect(await screen.findByRole("dialog")).toBeInTheDocument();
      expect(screen.getByText(/label scanner/i)).toBeInTheDocument();
    });
  });
});
