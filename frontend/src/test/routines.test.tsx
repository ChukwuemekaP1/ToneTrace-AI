import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { RoutinesPage } from "@/pages/RoutinesPage";
import { routineService, isValidUuid } from "@/api/routines";
import { shelfService } from "@/api/shelf";
import {
  RoutineResponse,
  RoutineCompletionResponse,
  ReminderPreferenceResponse,
  ShelfItemResponse,
  ApiError,
} from "@/api/types";

describe("Routines & Reminders Management (/routines) (Phase 7)", () => {
  const mockRoutine1: RoutineResponse = {
    id: "r1111111-2222-3333-4444-555555555555",
    user_id: "u1111111-2222-3333-4444-555555555555",
    name: "Morning Barrier Defense",
    description: "Daily morning protective protocol",
    time_of_day: "morning",
    frequency: "daily",
    days_of_week: [0, 1, 2, 3, 4, 5, 6],
    preferred_local_time: "08:00",
    user_timezone: "America/New_York",
    is_active: true,
    version: 1,
    total_completions: 12,
    created_at: "2026-10-01T08:00:00Z",
    updated_at: "2026-10-01T08:00:00Z",
    steps: [
      {
        id: "s1111111-2222-3333-4444-555555555555",
        routine_id: "r1111111-2222-3333-4444-555555555555",
        user_product_id: "a1111111-2222-3333-4444-555555555555",
        step_order: 1,
        time_of_day: "morning",
        step_label: "Hydrating Gentle Cleanser",
        custom_instruction: "Gently massage on damp skin for 60s",
        frequency: "every_session",
        wait_time_seconds: null,
        is_active: true,
        created_at: "2026-10-01T08:00:00Z",
        updated_at: "2026-10-01T08:00:00Z",
      },
      {
        id: "s2222222-3333-4444-5555-666666666666",
        routine_id: "r1111111-2222-3333-4444-555555555555",
        user_product_id: null,
        step_order: 2,
        time_of_day: "morning",
        step_label: "Centella Soothing Serum",
        custom_instruction: "Pat 3-4 drops until absorbed",
        frequency: "every_session",
        wait_time_seconds: 120,
        is_active: true,
        created_at: "2026-10-01T08:00:00Z",
        updated_at: "2026-10-01T08:00:00Z",
      },
    ],
  };

  const mockRoutine2: RoutineResponse = {
    id: "r2222222-3333-4444-5555-666666666666",
    user_id: "u1111111-2222-3333-4444-555555555555",
    name: "Evening Retinol Renewal",
    description: "Nightly renewal protocol",
    time_of_day: "evening",
    frequency: "every_other_day",
    days_of_week: [1, 3, 5],
    preferred_local_time: "21:30",
    user_timezone: "America/New_York",
    is_active: true,
    version: 2,
    total_completions: 6,
    created_at: "2026-10-05T19:00:00Z",
    updated_at: "2026-10-10T19:00:00Z",
    steps: [
      {
        id: "s3333333-4444-5555-6666-777777777777",
        routine_id: "r2222222-3333-4444-5555-666666666666",
        user_product_id: null,
        step_order: 1,
        time_of_day: "evening",
        step_label: "Lipid Replenishing Oil Cleanser",
        custom_instruction: "Melt sunscreen and makeup",
        frequency: "every_session",
        wait_time_seconds: null,
        is_active: true,
        created_at: "2026-10-05T19:00:00Z",
        updated_at: "2026-10-05T19:00:00Z",
      },
    ],
  };

  const mockReminders: ReminderPreferenceResponse = {
    id: "rem-1",
    user_id: "u1111111-2222-3333-4444-555555555555",
    reminders_enabled: true,
    preferred_channels: ["in_app"],
    morning_reminder_enabled: true,
    morning_reminder_time: "08:15",
    evening_reminder_enabled: true,
    evening_reminder_time: "21:45",
    quiet_hours_enabled: true,
    quiet_hours_start: "22:30",
    quiet_hours_end: "07:00",
    active_notification_provider: "local_test_recorder",
    is_simulated_delivery: true,
    effective_timezone: "America/New_York",
    created_at: "2026-10-01T08:00:00Z",
    updated_at: "2026-10-01T08:00:00Z",
  };

  const mockShelfProduct: ShelfItemResponse = {
    id: "a1111111-2222-3333-4444-555555555555",
    user_id: "u1111111-2222-3333-4444-555555555555",
    product_id: "p1111111-2222-3333-4444-555555555555",
    variant_id: null,
    ocr_job_id: null,
    is_custom: false,
    display_name: "Centella Soothing Cream",
    display_brand: "SkinScience",
    display_category: "Moisturizer",
    catalogue_status: "catalogue_linked",
    ingredient_data_status: "complete",
    ingredient_names: ["Centella Asiatica Leaf Water", "Glycerin"],
    sensitivity_alerts: [],
    incomplete_ingredient_warning: null,
    status: "in_use",
    opened_at: "2026-10-01T08:00:00Z",
    expires_at: null,
    purchase_price_minor_units: 2400,
    purchase_currency: "USD",
    private_notes: "Morning hydration only.",
    is_public: false,
    reactions: [],
    created_at: "2026-10-01T08:00:00Z",
    updated_at: "2026-10-01T08:00:00Z",
  };

  const mockCompletion: RoutineCompletionResponse = {
    id: "c1111111-2222-3333-4444-555555555555",
    routine_id: "r1111111-2222-3333-4444-555555555555",
    user_id: "u1111111-2222-3333-4444-555555555555",
    routine_name_snapshot: "Morning Barrier Defense",
    routine_version_snapshot: 1,
    time_of_day_snapshot: "morning",
    status: "completed",
    completed_at: "2026-10-28T08:05:00Z",
    local_date: "2026-10-28",
    local_time: "08:05",
    user_timezone: "America/New_York",
    notes: "Skin felt comfortable and calm.",
    completed_steps_snapshot: [
      {
        step_order: 1,
        step_label: "Hydrating Gentle Cleanser",
        status: "completed",
      },
    ],
    created_at: "2026-10-28T08:05:00Z",
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe("UUID Validation Helper", () => {
    it("validates canonical UUID formats correctly", () => {
      expect(isValidUuid("e1111111-2222-3333-4444-555555555555")).toBe(true);
      expect(isValidUuid("12345678-1234-1234-1234-1234567890ab")).toBe(true);
      expect(isValidUuid("r1111111-2222-3333-4444-555555555555")).toBe(false);
      expect(isValidUuid("invalid-uuid-format")).toBe(false);
      expect(isValidUuid("")).toBe(false);
    });
  });

  describe("Routines Listing & Slot Filtering", () => {
    it("loads and displays routines with backend-ordered steps and reminder status", async () => {
      vi.spyOn(routineService, "listRoutines").mockResolvedValue({
        items: [mockRoutine1, mockRoutine2],
        total: 2,
        page: 1,
        page_size: 50,
      });
      vi.spyOn(routineService, "getReminders").mockResolvedValue(mockReminders);
      vi.spyOn(shelfService, "listShelfItems").mockResolvedValue({
        items: [mockShelfProduct],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
      });

      render(<RoutinesPage onNavigate={vi.fn()} />);

      expect(await screen.findByText("Morning Barrier Defense")).toBeInTheDocument();
      expect(screen.getByText("Evening Retinol Renewal")).toBeInTheDocument();
      expect(screen.getByText("Hydrating Gentle Cleanser")).toBeInTheDocument();
      expect(screen.getByText("Centella Soothing Serum")).toBeInTheDocument();

      // Reminder banner text
      expect(
        screen.getByText(/Scheduled Reminders: Morning 08:15 • Evening 21:45 \(America\/New_York\)/i)
      ).toBeInTheDocument();
    });

    it("filters routines by supported time-of-day slots accurately", async () => {
      const listSpy = vi.spyOn(routineService, "listRoutines").mockResolvedValue({
        items: [mockRoutine1],
        total: 1,
        page: 1,
        page_size: 50,
      });
      vi.spyOn(routineService, "getReminders").mockResolvedValue(mockReminders);
      vi.spyOn(shelfService, "listShelfItems").mockResolvedValue({
        items: [],
        total: 0,
        page: 1,
        page_size: 50,
        total_pages: 0,
      });

      render(<RoutinesPage onNavigate={vi.fn()} />);

      await screen.findByText("Morning Barrier Defense");

      const eveningFilter = screen.getByRole("button", { name: /Evening Routines/i });
      fireEvent.click(eveningFilter);

      await waitFor(() => {
        expect(listSpy).toHaveBeenCalledWith({ time_of_day: "evening" });
      });
    });

    it("renders empty state with call to action when no routines exist", async () => {
      vi.spyOn(routineService, "listRoutines").mockResolvedValue({
        items: [],
        total: 0,
        page: 1,
        page_size: 50,
      });
      vi.spyOn(routineService, "getReminders").mockResolvedValue(mockReminders);
      vi.spyOn(shelfService, "listShelfItems").mockResolvedValue({
        items: [],
        total: 0,
        page: 1,
        page_size: 50,
        total_pages: 0,
      });

      render(<RoutinesPage onNavigate={vi.fn()} />);

      expect(await screen.findByText("No skincare routines yet")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Create First Routine" })).toBeInTheDocument();
    });

    it("displays error banner with retry button on API failure", async () => {
      vi.spyOn(routineService, "listRoutines").mockRejectedValue(
        new ApiError("Failed to fetch user routines.", 500)
      );
      vi.spyOn(routineService, "getReminders").mockResolvedValue(mockReminders);
      vi.spyOn(shelfService, "listShelfItems").mockResolvedValue({
        items: [],
        total: 0,
        page: 1,
        page_size: 50,
        total_pages: 0,
      });

      render(<RoutinesPage onNavigate={vi.fn()} />);

      expect(await screen.findByText("Failed to fetch user routines.")).toBeInTheDocument();

      const retryBtn = screen.getByRole("button", { name: "Retry" });
      expect(retryBtn).toBeInTheDocument();
    });
  });

  describe("Routine Completion Tracking", () => {
    it("records completion with server timestamp, avoids duplicate submit, and shows server confirmation", async () => {
      vi.spyOn(routineService, "listRoutines").mockResolvedValue({
        items: [mockRoutine1],
        total: 1,
        page: 1,
        page_size: 50,
      });
      vi.spyOn(routineService, "getReminders").mockResolvedValue(mockReminders);
      vi.spyOn(shelfService, "listShelfItems").mockResolvedValue({
        items: [],
        total: 0,
        page: 1,
        page_size: 50,
        total_pages: 0,
      });

      const completeSpy = vi
        .spyOn(routineService, "recordCompletion")
        .mockResolvedValue(mockCompletion);

      render(<RoutinesPage onNavigate={vi.fn()} />);

      await screen.findByText("Morning Barrier Defense");

      const completeBtn = screen.getByRole("button", { name: /Complete Routine/i });
      fireEvent.click(completeBtn);

      // Verify button goes into submitting state
      expect(completeBtn).toBeDisabled();

      await waitFor(() => {
        expect(completeSpy).toHaveBeenCalledWith(
          mockRoutine1.id,
          expect.objectContaining({
            status: "completed",
            idempotency_key: expect.stringMatching(/^comp_/),
          })
        );
      });

      // Confirmation banner reflects real server values
      expect(
        await screen.findByText(/Completed session recorded for 2026-10-28 at 08:05 \(America\/New_York\)/i)
      ).toBeInTheDocument();
    });

    it("opens completion logs modal and displays immutable server history without mock streak calculation", async () => {
      vi.spyOn(routineService, "listRoutines").mockResolvedValue({
        items: [mockRoutine1],
        total: 1,
        page: 1,
        page_size: 50,
      });
      vi.spyOn(routineService, "getReminders").mockResolvedValue(mockReminders);
      vi.spyOn(shelfService, "listShelfItems").mockResolvedValue({
        items: [],
        total: 0,
        page: 1,
        page_size: 50,
        total_pages: 0,
      });

      const historySpy = vi.spyOn(routineService, "listCompletions").mockResolvedValue({
        items: [mockCompletion],
        total: 1,
        page: 1,
        page_size: 30,
      });

      render(<RoutinesPage onNavigate={vi.fn()} />);

      await screen.findByText("Morning Barrier Defense");

      const viewLogsBtn = screen.getByRole("button", { name: /View Logs/i });
      fireEvent.click(viewLogsBtn);

      await waitFor(() => {
        expect(historySpy).toHaveBeenCalledWith(mockRoutine1.id, 1, 20);
      });

      expect(await screen.findByText("Completion History")).toBeInTheDocument();
      expect(screen.getByText("2026-10-28 at 08:05")).toBeInTheDocument();
      expect(screen.getByText(/Timezone: America\/New_York • Version #1/i)).toBeInTheDocument();
      expect(screen.getByText("Skin felt comfortable and calm.")).toBeInTheDocument();

      // Close modal
      const closeBtn = screen.getByRole("button", { name: "Close History" });
      fireEvent.click(closeBtn);

      await waitFor(() => {
        expect(screen.queryByText("Completion History")).not.toBeInTheDocument();
      });
    });
  });

  describe("Routine Builder (Create, Edit, Step Reordering & Shelf Linking)", () => {
    it("creates a new routine with steps and links to shelf product", async () => {
      vi.spyOn(routineService, "listRoutines").mockResolvedValue({
        items: [],
        total: 0,
        page: 1,
        page_size: 50,
      });
      vi.spyOn(routineService, "getReminders").mockResolvedValue(mockReminders);
      vi.spyOn(shelfService, "listShelfItems").mockResolvedValue({
        items: [mockShelfProduct],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
      });

      const createSpy = vi.spyOn(routineService, "createRoutine").mockResolvedValue(mockRoutine1);

      render(<RoutinesPage onNavigate={vi.fn()} />);

      const newRoutineBtn = await screen.findByRole("button", { name: /New Routine/i });
      fireEvent.click(newRoutineBtn);

      expect(await screen.findByText("Build New Routine")).toBeInTheDocument();

      // Fill form
      fireEvent.change(screen.getByPlaceholderText("e.g. Morning Barrier Defense"), {
        target: { value: "Evening Hydration" },
      });

      // Step #1 is already present by default; link it to shelf product
      expect(screen.getByText("Step #1")).toBeInTheDocument();
      const shelfSelect = screen.getByLabelText("Step 1 shelf link");
      fireEvent.change(shelfSelect, {
        target: { value: mockShelfProduct.id },
      });

      // Submit
      const saveBtn = screen.getByRole("button", { name: "Save Routine" });
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(createSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            name: "Evening Hydration",
            steps: expect.arrayContaining([
              expect.objectContaining({
                step_order: 1,
                user_product_id: mockShelfProduct.id,
              }),
            ]),
          })
        );
      });
    });

    it("edits an existing routine and reorders steps (move down / move up)", async () => {
      vi.spyOn(routineService, "listRoutines").mockResolvedValue({
        items: [mockRoutine1],
        total: 1,
        page: 1,
        page_size: 50,
      });
      vi.spyOn(routineService, "getReminders").mockResolvedValue(mockReminders);
      vi.spyOn(shelfService, "listShelfItems").mockResolvedValue({
        items: [mockShelfProduct],
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
      });

      const updateSpy = vi.spyOn(routineService, "updateRoutine").mockResolvedValue({
        ...mockRoutine1,
        version: 2,
      });

      render(<RoutinesPage onNavigate={vi.fn()} />);

      await screen.findByText("Morning Barrier Defense");

      // Click Edit button
      const editBtn = screen.getByRole("button", {
        name: `Edit routine ${mockRoutine1.name}`,
      });
      fireEvent.click(editBtn);

      expect(await screen.findByText("Edit Skincare Routine")).toBeInTheDocument();

      // Move Step 1 down
      const moveDownBtn = screen.getByLabelText("Move step 1 down");
      fireEvent.click(moveDownBtn);

      // Save
      const saveBtn = screen.getByRole("button", { name: "Save Routine" });
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(updateSpy).toHaveBeenCalledWith(
          mockRoutine1.id,
          expect.objectContaining({
            steps: expect.arrayContaining([
              expect.objectContaining({ step_order: 1, step_label: "Centella Soothing Serum" }),
              expect.objectContaining({ step_order: 2, step_label: "Hydrating Gentle Cleanser" }),
            ]),
          })
        );
      });
    });

    it("deletes a routine with confirmation dialog and respects cancellation", async () => {
      vi.spyOn(routineService, "listRoutines").mockResolvedValue({
        items: [mockRoutine1],
        total: 1,
        page: 1,
        page_size: 50,
      });
      vi.spyOn(routineService, "getReminders").mockResolvedValue(mockReminders);
      vi.spyOn(shelfService, "listShelfItems").mockResolvedValue({
        items: [],
        total: 0,
        page: 1,
        page_size: 50,
        total_pages: 0,
      });

      const deleteSpy = vi
        .spyOn(routineService, "deleteRoutine")
        .mockResolvedValue({ status: "deleted", routine_id: mockRoutine1.id });

      render(<RoutinesPage onNavigate={vi.fn()} />);

      await screen.findByText("Morning Barrier Defense");

      const trashBtn = screen.getByRole("button", {
        name: `Delete routine ${mockRoutine1.name}`,
      });
      fireEvent.click(trashBtn);

      expect(await screen.findByText("Delete Skincare Routine?")).toBeInTheDocument();

      // Cancel button first
      const cancelBtn = screen.getByRole("button", { name: "Keep Routine" });
      fireEvent.click(cancelBtn);

      expect(screen.queryByText("Delete Skincare Routine?")).not.toBeInTheDocument();
      expect(deleteSpy).not.toHaveBeenCalled();

      // Open again and confirm
      fireEvent.click(trashBtn);
      const confirmDeleteBtn = await screen.findByRole("button", { name: "Yes, Delete" });
      fireEvent.click(confirmDeleteBtn);

      await waitFor(() => {
        expect(deleteSpy).toHaveBeenCalledWith(mockRoutine1.id);
      });
    });
  });

  describe("Reminder Preferences & Notification Transparency", () => {
    it("displays delivery transparency notice for simulated provider and saves updated times", async () => {
      vi.spyOn(routineService, "listRoutines").mockResolvedValue({
        items: [mockRoutine1],
        total: 1,
        page: 1,
        page_size: 50,
      });
      vi.spyOn(routineService, "getReminders").mockResolvedValue(mockReminders);
      vi.spyOn(shelfService, "listShelfItems").mockResolvedValue({
        items: [],
        total: 0,
        page: 1,
        page_size: 50,
        total_pages: 0,
      });

      const updateRemindersSpy = vi
        .spyOn(routineService, "updateReminders")
        .mockResolvedValue({
          ...mockReminders,
          morning_reminder_time: "07:30",
        });

      render(<RoutinesPage onNavigate={vi.fn()} />);

      const settingsBtn = await screen.findByRole("button", { name: "Settings" });
      fireEvent.click(settingsBtn);

      expect(await screen.findByText("Reminder Preferences")).toBeInTheDocument();

      // Transparency notice
      expect(screen.getByText("Notification Delivery Status")).toBeInTheDocument();
      expect(screen.getByText("local_test_recorder")).toBeInTheDocument();

      // Save preferences
      const savePrefsBtn = screen.getByRole("button", { name: "Save Preferences" });
      fireEvent.click(savePrefsBtn);

      await waitFor(() => {
        expect(updateRemindersSpy).toHaveBeenCalled();
      });

      expect(
        await screen.findByText("Reminder preferences saved to backend.")
      ).toBeInTheDocument();
    });
  });
});
