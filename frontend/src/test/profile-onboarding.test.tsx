import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { OnboardingPage } from "../pages/auth/OnboardingPage";
import { SkinProfileEditorPage } from "../pages/SkinProfileEditorPage";
import { AuthProvider } from "../context/AuthContext";
import { profileService } from "../api/profile";
import { authService } from "../api/auth";
import { ApiError } from "../api/types";
import { FACIAL_SCAN_CONSENT_PURPOSE } from "../api/profile-constants";

describe("Onboarding Journey & Profile Editor Integration", () => {
  const mockMeSummary = {
    user: {
      id: "user-1",
      email: "tester@example.com",
      account_status: "active",
      is_email_verified: true,
      created_at: "2026-10-28T09:00:00Z",
      updated_at: "2026-10-28T09:00:00Z",
    },
    profile: {
      id: "prof-1",
      user_id: "user-1",
      display_name: "Tester",
      timezone: "America/New_York",
      created_at: "2026-10-28T09:00:00Z",
      updated_at: "2026-10-28T09:00:00Z",
    },
    skin_profile: {
      id: "sp-1",
      user_id: "user-1",
      skin_type: null,
      skin_concerns: [],
      skin_goals: [],
      created_at: "2026-10-28T09:00:00Z",
      updated_at: "2026-10-28T09:00:00Z",
    },
    sensitivities: [],
    preferences: {},
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(authService, "getMe").mockResolvedValue(mockMeSummary as any);
    vi.spyOn(profileService, "getMe").mockResolvedValue(mockMeSummary as any);
  });

  describe("OnboardingPage", () => {
    it("new user: loads defaults, detects timezone, and advances steps with accessible controls", async () => {
      vi.spyOn(profileService, "getSkinProfile").mockResolvedValue({
        id: "sp-1",
        user_id: "user-1",
        skin_type: null,
        skin_concerns: [],
        skin_goals: [],
        created_at: "2026-10-28T09:00:00Z",
        updated_at: "2026-10-28T09:00:00Z",
      });
      vi.spyOn(profileService, "listSensitivities").mockResolvedValue([]);
      vi.spyOn(profileService, "listConsents").mockResolvedValue([]);

      render(
        <AuthProvider>
          <OnboardingPage onNavigate={vi.fn()} />
        </AuthProvider>
      );

      // Wait for loading to finish and find skin type group
      const combinationBtn = await screen.findByRole("radio", { name: /combination/i });
      expect(combinationBtn).toHaveAttribute("aria-checked", "false");

      fireEvent.click(combinationBtn);
      expect(combinationBtn).toHaveAttribute("aria-checked", "true");

      // Verify concerns checkboxes
      const acneBtn = screen.getByRole("checkbox", { name: /acne/i });
      expect(acneBtn).toHaveAttribute("aria-checked", "false");
      fireEvent.click(acneBtn);
      expect(acneBtn).toHaveAttribute("aria-checked", "true");

      // Continue to Step 2
      fireEvent.click(screen.getByRole("button", { name: /continue to sensitivities/i }));
      expect(await screen.findByText(/known cosmetic sensitivities/i)).toBeInTheDocument();
    });

    it("partially completed profile: resumes previous values and allows saving progress", async () => {
      vi.spyOn(profileService, "getSkinProfile").mockResolvedValue({
        id: "sp-partial",
        user_id: "user-1",
        skin_type: "oily",
        skin_concerns: ["pores"],
        skin_goals: ["acne_control"],
        created_at: "2026-10-28T09:00:00Z",
        updated_at: "2026-10-28T09:00:00Z",
      });
      vi.spyOn(profileService, "listSensitivities").mockResolvedValue([]);
      vi.spyOn(profileService, "listConsents").mockResolvedValue([]);

      const updateSkinSpy = vi.spyOn(profileService, "updateSkinProfile").mockResolvedValue({
        id: "sp-partial",
        user_id: "user-1",
        skin_type: "oily",
        skin_concerns: ["pores"],
        skin_goals: ["acne_control"],
        created_at: "2026-10-28T09:00:00Z",
        updated_at: "2026-10-28T09:00:00Z",
      });
      vi.spyOn(profileService, "updateProfile").mockResolvedValue({
        id: "prof-1",
        user_id: "user-1",
        display_name: "Tester",
        timezone: "UTC",
        created_at: "2026-10-28T09:00:00Z",
        updated_at: "2026-10-28T09:00:00Z",
      });
      vi.spyOn(profileService, "updateConsent").mockResolvedValue({
        id: "c-1",
        user_id: "user-1",
        purpose: FACIAL_SCAN_CONSENT_PURPOSE,
        policy_version: "1.0",
        is_granted: false,
        created_at: "2026-10-28T09:00:00Z",
        updated_at: "2026-10-28T09:00:00Z",
      });

      const navigateMock = vi.fn();
      render(
        <AuthProvider>
          <OnboardingPage onNavigate={navigateMock} />
        </AuthProvider>
      );

      // Verify previously saved 'Oily' is pre-selected
      const oilyBtn = await screen.findByRole("radio", { name: /^oily\b/i });
      expect(oilyBtn).toHaveAttribute("aria-checked", "true");

      // Add another concern
      const rednessBtn = screen.getByRole("checkbox", { name: /redness & irritation/i });
      fireEvent.click(rednessBtn);

      // Save & Exit immediately
      fireEvent.click(screen.getByRole("button", { name: /save & exit/i }));

      await waitFor(() => {
        expect(updateSkinSpy).toHaveBeenCalledWith({
          skin_type: "oily",
          skin_concerns: ["pores", "redness"],
          skin_goals: ["acne_control"],
        });
        expect(navigateMock).toHaveBeenCalledWith("/");
      });
    });

    it("consent accepted: explicitly grants facial analysis consent when opted-in", async () => {
      vi.spyOn(profileService, "getSkinProfile").mockResolvedValue({
        id: "sp-1",
        user_id: "user-1",
        skin_type: "dry",
        skin_concerns: [],
        skin_goals: [],
        created_at: "2026-10-28T09:00:00Z",
        updated_at: "2026-10-28T09:00:00Z",
      });
      vi.spyOn(profileService, "listSensitivities").mockResolvedValue([]);
      vi.spyOn(profileService, "listConsents").mockResolvedValue([]);
      vi.spyOn(profileService, "updateSkinProfile").mockResolvedValue({} as any);
      vi.spyOn(profileService, "updateProfile").mockResolvedValue({} as any);
      const consentSpy = vi.spyOn(profileService, "updateConsent").mockResolvedValue({
        id: "c-1",
        user_id: "user-1",
        purpose: FACIAL_SCAN_CONSENT_PURPOSE,
        policy_version: "1.0",
        is_granted: true,
        created_at: "2026-10-28T09:00:00Z",
        updated_at: "2026-10-28T09:00:00Z",
      });

      const navigateMock = vi.fn();
      render(
        <AuthProvider>
          <OnboardingPage onNavigate={navigateMock} />
        </AuthProvider>
      );

      fireEvent.click(await screen.findByRole("button", { name: /continue to sensitivities/i }));
      fireEvent.click(await screen.findByRole("button", { name: /continue to privacy/i }));

      // Opt in to facial scan consent
      const consentCheckbox = await screen.findByRole("checkbox");
      expect(consentCheckbox).not.toBeChecked();
      fireEvent.click(consentCheckbox);
      expect(consentCheckbox).toBeChecked();

      // Finish
      fireEvent.click(screen.getByRole("button", { name: /complete setup/i }));

      await waitFor(() => {
        expect(consentSpy).toHaveBeenCalledWith(FACIAL_SCAN_CONSENT_PURPOSE, {
          is_granted: true,
          policy_version: "1.0",
        });
        expect(navigateMock).toHaveBeenCalledWith("/");
      });
    });

    it("consent declined: proceeds cleanly without blocking when consent is declined", async () => {
      vi.spyOn(profileService, "getSkinProfile").mockResolvedValue({
        id: "sp-1",
        user_id: "user-1",
        skin_type: "dry",
        skin_concerns: [],
        skin_goals: [],
        created_at: "2026-10-28T09:00:00Z",
        updated_at: "2026-10-28T09:00:00Z",
      });
      vi.spyOn(profileService, "listSensitivities").mockResolvedValue([]);
      vi.spyOn(profileService, "listConsents").mockResolvedValue([]);
      vi.spyOn(profileService, "updateSkinProfile").mockResolvedValue({} as any);
      vi.spyOn(profileService, "updateProfile").mockResolvedValue({} as any);
      const consentSpy = vi.spyOn(profileService, "updateConsent").mockResolvedValue({
        id: "c-1",
        user_id: "user-1",
        purpose: FACIAL_SCAN_CONSENT_PURPOSE,
        policy_version: "1.0",
        is_granted: false,
        created_at: "2026-10-28T09:00:00Z",
        updated_at: "2026-10-28T09:00:00Z",
      });

      const navigateMock = vi.fn();
      render(
        <AuthProvider>
          <OnboardingPage onNavigate={navigateMock} />
        </AuthProvider>
      );

      fireEvent.click(await screen.findByRole("button", { name: /continue to sensitivities/i }));
      fireEvent.click(await screen.findByRole("button", { name: /continue to privacy/i }));

      // Confirm not checked
      const consentCheckbox = await screen.findByRole("checkbox");
      expect(consentCheckbox).not.toBeChecked();

      // Complete setup without checking
      fireEvent.click(screen.getByRole("button", { name: /complete setup/i }));

      await waitFor(() => {
        expect(consentSpy).toHaveBeenCalledWith(FACIAL_SCAN_CONSENT_PURPOSE, {
          is_granted: false,
          policy_version: "1.0",
        });
        expect(navigateMock).toHaveBeenCalledWith("/");
      });
    });

    it("sensitivity add failure: displays error and retains entered text for retry", async () => {
      vi.spyOn(profileService, "getSkinProfile").mockResolvedValue({
        id: "sp-1",
        user_id: "user-1",
        skin_type: "normal",
        skin_concerns: [],
        skin_goals: [],
        created_at: "2026-10-28T09:00:00Z",
        updated_at: "2026-10-28T09:00:00Z",
      });
      vi.spyOn(profileService, "listSensitivities").mockResolvedValue([]);
      vi.spyOn(profileService, "listConsents").mockResolvedValue([]);
      vi.spyOn(profileService, "addSensitivity").mockRejectedValue(
        new ApiError("Database connection timed out", 500, "DB_TIMEOUT")
      );

      render(
        <AuthProvider>
          <OnboardingPage onNavigate={vi.fn()} />
        </AuthProvider>
      );

      fireEvent.click(await screen.findByRole("button", { name: /continue to sensitivities/i }));

      const input = await screen.findByPlaceholderText(/enter ingredient name/i);
      fireEvent.change(input, { target: { value: "Salicylic Acid" } });

      // Click add button
      const addButtons = screen.getAllByRole("button");
      const plusBtn = addButtons.find((btn) => btn.querySelector("svg.lucide-plus"));
      if (plusBtn) fireEvent.click(plusBtn);

      expect(await screen.findByText(/database connection timed out/i)).toBeInTheDocument();
      expect(input).toHaveValue("Salicylic Acid");
    });

    it("API validation error: displays error panel and preserves entered form values", async () => {
      vi.spyOn(profileService, "getSkinProfile").mockResolvedValue({
        id: "sp-1",
        user_id: "user-1",
        skin_type: "dry",
        skin_concerns: [],
        skin_goals: [],
        created_at: "2026-10-28T09:00:00Z",
        updated_at: "2026-10-28T09:00:00Z",
      });
      vi.spyOn(profileService, "listSensitivities").mockResolvedValue([]);
      vi.spyOn(profileService, "listConsents").mockResolvedValue([]);
      vi.spyOn(profileService, "updateSkinProfile").mockRejectedValue(
        new ApiError("Invalid skin concern item", 422, "VALIDATION_ERROR")
      );

      render(
        <AuthProvider>
          <OnboardingPage onNavigate={vi.fn()} />
        </AuthProvider>
      );

      fireEvent.click(await screen.findByRole("button", { name: /continue to sensitivities/i }));
      fireEvent.click(await screen.findByRole("button", { name: /continue to privacy/i }));
      fireEvent.click(await screen.findByRole("button", { name: /complete setup/i }));

      expect(await screen.findByText(/onboarding save error/i)).toBeInTheDocument();
      expect(screen.getByText(/invalid skin concern item/i)).toBeInTheDocument();
    });

    it("timezone optional/unavailable: defaults gracefully when Intl is not supported", async () => {
      const origIntl = globalThis.Intl;
      (globalThis as any).Intl = undefined;

      vi.spyOn(profileService, "getSkinProfile").mockResolvedValue({
        id: "sp-1",
        user_id: "user-1",
        skin_type: "normal",
        skin_concerns: [],
        skin_goals: [],
        created_at: "2026-10-28T09:00:00Z",
        updated_at: "2026-10-28T09:00:00Z",
      });
      vi.spyOn(profileService, "listSensitivities").mockResolvedValue([]);
      vi.spyOn(profileService, "listConsents").mockResolvedValue([]);
      const updateProfSpy = vi.spyOn(profileService, "updateProfile").mockResolvedValue({} as any);
      vi.spyOn(profileService, "updateSkinProfile").mockResolvedValue({} as any);
      vi.spyOn(profileService, "updateConsent").mockResolvedValue({} as any);

      try {
        render(
          <AuthProvider>
            <OnboardingPage onNavigate={vi.fn()} />
          </AuthProvider>
        );

        fireEvent.click(await screen.findByRole("button", { name: /continue to sensitivities/i }));
        fireEvent.click(await screen.findByRole("button", { name: /continue to privacy/i }));

        // Default UTC timezone fallback is shown
        expect(await screen.findByText("UTC")).toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: /complete setup/i }));

        await waitFor(() => {
          expect(updateProfSpy).toHaveBeenCalledWith({ timezone: "UTC" });
        });
      } finally {
        globalThis.Intl = origIntl;
      }
    });
  });

  describe("SkinProfileEditorPage (/settings/skin-profile)", () => {
    it("data reloads from backend on opening page and updates skin profile", async () => {
      const getSkinSpy = vi.spyOn(profileService, "getSkinProfile").mockResolvedValue({
        id: "sp-edit",
        user_id: "user-1",
        skin_type: "combination",
        skin_concerns: ["hyperpigmentation"],
        skin_goals: ["brightening"],
        created_at: "2026-10-28T09:00:00Z",
        updated_at: "2026-10-28T09:00:00Z",
      });
      const listSensSpy = vi.spyOn(profileService, "listSensitivities").mockResolvedValue([
        {
          id: "sens-1",
          user_id: "user-1",
          ingredient_name: "Fragrance",
          severity: "high",
          created_at: "2026-10-28T09:00:00Z",
        },
      ]);
      const listConsentSpy = vi.spyOn(profileService, "listConsents").mockResolvedValue([
        {
          id: "c-1",
          user_id: "user-1",
          purpose: FACIAL_SCAN_CONSENT_PURPOSE,
          policy_version: "1.0",
          is_granted: true,
          created_at: "2026-10-28T09:00:00Z",
          updated_at: "2026-10-28T09:00:00Z",
        },
      ]);
      const updateSkinSpy = vi.spyOn(profileService, "updateSkinProfile").mockResolvedValue({
        id: "sp-edit",
        user_id: "user-1",
        skin_type: "sensitive",
        skin_concerns: ["hyperpigmentation", "redness"],
        skin_goals: ["brightening"],
        created_at: "2026-10-28T09:00:00Z",
        updated_at: "2026-10-28T09:00:00Z",
      });
      vi.spyOn(profileService, "updateProfile").mockResolvedValue({} as any);

      render(
        <AuthProvider>
          <SkinProfileEditorPage onNavigate={vi.fn()} />
        </AuthProvider>
      );

      // Verify backend calls fired on reload
      expect(getSkinSpy).toHaveBeenCalled();
      expect(listSensSpy).toHaveBeenCalled();
      expect(listConsentSpy).toHaveBeenCalled();

      // Check loaded existing values
      expect(await screen.findByText("Fragrance")).toBeInTheDocument();
      const combBtn = screen.getByRole("radio", { name: /combination/i });
      expect(combBtn).toHaveAttribute("aria-checked", "true");

      // Switch to Sensitive
      const sensBtn = screen.getByRole("radio", { name: /sensitive/i });
      fireEvent.click(sensBtn);

      // Add Redness concern
      const rednessBtn = screen.getByRole("checkbox", { name: /redness & irritation/i });
      fireEvent.click(rednessBtn);

      // Save
      fireEvent.click(screen.getByRole("button", { name: /save profile settings/i }));

      await waitFor(() => {
        expect(updateSkinSpy).toHaveBeenCalledWith({
          skin_type: "sensitive",
          skin_concerns: ["hyperpigmentation", "redness"],
          skin_goals: ["brightening"],
        });
        expect(screen.getByText(/skin profile and preferences updated successfully/i)).toBeInTheDocument();
      });
    });

    it("consent revoked: revokes facial scan consent without erasing profile or sensitivities", async () => {
      vi.spyOn(profileService, "getSkinProfile").mockResolvedValue({
        id: "sp-edit",
        user_id: "user-1",
        skin_type: "oily",
        skin_concerns: ["acne"],
        skin_goals: [],
        created_at: "2026-10-28T09:00:00Z",
        updated_at: "2026-10-28T09:00:00Z",
      });
      vi.spyOn(profileService, "listSensitivities").mockResolvedValue([]);
      vi.spyOn(profileService, "listConsents").mockResolvedValue([
        {
          id: "c-active",
          user_id: "user-1",
          purpose: FACIAL_SCAN_CONSENT_PURPOSE,
          policy_version: "1.0",
          is_granted: true,
          created_at: "2026-10-28T09:00:00Z",
          updated_at: "2026-10-28T09:00:00Z",
        },
      ]);
      const updateConsentSpy = vi.spyOn(profileService, "updateConsent").mockResolvedValue({
        id: "c-active",
        user_id: "user-1",
        purpose: FACIAL_SCAN_CONSENT_PURPOSE,
        policy_version: "1.0",
        is_granted: false,
        revoked_at: "2026-10-28T09:30:00Z",
        created_at: "2026-10-28T09:00:00Z",
        updated_at: "2026-10-28T09:30:00Z",
      });

      render(
        <AuthProvider>
          <SkinProfileEditorPage onNavigate={vi.fn()} />
        </AuthProvider>
      );

      // Active consent badge is shown
      expect(await screen.findByText(/active \/ granted/i)).toBeInTheDocument();

      // Revoke button
      const revokeBtn = screen.getByRole("button", {
        name: /revoke facial analysis consent/i,
      });
      fireEvent.click(revokeBtn);

      await waitFor(() => {
        expect(updateConsentSpy).toHaveBeenCalledWith(FACIAL_SCAN_CONSENT_PURPOSE, {
          is_granted: false,
          policy_version: "1.0",
        });
        expect(screen.getByText(/declined \/ revoked/i)).toBeInTheDocument();
      });

      // Confirm skin type and concerns are still present and NOT erased
      const oilyBtn = screen.getByRole("radio", { name: /^oily\b/i });
      expect(oilyBtn).toHaveAttribute("aria-checked", "true");
    });
  });
});
