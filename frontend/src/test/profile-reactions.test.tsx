import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AuthProvider } from "@/context/AuthContext";
import { ProfilePage } from "@/pages/ProfilePage";
import { ProductReactionModal } from "@/components/reactions/ProductReactionModal";
import { ShelfPage } from "@/pages/ShelfPage";
import { profileService } from "@/api/profile";
import { routineService } from "@/api/routines";
import { shelfService } from "@/api/shelf";
import { authService } from "@/api/auth";
import { tokenStore } from "@/api/token-store";
import {
  SafetyAwareReactionResponse,
  ShelfItemResponse,
  UserConsentResponse,
} from "@/api/types";
import { FACIAL_SCAN_CONSENT_PURPOSE } from "@/api/profile-constants";

describe("Phase 10: Product Reactions, Profile, Settings & Privacy", () => {
  const mockUser = {
    id: "user-uuid-1111-2222-3333-444455556666",
    email: "sarah@tonetrace.test",
    account_status: "active",
    is_email_verified: true,
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
  };

  const mockProfileSummary = {
    user: mockUser,
    profile: {
      id: "prof-uuid-111",
      user_id: mockUser.id,
      display_name: "Sarah Jenkins",
      timezone: "America/New_York",
      created_at: "2026-10-01T00:00:00Z",
      updated_at: "2026-10-01T00:00:00Z",
    },
    skin_profile: {
      id: "sp-uuid-111",
      user_id: mockUser.id,
      skin_type: "combination",
      skin_concerns: ["redness", "sensitivity"],
      skin_goals: ["barrier_repair"],
      created_at: "2026-10-01T00:00:00Z",
      updated_at: "2026-10-01T00:00:00Z",
    },
    sensitivities: [
      { id: "sens-1", ingredient_name: "Fragrance", severity: "high" },
      { id: "sens-2", ingredient_name: "Denatured Alcohol", severity: "moderate" },
    ],
    preferences: null,
  };

  const mockShelfItems: ShelfItemResponse[] = [
    {
      id: "item-111",
      user_id: mockUser.id,
      product_id: "prod-111",
      custom_name: null,
      custom_brand: null,
      custom_category: null,
      catalogue_status: "catalogue_linked",
      ingredient_data_status: "complete",
      is_public: false,
      status: "in_use",
      opened_at: "2026-10-10T00:00:00Z",
      expires_at: "2027-10-10T00:00:00Z",
      display_name: "Hydrating Cleanser",
      display_brand: "CeraVe",
      display_category: "Cleanser",
      is_custom: false,
      ingredient_names: ["Water", "Ceramides", "Hyaluronic Acid"],
      sensitivity_alerts: [],
      private_notes: "Gentle morning wash",
      created_at: "2026-10-10T00:00:00Z",
      updated_at: "2026-10-10T00:00:00Z",
    },
    {
      id: "item-222",
      user_id: mockUser.id,
      product_id: null,
      custom_name: "Calming Recovery Toner",
      custom_brand: "Custom Care",
      custom_category: "Toner",
      catalogue_status: "custom_entry",
      ingredient_data_status: "complete",
      is_public: false,
      status: "in_use",
      opened_at: "2026-10-15T00:00:00Z",
      expires_at: null,
      display_name: "Calming Recovery Toner",
      display_brand: "Custom Care",
      display_category: "Toner",
      is_custom: true,
      ingredient_names: ["Centella", "Panthenol", "Fragrance"],
      sensitivity_alerts: ["Fragrance"],
      private_notes: "Slight stinging noticed",
      created_at: "2026-10-15T00:00:00Z",
      updated_at: "2026-10-15T00:00:00Z",
    },
  ];

  const mockConsents: UserConsentResponse[] = [
    {
      id: "consent-1",
      user_id: mockUser.id,
      purpose: FACIAL_SCAN_CONSENT_PURPOSE,
      policy_version: "2026.1",
      is_granted: true,
      granted_at: "2026-10-01T10:00:00Z",
      revoked_at: null,
      created_at: "2026-10-01T10:00:00Z",
      updated_at: "2026-10-01T10:00:00Z",
    },
  ];

  const mockReactions: SafetyAwareReactionResponse[] = [
    {
      id: "react-1",
      user_id: mockUser.id,
      user_product_id: "item-222",
      product_id: null,
      product_display_name: "Custom Care Calming Recovery Toner",
      routine_id: null,
      observed_at: "2026-10-20T18:00:00Z",
      reaction_type: "stinging",
      severity: "mild",
      symptoms: ["stinging", "redness"],
      is_rapidly_worsening: false,
      suspected_ingredient_names: ["Fragrance"],
      notes: "Stung on cheeks immediately after applying",
      requires_urgent_care_guidance: false,
      urgent_care_guidance: null,
      is_causal_proof: false,
      is_medical_diagnosis: false,
      ordinary_recommendations_suspended: false,
      epistemic_disclaimer:
        "Product reactions reflect reported tolerance patterns and do not constitute an allergy test or medical diagnosis.",
      created_at: "2026-10-20T18:05:00Z",
    },
  ];

  beforeEach(() => {
    vi.restoreAllMocks();

    tokenStore.setTokens({
      access_token: "mock-access-token",
      refresh_token: "mock-refresh-token",
      token_type: "bearer",
      expires_in: 900,
    });

    vi.spyOn(authService, "refresh").mockResolvedValue({
      access_token: "mock-access-token",
      refresh_token: "mock-refresh-token",
      token_type: "bearer",
      expires_in: 900,
    });
    vi.spyOn(authService, "getMe").mockResolvedValue(mockProfileSummary);
    vi.spyOn(profileService, "getMe").mockResolvedValue(mockProfileSummary);
    vi.spyOn(profileService, "getSkinProfile").mockResolvedValue(mockProfileSummary.skin_profile);
    vi.spyOn(profileService, "listConsents").mockResolvedValue(mockConsents);
    vi.spyOn(profileService, "updateConsent").mockResolvedValue({
      id: "consent-1",
      user_id: mockUser.id,
      purpose: FACIAL_SCAN_CONSENT_PURPOSE,
      policy_version: "2026.1",
      is_granted: false,
      granted_at: null,
      revoked_at: "2026-10-28T12:00:00Z",
      created_at: "2026-10-01T10:00:00Z",
      updated_at: "2026-10-28T12:00:00Z",
    });
    vi.spyOn(profileService, "addSensitivity").mockResolvedValue({
      id: "sens-3",
      user_id: mockUser.id,
      ingredient_name: "Niacinamide",
      severity: "moderate",
      created_at: "2026-10-28T12:00:00Z",
    });
    vi.spyOn(profileService, "deleteSensitivity").mockResolvedValue(undefined as any);
    vi.spyOn(profileService, "updateProfile").mockResolvedValue({
      id: "prof-uuid-111",
      user_id: mockUser.id,
      display_name: "Sarah Updated",
      timezone: "America/Chicago",
      created_at: "2026-10-01T00:00:00Z",
      updated_at: "2026-10-28T12:00:00Z",
    });
    vi.spyOn(profileService, "deleteAccount").mockResolvedValue({
      status: "deleted",
      user_id: mockUser.id,
      purged_storage_objects: 3,
    });

    vi.spyOn(routineService, "listReactions").mockResolvedValue({
      items: mockReactions,
      total: 1,
      page: 1,
      page_size: 20,
      epistemic_disclaimer: "Non-diagnostic disclaimer",
    });

    vi.spyOn(shelfService, "listShelfItems").mockResolvedValue({
      items: mockShelfItems,
      total: 2,
      page: 1,
      page_size: 50,
      total_pages: 1,
    });
  });

  describe("ProductReactionModal Workflow", () => {
    it("renders reaction form with non-alarmist copy and non-diagnostic disclaimer", async () => {
      render(
        <ProductReactionModal
          isOpen={true}
          onClose={vi.fn()}
        />
      );

      // Verify header and non-diagnostic disclaimer
      expect(screen.getByText("Report Product Reaction")).toBeInTheDocument();
      expect(
        screen.getByText(/never a medical diagnosis of an allergic reaction/i)
      ).toBeInTheDocument();

      // Product selector should be present when no initial product is provided
      expect(await screen.findByLabelText(/Select product for reaction/i)).toBeInTheDocument();

      // Reaction types chips
      expect(screen.getByText("Skin Irritation")).toBeInTheDocument();
      expect(screen.getByText("Stinging / Burning")).toBeInTheDocument();

      // Symptoms multi-select
      expect(screen.getByRole("button", { name: /✓ Redness/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /^Itching$/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /^Swelling$/i })).toBeInTheDocument();

      // Rapidly worsening checkbox
      expect(
        screen.getByText(/Reaction is rapidly worsening or spreading/i)
      ).toBeInTheDocument();
    });

    it("displays urgent care escalation guidance immediately when severe severity or worsening is checked", async () => {
      render(
        <ProductReactionModal
          isOpen={true}
          onClose={vi.fn()}
        />
      );

      // Initially, no urgent care notice
      expect(screen.queryByText(/Immediate Medical Care Notice/i)).not.toBeInTheDocument();

      // Select 'severe' severity
      const severeButton = screen.getByRole("button", { name: /^severe/i });
      fireEvent.click(severeButton);

      // Urgent care banner should appear
      expect(screen.getByText(/Immediate Medical Care Notice/i)).toBeInTheDocument();
      expect(
        screen.getByText(/URGENT CARE GUIDANCE/i)
      ).toBeInTheDocument();

      // Reset to mild
      const mildButton = screen.getByRole("button", { name: /^mild/i });
      fireEvent.click(mildButton);
      expect(screen.queryByText(/Immediate Medical Care Notice/i)).not.toBeInTheDocument();

      // Checking 'rapidly worsening' triggers urgent care notice again
      const worseningCheckbox = screen.getByRole("checkbox");
      fireEvent.click(worseningCheckbox);
      expect(screen.getByText(/Immediate Medical Care Notice/i)).toBeInTheDocument();
    });

    it("validates required product before submitting", async () => {
      render(
        <ProductReactionModal
          isOpen={true}
          onClose={vi.fn()}
        />
      );

      const submitBtn = screen.getByRole("button", { name: /Record Reaction/i });
      expect(submitBtn).toBeDisabled();
    });

    it("submits reaction to backend and displays confirmation with epistemic disclaimer", async () => {
      const createReactionSpy = vi.spyOn(routineService, "createReaction").mockResolvedValue({
        id: "react-new-123",
        user_id: mockUser.id,
        user_product_id: "item-111",
        product_id: "prod-111",
        product_display_name: "CeraVe Hydrating Cleanser",
        routine_id: null,
        observed_at: new Date().toISOString(),
        reaction_type: "irritation",
        severity: "mild",
        symptoms: ["redness"],
        is_rapidly_worsening: false,
        suspected_ingredient_names: ["Ceramides"],
        notes: "Mild redness on forehead",
        requires_urgent_care_guidance: false,
        urgent_care_guidance: null,
        is_causal_proof: false,
        is_medical_diagnosis: false,
        ordinary_recommendations_suspended: false,
        epistemic_disclaimer:
          "Reported tolerance data is private to your profile. This does not constitute clinical allergy diagnosis.",
        created_at: new Date().toISOString(),
      });

      const onReactionCreatedMock = vi.fn();

      render(
        <ProductReactionModal
          isOpen={true}
          onClose={vi.fn()}
          initialUserProductId="item-111"
          initialProductId="prod-111"
          initialProductName="CeraVe Hydrating Cleanser"
          onReactionCreated={onReactionCreatedMock}
        />
      );

      // Pre-populated product display
      expect(screen.getByText("CeraVe Hydrating Cleanser")).toBeInTheDocument();

      // Fill in suspected ingredient and notes
      fireEvent.change(screen.getByPlaceholderText(/e\.g\. Fragrance, Glycolic Acid/i), {
        target: { value: "Ceramides" },
      });
      fireEvent.change(screen.getByPlaceholderText(/Describe when symptoms began/i), {
        target: { value: "Mild redness on forehead" },
      });

      // Submit
      const submitBtn = screen.getByRole("button", { name: /Record Reaction/i });
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(createReactionSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            user_product_id: "item-111",
            product_id: "prod-111",
            reaction_type: "irritation",
            severity: "mild",
            suspected_ingredient_names: ["Ceramides"],
            notes: "Mild redness on forehead",
          })
        );
      });

      // Verify confirmation screen
      expect(await screen.findByText(/Reaction Logged Successfully/i)).toBeInTheDocument();
      expect(
        screen.getByText(/This does not constitute clinical allergy diagnosis/i)
      ).toBeInTheDocument();
      expect(onReactionCreatedMock).toHaveBeenCalled();
    });
  });

  describe("Profile Page & Settings Management", () => {
    it("renders user information, timezone, and skin blueprint summary", async () => {
      render(
        <AuthProvider>
          <ProfilePage onNavigate={vi.fn()} />
        </AuthProvider>
      );

      // Authenticated user details
      expect(await screen.findByText("Sarah Jenkins")).toBeInTheDocument();
      expect(screen.getByText("sarah@tonetrace.test")).toBeInTheDocument();
      expect(screen.getByText(/America\/New_York/i)).toBeInTheDocument();
      expect(screen.getByText("active")).toBeInTheDocument();

      // Skin Blueprint deep link card
      expect(screen.getByText(/Skin Blueprint/i)).toBeInTheDocument();
      expect(screen.getByText("combination")).toBeInTheDocument();
      expect(screen.getByText("Open Comprehensive Skin Profile Editor")).toBeInTheDocument();
    });

    it("allows updating profile display name and timezone via PATCH /api/v1/me", async () => {
      render(
        <AuthProvider>
          <ProfilePage onNavigate={vi.fn()} />
        </AuthProvider>
      );

      // Click Edit Profile button
      const editBtn = await screen.findByRole("button", { name: /Edit user profile/i });
      fireEvent.click(editBtn);

      // Edit name and timezone
      const nameInput = screen.getByDisplayValue("Sarah Jenkins");
      fireEvent.change(nameInput, { target: { value: "Sarah Updated" } });

      const tzInput = screen.getByDisplayValue("America/New_York");
      fireEvent.change(tzInput, { target: { value: "America/Chicago" } });

      // Save
      const saveBtn = screen.getByRole("button", { name: /Save Profile Details/i });
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(profileService.updateProfile).toHaveBeenCalledWith({
          display_name: "Sarah Updated",
          timezone: "America/Chicago",
        });
      });

      expect(await screen.findByText(/Profile details updated successfully/i)).toBeInTheDocument();
    });

    it("manages ingredient sensitivities (add and delete)", async () => {
      render(
        <AuthProvider>
          <ProfilePage onNavigate={vi.fn()} />
        </AuthProvider>
      );

      // Existing sensitivities
      expect(await screen.findByText("Fragrance")).toBeInTheDocument();
      expect(screen.getByText("Denatured Alcohol")).toBeInTheDocument();

      // Add a new sensitivity
      const ingredientInput = screen.getByPlaceholderText(/Add ingredient/i);
      fireEvent.change(ingredientInput, { target: { value: "Niacinamide" } });

      const addBtn = screen.getByRole("button", { name: /Add sensitivity/i });
      fireEvent.click(addBtn);

      await waitFor(() => {
        expect(profileService.addSensitivity).toHaveBeenCalledWith({
          ingredient_name: "Niacinamide",
          severity: "moderate",
        });
      });

      // Delete an existing sensitivity
      const deleteFragranceBtn = screen.getByLabelText(/Remove sensitivity for Fragrance/i);
      fireEvent.click(deleteFragranceBtn);

      await waitFor(() => {
        expect(profileService.deleteSensitivity).toHaveBeenCalledWith("sens-1");
      });
    });

    it("handles privacy consent toggling with plain-language explanation of impact", async () => {
      render(
        <AuthProvider>
          <ProfilePage onNavigate={vi.fn()} />
        </AuthProvider>
      );

      // Facial analysis consent section
      expect(await screen.findByText(/Facial Scan Privacy Consent/i)).toBeInTheDocument();
      expect(screen.getByText("Granted")).toBeInTheDocument();

      // Plain language explanation that past scans remain until deleted
      expect(
        screen.getByText(/Revoking consent prevents future scan submissions/i)
      ).toBeInTheDocument();

      // Revoke consent
      const revokeBtn = screen.getByRole("button", { name: /Revoke facial scan consent/i });
      fireEvent.click(revokeBtn);

      await waitFor(() => {
        expect(profileService.updateConsent).toHaveBeenCalledWith(
          FACIAL_SCAN_CONSENT_PURPOSE,
          expect.objectContaining({ is_granted: false })
        );
      });

      expect(await screen.findByText("Revoked")).toBeInTheDocument();
    });

    it("displays reaction history and opens reaction modal", async () => {
      render(
        <AuthProvider>
          <ProfilePage onNavigate={vi.fn()} />
        </AuthProvider>
      );

      // Verify reaction history is rendered
      expect(await screen.findByText("Custom Care Calming Recovery Toner")).toBeInTheDocument();
      expect(screen.getByText(/Stung on cheeks immediately after applying/i)).toBeInTheDocument();

      // Clicking 'Log Reaction' opens ProductReactionModal
      const logReactionBtn = screen.getByRole("button", { name: /Report product reaction/i });
      fireEvent.click(logReactionBtn);

      expect(await screen.findByText("Report Product Reaction")).toBeInTheDocument();
    });

    it("truthfully discloses data export as in development without rendering a fake button", async () => {
      render(
        <AuthProvider>
          <ProfilePage onNavigate={vi.fn()} />
        </AuthProvider>
      );

      // Data Portability card should explain export is in development
      expect(await screen.findByText(/Data Governance & Export/i)).toBeInTheDocument();
      expect(
        screen.getByText(/Comprehensive data archive export/i)
      ).toBeInTheDocument();

      // No fake "Export My Data" or "Download Data" button
      expect(screen.queryByRole("button", { name: /export my data/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /download data/i })).not.toBeInTheDocument();
    });

    it("requires typing DELETE before executing permanent account deletion (DELETE /api/v1/me)", async () => {
      const logoutSpy = vi.spyOn(authService, "logout").mockResolvedValue(undefined as any);

      render(
        <AuthProvider>
          <ProfilePage onNavigate={vi.fn()} />
        </AuthProvider>
      );

      // Click Delete Account trigger
      const deleteTrigger = await screen.findByRole("button", { name: /Open delete account confirmation modal/i });
      fireEvent.click(deleteTrigger);

      // Modal appears
      expect(
        screen.getByText(/This action is irreversible. All stored facial photos/i)
      ).toBeInTheDocument();

      const confirmDeleteBtn = screen.getByRole("button", {
        name: /Confirm Delete/i,
      });

      // Disabled initially
      expect(confirmDeleteBtn).toBeDisabled();

      // Type DELETE
      const confirmInput = screen.getByLabelText(/Confirm deletion by typing DELETE/i);
      fireEvent.change(confirmInput, { target: { value: "DELETE" } });

      expect(confirmDeleteBtn).not.toBeDisabled();

      // Submit deletion
      fireEvent.click(confirmDeleteBtn);

      await waitFor(() => {
        expect(profileService.deleteAccount).toHaveBeenCalled();
        expect(logoutSpy).toHaveBeenCalled();
      });
    });

    it("supports single-session logout", async () => {
      const logoutSpy = vi.spyOn(authService, "logout").mockResolvedValue(undefined as any);

      render(
        <AuthProvider>
          <ProfilePage onNavigate={vi.fn()} />
        </AuthProvider>
      );

      const logoutBtn = await screen.findByRole("button", { name: /^Sign Out$/i });
      fireEvent.click(logoutBtn);

      await waitFor(() => {
        expect(logoutSpy).toHaveBeenCalled();
      });
    });

    it("supports logout-all across all devices", async () => {
      const logoutAllSpy = vi.spyOn(authService, "logoutAll").mockResolvedValue(undefined as any);

      render(
        <AuthProvider>
          <ProfilePage onNavigate={vi.fn()} />
        </AuthProvider>
      );

      const logoutAllBtn = await screen.findByRole("button", { name: /Sign Out From All Devices/i });
      fireEvent.click(logoutAllBtn);

      await waitFor(() => {
        expect(logoutAllSpy).toHaveBeenCalled();
      });
    });
  });

  describe("Shelf Item Detail Integration with Reaction Reporting", () => {
    it("allows logging a reaction directly from shelf item detail modal", async () => {
      render(<ShelfPage onNavigate={vi.fn()} />);

      // Click on first item
      const itemCard = await screen.findByText("Hydrating Cleanser");
      fireEvent.click(itemCard);

      // Detail modal opens, click 'Log Reaction'
      const logReactionBtn = await screen.findByRole("button", { name: /Log Reaction/i });
      fireEvent.click(logReactionBtn);

      // Reaction modal should be open with CeraVe Hydrating Cleanser pre-populated
      expect(await screen.findByText("Report Product Reaction")).toBeInTheDocument();
      expect(screen.getByText("CeraVe Hydrating Cleanser")).toBeInTheDocument();
    });
  });
});
