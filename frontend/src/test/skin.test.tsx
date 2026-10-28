import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { SkinScanPage } from "@/pages/SkinScanPage";
import { SkinStoryPage } from "@/pages/SkinStoryPage";
import { skinService, isValidUuid } from "@/api/skin";
import { profileService } from "@/api/profile";
import {
  SkinScanResponse,
  SkinStoryResponse,
  SkinJournalEntryResponse,
  UserConsentResponse,
  ApiError,
} from "@/api/types";

describe("Skin Analysis & Longitudinal Skin Story (/skin/scan & /skin/story) (Phase 8)", () => {
  const activeConsent: UserConsentResponse = {
    id: "c1111111-2222-3333-4444-555555555555",
    user_id: "u1111111-2222-3333-4444-555555555555",
    purpose: "skin_data_processing",
    policy_version: "1.0.0",
    is_granted: true,
    granted_at: "2026-10-01T08:00:00Z",
    revoked_at: null,
    created_at: "2026-10-01T08:00:00Z",
    updated_at: "2026-10-01T08:00:00Z",
  };

  const revokedConsent: UserConsentResponse = {
    ...activeConsent,
    is_granted: false,
    revoked_at: "2026-10-15T12:00:00Z",
  };

  const mockScanSuccess: SkinScanResponse = {
    id: "e1111111-2222-3333-4444-555555555555",
    user_id: "u1111111-2222-3333-4444-555555555555",
    provider: "mock",
    provider_task_id: "task-mock-1",
    provider_model_version: "mock-deterministic-v1.0",
    status: "succeeded",
    overall_score: 76.5,
    non_diagnostic_disclaimer:
      "Visual surface observations are derived from 2D photographs for cosmetic tracking only. They do not infer the underlying cause of pigmentation, do not diagnose any dermatological or medical condition, and do not substitute for an in-person clinical evaluation.",
    variability_disclosure:
      "Lighting, angle, device camera, image quality, and skin preparation affect comparability.",
    created_at: "2026-10-28T09:00:00Z",
    observations: [
      {
        id: "o1111111-2222-3333-4444-555555555555",
        skin_scan_id: "e1111111-2222-3333-4444-555555555555",
        metric_code: "spots",
        metric_label: "Visible Tone Unevenness & Surface Spots",
        raw_value: 78.4,
        display_value: 78.0,
        unit: "score_0_100",
        directionality: "higher_is_better",
        facial_zone: "full_face",
        provider_name: "mock",
        provider_model_version: "mock-deterministic-v1.0",
        caveat_note:
          "Visual surface metric derived from a 2D photograph. Lighting and cosmetics residue can affect this measurement.",
        observed_at: "2026-10-28T09:00:00Z",
      },
      {
        id: "o2222222-3333-4444-5555-666666666666",
        skin_scan_id: "e1111111-2222-3333-4444-555555555555",
        metric_code: "redness",
        metric_label: "Visible Surface Redness",
        raw_value: 75.1,
        display_value: 75.0,
        unit: "score_0_100",
        directionality: "higher_is_better",
        facial_zone: "full_face",
        provider_name: "mock",
        provider_model_version: "mock-deterministic-v1.0",
        caveat_note: "Cosmetic surface appearance check.",
        observed_at: "2026-10-28T09:00:00Z",
      },
    ],
  };

  const mockJournalEntry: SkinJournalEntryResponse = {
    id: "f1111111-2222-3333-4444-555555555555",
    user_id: "u1111111-2222-3333-4444-555555555555",
    skin_scan_id: null,
    recorded_at: "2026-10-28T09:30:00Z",
    perceived_skin_state: "Calm & Balanced",
    self_reported_observations: ["Cheek redness reduced", "Smooth texture"],
    routine_notes: "Morning barrier serum applied after gentle cleanser.",
    products_used: ["Centella Cleanser", "Ceramide Cream"],
    environmental_or_lifestyle_factors: {},
    notes: "Skin felt comfortable throughout the day without tightness.",
    created_at: "2026-10-28T09:30:00Z",
    updated_at: "2026-10-28T09:30:00Z",
  };

  const mockSkinStory: SkinStoryResponse = {
    user_id: "u1111111-2222-3333-4444-555555555555",
    generated_at: "2026-10-28T10:00:00Z",
    total_succeeded_scans: 3,
    metric_timelines: [
      {
        metric_code: "redness",
        metric_label: "Visible Surface Redness",
        unit: "score_0_100",
        directionality: "higher_is_better",
        baseline_provider: "mock",
        baseline_model_version: "mock-deterministic-v1.0",
        comparable_point_count: 2,
        net_observed_delta: 4.0,
        observation_classification: "visual_metric_increase",
        non_clinical_interpretation:
          "Observed surface redness score increased by 4.0 points across comparable scans. This indicates visible visual change, not clinical diagnosis.",
        compatibility_warnings: [],
        points: [
          {
            observation_id: "p1111111-1111-1111-1111-111111111111",
            scan_id: "s1111111-1111-1111-1111-111111111111",
            observed_at: "2026-10-20T09:00:00Z",
            raw_value: 71.0,
            display_value: 71.0,
            unit: "score_0_100",
            directionality: "higher_is_better",
            is_comparable_to_baseline: true,
          },
          {
            observation_id: "p2222222-2222-2222-2222-222222222222",
            scan_id: "s2222222-2222-2222-2222-222222222222",
            observed_at: "2026-10-28T09:00:00Z",
            raw_value: 75.0,
            display_value: 75.0,
            unit: "score_0_100",
            directionality: "higher_is_better",
            is_comparable_to_baseline: true,
          },
        ],
      },
      {
        metric_code: "spots",
        metric_label: "Visible Tone Unevenness & Surface Spots",
        unit: "score_0_100",
        directionality: "higher_is_better",
        baseline_provider: "mock",
        baseline_model_version: "mock-deterministic-v1.0",
        comparable_point_count: 1,
        net_observed_delta: null,
        observation_classification: "insufficient_comparable_data",
        non_clinical_interpretation:
          "A single baseline observation has been recorded. At least two comparable scans are required to evaluate visual change.",
        compatibility_warnings: [
          "Scan on 2026-10-15 used a different optical version and cannot be directly compared to current baseline.",
        ],
        points: [
          {
            observation_id: "p3333333-3333-3333-3333-333333333333",
            scan_id: "s3333333-3333-3333-3333-333333333333",
            observed_at: "2026-10-15T09:00:00Z",
            raw_value: 65.0,
            display_value: 65.0,
            unit: "score_0_100",
            directionality: "higher_is_better",
            is_comparable_to_baseline: false,
            incompatibility_reason: "Optical engine version mismatch (v0.9 vs v1.0).",
          },
          {
            observation_id: "p4444444-4444-4444-4444-444444444444",
            scan_id: "s4444444-4444-4444-4444-444444444444",
            observed_at: "2026-10-28T09:00:00Z",
            raw_value: 78.0,
            display_value: 78.0,
            unit: "score_0_100",
            directionality: "higher_is_better",
            is_comparable_to_baseline: true,
          },
        ],
      },
    ],
    recent_journal_entries: [mockJournalEntry],
    capture_variability_notice:
      "Lighting, angle, device camera, image quality, and skin preparation affect comparability.",
    non_diagnostic_disclaimer:
      "Visual surface observations are derived from 2D photographs for cosmetic tracking only.",
    pigmentation_and_causation_guardrail:
      "ToneTrace AI reports only surface-level visual appearance metrics and never infers biological cause of pigmentation.",
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe("UUID Validation Helper", () => {
    it("validates canonical UUID formats correctly", () => {
      expect(isValidUuid("e1111111-2222-3333-4444-555555555555")).toBe(true);
      expect(isValidUuid("12345678-1234-1234-1234-1234567890ab")).toBe(true);
      expect(isValidUuid("s1111111-2222-3333-4444-555555555555")).toBe(false);
      expect(isValidUuid("not-a-uuid")).toBe(false);
      expect(isValidUuid("")).toBe(false);
    });
  });

  describe("Facial Scan Flow (/skin/scan) & Privacy Consent Gates", () => {
    it("blocks image submission when consent is missing and renders explicit consent explanation", async () => {
      vi.spyOn(profileService, "listConsents").mockResolvedValue([]);

      render(<SkinScanPage onNavigate={vi.fn()} />);

      expect(await screen.findByText("Explicit Privacy Consent Required")).toBeInTheDocument();
      expect(
        screen.getByText(/Facial skin analysis processes photographs of your face/i)
      ).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Grant Facial Analysis Consent" })).toBeInTheDocument();

      // Camera input / submit button must not be available
      expect(screen.queryByText("Analyze Facial Surface")).not.toBeInTheDocument();
    });

    it("blocks upload when consent is revoked and allows re-granting directly", async () => {
      vi.spyOn(profileService, "listConsents").mockResolvedValue([revokedConsent]);
      const updateConsentSpy = vi.spyOn(profileService, "updateConsent").mockResolvedValue({
        ...activeConsent,
        is_granted: true,
      });

      render(<SkinScanPage onNavigate={vi.fn()} />);

      expect(await screen.findByText("Explicit Privacy Consent Required")).toBeInTheDocument();

      // Click grant consent
      const grantBtn = screen.getByRole("button", { name: "Grant Facial Analysis Consent" });
      fireEvent.click(grantBtn);

      await waitFor(() => {
        expect(updateConsentSpy).toHaveBeenCalledWith("skin_data_processing", {
          is_granted: true,
          policy_version: "1.0.0",
        });
      });

      // After consent is granted, camera/upload form is revealed
      expect(await screen.findByLabelText("Upload facial photograph")).toBeInTheDocument();
    });

    it("enforces client-side validation for unsupported file types and oversized images", async () => {
      vi.spyOn(profileService, "listConsents").mockResolvedValue([activeConsent]);

      render(<SkinScanPage onNavigate={vi.fn()} />);

      const fileInput = await screen.findByLabelText("Upload facial photograph");

      // 1. Unsupported MIME type (PDF)
      const pdfFile = new File(["dummy pdf content"], "medical_record.pdf", {
        type: "application/pdf",
      });
      fireEvent.change(fileInput, { target: { files: [pdfFile] } });

      expect(
        await screen.findByText(/Unsupported file format. Please upload a JPEG, PNG, or WebP photograph/i)
      ).toBeInTheDocument();

      // 2. Oversized image (> 10MB)
      const hugeBytes = new Uint8Array(11 * 1024 * 1024);
      const hugeFile = new File([hugeBytes], "giant_photo.jpg", { type: "image/jpeg" });
      fireEvent.change(fileInput, { target: { files: [hugeFile] } });

      expect(
        await screen.findByText(/exceeds the maximum allowed limit of 10 MB/i)
      ).toBeInTheDocument();
    });

    it("submits valid photo with capture conditions and renders exact observation fields and mock badge", async () => {
      vi.spyOn(profileService, "listConsents").mockResolvedValue([activeConsent]);
      const createScanSpy = vi.spyOn(skinService, "createScan").mockResolvedValue(mockScanSuccess);

      // Mock URL.createObjectURL / revokeObjectURL for JSDOM
      window.URL.createObjectURL = vi.fn(() => "blob:http://localhost/preview-1");
      window.URL.revokeObjectURL = vi.fn();

      render(<SkinScanPage onNavigate={vi.fn()} />);

      const fileInput = await screen.findByLabelText("Upload facial photograph");

      const validImage = new File(["fake image content"], "selfie.jpg", { type: "image/jpeg" });
      fireEvent.change(fileInput, { target: { files: [validImage] } });

      expect(await screen.findByText("selfie.jpg")).toBeInTheDocument();

      // Set capture conditions
      const lightingSelect = screen.getByLabelText("Ambient Lighting");
      fireEvent.change(lightingSelect, { target: { value: "natural_daylight" } });

      const cosmeticsCheck = screen.getByRole("checkbox");
      fireEvent.click(cosmeticsCheck);

      // Submit
      const submitBtn = screen.getByRole("button", { name: "Analyze Facial Surface" });
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(createScanSpy).toHaveBeenCalledWith(expect.any(FormData));
      });

      // Observations rendering
      expect(await screen.findByText("Demo / Simulated Analysis Environment")).toBeInTheDocument();
      expect(screen.getByText("Visible Tone Unevenness & Surface Spots")).toBeInTheDocument();
      expect(screen.getByText("78")).toBeInTheDocument();
      expect(screen.getByText("Visible Surface Redness")).toBeInTheDocument();
      expect(screen.getByText("75")).toBeInTheDocument();

      // Non-clinical disclaimer present
      expect(
        screen.getByText(/Visual surface observations are derived from 2D photographs for cosmetic tracking only/i)
      ).toBeInTheDocument();
    });

    it("displays error panel when scan API fails and allows retry", async () => {
      vi.spyOn(profileService, "listConsents").mockResolvedValue([activeConsent]);
      vi.spyOn(skinService, "createScan").mockRejectedValue(
        new ApiError("Face could not be clearly framed in lighting.", 422)
      );

      window.URL.createObjectURL = vi.fn(() => "blob:http://localhost/preview-2");
      window.URL.revokeObjectURL = vi.fn();

      render(<SkinScanPage onNavigate={vi.fn()} />);

      const fileInput = await screen.findByLabelText("Upload facial photograph");
      const validImage = new File(["fake image content"], "selfie.jpg", { type: "image/jpeg" });
      fireEvent.change(fileInput, { target: { files: [validImage] } });

      const submitBtn = await screen.findByRole("button", { name: "Analyze Facial Surface" });
      fireEvent.click(submitBtn);

      expect(
        await screen.findByText("Face could not be clearly framed in lighting.")
      ).toBeInTheDocument();

      // Dismiss button
      const dismissBtn = screen.getByRole("button", { name: "Dismiss" });
      fireEvent.click(dismissBtn);

      expect(
        screen.queryByText("Face could not be clearly framed in lighting.")
      ).not.toBeInTheDocument();
    });

    it("supports scan deletion workflow with confirmation dialog and purges data", async () => {
      vi.spyOn(profileService, "listConsents").mockResolvedValue([activeConsent]);
      const deleteScanSpy = vi.spyOn(skinService, "deleteScan").mockResolvedValue({
        scan_id: mockScanSuccess.id,
        status: "deleted",
        purged_media_count: 1,
        deleted_at: "2026-10-28T09:15:00Z",
        message: "Scan record and private photos permanently deleted.",
      });

      // Deep linked scan mock
      vi.spyOn(skinService, "getScan").mockResolvedValue(mockScanSuccess);

      render(<SkinScanPage onNavigate={vi.fn()} initialScanId={mockScanSuccess.id} />);

      const deleteBtn = await screen.findByRole("button", { name: "Delete Scan" });
      fireEvent.click(deleteBtn);

      expect(await screen.findByText("Delete Skin Scan?")).toBeInTheDocument();
      expect(
        screen.getByText(/permanently delete this scan record, its visual surface observations, and purge/i)
      ).toBeInTheDocument();

      // Confirm deletion
      const confirmDeleteBtn = screen.getByRole("button", { name: "Yes, Permanently Delete" });
      fireEvent.click(confirmDeleteBtn);

      await waitFor(() => {
        expect(deleteScanSpy).toHaveBeenCalledWith(mockScanSuccess.id);
      });

      expect(
        await screen.findByText("Scan record and private photos permanently deleted.")
      ).toBeInTheDocument();
    });
  });

  describe("Longitudinal Skin Story & Journal Reflection (/skin/story)", () => {
    it("renders longitudinal metric timelines and draws SVG line chart only when multiple comparable observations exist", async () => {
      vi.spyOn(skinService, "getSkinStory").mockResolvedValue(mockSkinStory);

      render(<SkinStoryPage onNavigate={vi.fn()} />);

      expect(
        await screen.findByRole("heading", { name: "Skin Story" })
      ).toBeInTheDocument();
      expect(
        screen.getByRole("heading", { name: "Visible Surface Redness" })
      ).toBeInTheDocument();
      expect(screen.getByText("+4")).toBeInTheDocument();

      // Comparable trend chart present for Redness (2 comparable points)
      expect(screen.getByText("Comparable Visual Score Trend")).toBeInTheDocument();
      expect(
        screen.getByRole("img", {
          name: "Visual trend line chart for Visible Surface Redness",
        })
      ).toBeInTheDocument();

      // Non-clinical and causation disclaimers
      expect(
        screen.getByText(/Photo-based observations are for tracking visible changes, not a clinical diagnosis/i)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Temporal correlation does not imply clinical causation/i)
      ).toBeInTheDocument();
    });

    it("displays discrete observations and explanation instead of a false line chart when data is insufficient or non-comparable", async () => {
      vi.spyOn(skinService, "getSkinStory").mockResolvedValue(mockSkinStory);

      render(<SkinStoryPage onNavigate={vi.fn()} />);

      await screen.findByRole("heading", { name: "Skin Story" });

      // For Spots timeline (only 1 comparable point, 1 incompatible point)
      expect(
        screen.getByRole("heading", {
          name: "Visible Tone Unevenness & Surface Spots",
        })
      ).toBeInTheDocument();
      expect(screen.getByText("Single / Insufficient Data")).toBeInTheDocument();
      expect(screen.getByText("Discrete Historical Observations")).toBeInTheDocument();
      expect(
        screen.getByText(/A continuous line chart requires at least 2 comparable observations/i)
      ).toBeInTheDocument();

      // Shows compatibility warning & badge
      expect(
        screen.getByText(/Scan on 2026-10-15 used a different optical version and cannot be directly compared/i)
      ).toBeInTheDocument();
      expect(screen.getByText("Non-comparable")).toBeInTheDocument();
      expect(
        screen.getByText("Optical engine version mismatch (v0.9 vs v1.0).")
      ).toBeInTheDocument();
    });

    it("creates and appends a self-reported skin journal reflection", async () => {
      vi.spyOn(skinService, "getSkinStory").mockResolvedValue(mockSkinStory);
      const createJournalSpy = vi
        .spyOn(skinService, "createJournalEntry")
        .mockResolvedValue(mockJournalEntry);

      render(<SkinStoryPage onNavigate={vi.fn()} />);

      const logJournalBtn = await screen.findByRole("button", { name: "New journal reflection" });
      fireEvent.click(logJournalBtn);

      expect(await screen.findByText("Log Skin Reflection")).toBeInTheDocument();

      // Select state chip
      const calmChip = screen.getByRole("button", { name: "Calm & Balanced" });
      fireEvent.click(calmChip);

      // Add routine notes
      const routineInput = screen.getByPlaceholderText(
        "e.g. Skipped exfoliant today; added barrier moisturizer"
      );
      fireEvent.change(routineInput, {
        target: { value: "Morning barrier serum applied after gentle cleanser." },
      });

      // Submit reflection
      const saveBtn = screen.getByRole("button", { name: "Save Reflection" });
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(createJournalSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            perceived_skin_state: "Calm & Balanced",
            routine_notes: "Morning barrier serum applied after gentle cleanser.",
          })
        );
      });

      expect(
        await screen.findByText("Journal reflection logged successfully.")
      ).toBeInTheDocument();
    });

    it("renders empty state when no skin story data exists and guides user to take first scan", async () => {
      vi.spyOn(skinService, "getSkinStory").mockResolvedValue({
        user_id: "u1111111-2222-3333-4444-555555555555",
        generated_at: "2026-10-28T10:00:00Z",
        total_succeeded_scans: 0,
        metric_timelines: [],
        recent_journal_entries: [],
        capture_variability_notice: "Variability notice",
        non_diagnostic_disclaimer: "Non-diagnostic disclaimer",
        pigmentation_and_causation_guardrail: "Guardrail",
      });

      const navigateSpy = vi.fn();
      render(<SkinStoryPage onNavigate={navigateSpy} />);

      expect(await screen.findByText("No Skin Story Observations Yet")).toBeInTheDocument();

      const startScanBtn = screen.getByRole("button", { name: "Start First Skin Scan" });
      fireEvent.click(startScanBtn);

      expect(navigateSpy).toHaveBeenCalledWith("/skin/scan");
    });
  });
});
