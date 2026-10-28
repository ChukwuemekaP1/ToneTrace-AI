import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { DashboardPage } from "@/pages/DashboardPage";
import { AuthProvider } from "@/context/AuthContext";
import { profileService } from "@/api/profile";
import { dashboardService } from "@/api/dashboard";
import { authService } from "@/api/auth";
import { tokenStore } from "@/api/token-store";
import { ApiError } from "@/api/types";

describe("Main Dashboard Integration (/)", () => {
  const mockUser = {
    id: "user-1",
    email: "clara@tonetrace.test",
    account_status: "active",
    is_email_verified: true,
    created_at: "2026-10-28T08:00:00Z",
    updated_at: "2026-10-28T08:00:00Z",
  };

  const mockProfileSummary = {
    user: mockUser,
    profile: {
      id: "prof-1",
      user_id: "user-1",
      display_name: "Clara",
      timezone: "America/New_York",
      created_at: "2026-10-28T08:00:00Z",
      updated_at: "2026-10-28T08:00:00Z",
    },
    skin_profile: {
      id: "sp-1",
      user_id: "user-1",
      skin_type: "combination",
      skin_concerns: ["pores", "redness"],
      skin_goals: ["barrier_repair"],
      created_at: "2026-10-28T08:00:00Z",
      updated_at: "2026-10-28T08:00:00Z",
    },
    sensitivities: [
      { id: "s-1", ingredient_name: "Fragrance", severity: "high" },
      { id: "s-2", ingredient_name: "Denatured Alcohol", severity: "moderate" },
    ],
    preferences: null,
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    dashboardService.invalidateCache();

    // Default auth session
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
  });

  it("complete onboarding: renders personalized greeting, configured skin type, and concerns", async () => {
    vi.spyOn(dashboardService, "getRoutines").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    vi.spyOn(dashboardService, "getReminders").mockResolvedValue(null as any);
    vi.spyOn(dashboardService, "getRecentScan").mockResolvedValue(null);
    vi.spyOn(dashboardService, "getSkinStory").mockResolvedValue(null);
    vi.spyOn(dashboardService, "getDiscoveryFeed").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 4,
      total_pages: 0,
      search_backend_used: "postgresql_catalogue",
      rule_engine_version: "1.0",
    });

    const navigateMock = vi.fn();
    render(
      <AuthProvider>
        <DashboardPage onNavigate={navigateMock} />
      </AuthProvider>
    );

    // Displays returned display name in greeting
    expect(await screen.findByText(/clara/i)).toBeInTheDocument();

    // Displays biological skin type and avoided sensitivities
    expect(await screen.findByText("combination")).toBeInTheDocument();
    expect(screen.getByText(/2 ingredients/i)).toBeInTheDocument();
    expect(screen.getByText("pores")).toBeInTheDocument();
    expect(screen.getByText("redness")).toBeInTheDocument();

    // Truthful disclosure is present
    expect(
      screen.getByText(/no composite health score is computed/i)
    ).toBeInTheDocument();

    // No incomplete onboarding banner shown
    expect(screen.queryByText(/skin profile incomplete/i)).not.toBeInTheDocument();
  });

  it("incomplete onboarding: renders calm alert banner with link to onboarding", async () => {
    vi.spyOn(profileService, "getSkinProfile").mockResolvedValue({
      id: "sp-empty",
      user_id: "user-1",
      skin_type: null,
      skin_concerns: [],
      skin_goals: [],
      created_at: "2026-10-28T08:00:00Z",
      updated_at: "2026-10-28T08:00:00Z",
    });
    vi.spyOn(dashboardService, "getRoutines").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    vi.spyOn(dashboardService, "getReminders").mockResolvedValue(null as any);
    vi.spyOn(dashboardService, "getRecentScan").mockResolvedValue(null);
    vi.spyOn(dashboardService, "getSkinStory").mockResolvedValue(null);
    vi.spyOn(dashboardService, "getDiscoveryFeed").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 4,
      total_pages: 0,
      search_backend_used: "postgresql_catalogue",
      rule_engine_version: "1.0",
    });

    const navigateMock = vi.fn();
    render(
      <AuthProvider>
        <DashboardPage onNavigate={navigateMock} />
      </AuthProvider>
    );

    expect(await screen.findByText(/skin profile incomplete/i)).toBeInTheDocument();

    const completeBtn = screen.getByRole("button", { name: /complete/i });
    fireEvent.click(completeBtn);
    expect(navigateMock).toHaveBeenCalledWith("/onboarding");
  });

  it("empty routine: displays helpful empty state with create routine action", async () => {
    vi.spyOn(dashboardService, "getRoutines").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    vi.spyOn(dashboardService, "getReminders").mockResolvedValue({
      id: "rem-1",
      user_id: "user-1",
      reminders_enabled: false,
      preferred_channels: ["in_app"],
      morning_reminder_enabled: true,
      morning_reminder_time: "08:00",
      evening_reminder_enabled: true,
      evening_reminder_time: "21:00",
      quiet_hours_enabled: true,
      quiet_hours_start: "22:30",
      quiet_hours_end: "07:00",
      effective_timezone: "America/New_York",
      active_notification_provider: "local_test_recorder",
      is_simulated_delivery: true,
      created_at: "2026-10-28T08:00:00Z",
      updated_at: "2026-10-28T08:00:00Z",
    });
    vi.spyOn(dashboardService, "getRecentScan").mockResolvedValue(null);
    vi.spyOn(dashboardService, "getSkinStory").mockResolvedValue(null);
    vi.spyOn(dashboardService, "getDiscoveryFeed").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 4,
      total_pages: 0,
      search_backend_used: "postgresql_catalogue",
      rule_engine_version: "1.0",
    });

    const navigateMock = vi.fn();
    render(
      <AuthProvider>
        <DashboardPage onNavigate={navigateMock} />
      </AuthProvider>
    );

    expect(await screen.findByText(/no routines set up yet/i)).toBeInTheDocument();
    expect(screen.getByText(/scheduled reminders paused/i)).toBeInTheDocument();

    const createRoutineBtn = screen.getByRole("button", { name: /create routine/i });
    fireEvent.click(createRoutineBtn);
    expect(navigateMock).toHaveBeenCalledWith("/routines");
  });

  it("no scans: displays truthful alternative without fabricated scores or progress bars", async () => {
    vi.spyOn(dashboardService, "getRoutines").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    vi.spyOn(dashboardService, "getReminders").mockResolvedValue(null as any);
    vi.spyOn(dashboardService, "getRecentScan").mockResolvedValue(null);
    vi.spyOn(dashboardService, "getSkinStory").mockResolvedValue(null);
    vi.spyOn(dashboardService, "getDiscoveryFeed").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 4,
      total_pages: 0,
      search_backend_used: "postgresql_catalogue",
      rule_engine_version: "1.0",
    });

    const navigateMock = vi.fn();
    render(
      <AuthProvider>
        <DashboardPage onNavigate={navigateMock} />
      </AuthProvider>
    );

    expect(
      await screen.findByText(/no skin story entries yet/i)
    ).toBeInTheDocument();

    // Confirm truthful guardrail note is always present
    expect(screen.getByText(/no composite health score is computed/i)).toBeInTheDocument();

    const trackBtn = screen.getByRole("button", { name: /^track skin$/i });
    fireEvent.click(trackBtn);
    expect(navigateMock).toHaveBeenCalledWith("/skin/track");
  });

  it("empty discovery: renders discovery shortcut instead of fake product recommendations", async () => {
    vi.spyOn(dashboardService, "getRoutines").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    vi.spyOn(dashboardService, "getReminders").mockResolvedValue(null as any);
    vi.spyOn(dashboardService, "getRecentScan").mockResolvedValue(null);
    vi.spyOn(dashboardService, "getSkinStory").mockResolvedValue(null);
    vi.spyOn(dashboardService, "getDiscoveryFeed").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 4,
      total_pages: 0,
      search_backend_used: "postgresql_catalogue",
      rule_engine_version: "1.0",
    });

    const navigateMock = vi.fn();
    render(
      <AuthProvider>
        <DashboardPage onNavigate={navigateMock} />
      </AuthProvider>
    );

    expect(
      await screen.findByText(/search thousands of verified cosmetic products/i)
    ).toBeInTheDocument();
    expect(screen.queryByText(/recommended for you/i)).not.toBeInTheDocument();

    const exploreBtn = screen.getByRole("button", { name: /^explore products$/i });
    fireEvent.click(exploreBtn);
    expect(navigateMock).toHaveBeenCalledWith("/explore");
  });

  it("populated state: renders routines preview, reminder times, recent scan, and discovery items", async () => {
    vi.spyOn(dashboardService, "getRoutines").mockResolvedValue({
      items: [
        {
          id: "r-morning",
          user_id: "user-1",
          name: "Morning Barrier Defense",
          description: "Gentle cleanse and SPF",
          time_of_day: "morning",
          frequency: "daily",
          days_of_week: [0, 1, 2, 3, 4, 5, 6],
          preferred_local_time: "08:15",
          user_timezone: "America/New_York",
          is_active: true,
          version: 1,
          steps: [
            {
              id: "step-1",
              routine_id: "r-morning",
              step_order: 1,
              time_of_day: "morning",
              step_label: "Gentle Cleanser",
              frequency: "daily",
              is_active: true,
              created_at: "2026-10-28T08:00:00Z",
              updated_at: "2026-10-28T08:00:00Z",
            },
          ],
          total_completions: 14,
          created_at: "2026-10-28T08:00:00Z",
          updated_at: "2026-10-28T08:00:00Z",
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });
    vi.spyOn(dashboardService, "getReminders").mockResolvedValue({
      id: "rem-1",
      user_id: "user-1",
      reminders_enabled: true,
      preferred_channels: ["in_app"],
      morning_reminder_enabled: true,
      morning_reminder_time: "08:15",
      evening_reminder_enabled: true,
      evening_reminder_time: "21:30",
      quiet_hours_enabled: true,
      quiet_hours_start: "22:30",
      quiet_hours_end: "07:00",
      effective_timezone: "America/New_York",
      active_notification_provider: "local_test_recorder",
      is_simulated_delivery: true,
      created_at: "2026-10-28T08:00:00Z",
      updated_at: "2026-10-28T08:00:00Z",
    });
    vi.spyOn(dashboardService, "getRecentScan").mockResolvedValue({
      id: "scan-1",
      user_id: "user-1",
      provider: "mock",
      status: "succeeded",
      created_at: "2026-10-28T09:00:00Z",
      lighting_condition: "natural_daylight",
      camera_angle: "frontal",
      cosmetics_worn: false,
      observations: [],
      media_count: 1,
    });
    vi.spyOn(dashboardService, "getSkinStory").mockResolvedValue({
      user_id: "user-1",
      generated_at: "2026-10-28T09:00:00Z",
      total_succeeded_scans: 3,
      metric_timelines: [],
      recent_journal_entries: [],
      capture_variability_notice: "Notice",
      non_diagnostic_disclaimer: "Disclaimer",
      pigmentation_and_causation_guardrail: "Guardrail",
    });
    vi.spyOn(dashboardService, "getDiscoveryFeed").mockResolvedValue({
      items: [
        {
          product_id: "prod-101",
          source_id: "obf:123456",
          name: "Ceramide Moisture Cream",
          brand: "CeraDerm",
          category: "Moisturizer",
          ingredient_count: 18,
          ingredient_data_status: "complete",
          on_user_shelf: false,
          recommendation: {
            is_suitable: true,
            decision: "suitable_for_skin_profile",
            summary: "Matches barrier repair goal",
          },
        },
      ],
      total: 1,
      page: 1,
      page_size: 4,
      total_pages: 1,
      search_backend_used: "postgresql_catalogue",
      rule_engine_version: "1.0",
    });

    render(
      <AuthProvider>
        <DashboardPage onNavigate={vi.fn()} />
      </AuthProvider>
    );

    // Routine preview
    expect(await screen.findByText("Morning Barrier Defense")).toBeInTheDocument();
    expect(screen.getByText(/14 completed/i)).toBeInTheDocument();
    expect(screen.getByText(/reminders active \(morning: 08:15/i)).toBeInTheDocument();

    // Scan preview
    expect(screen.getByText(/natural daylight • frontal angle/i)).toBeInTheDocument();
    expect(screen.getByText(/3 longitudinal visual check-ins recorded/i)).toBeInTheDocument();

    // Discovery feed
    expect(screen.getByText("Ceramide Moisture Cream")).toBeInTheDocument();
    expect(screen.getByText(/ceraderm • moisturizer/i)).toBeInTheDocument();
    expect(screen.getByText(/suitable for skin profile/i)).toBeInTheDocument();
  });

  it("one request failure resilience: card shows retry state while other cards remain fully usable", async () => {
    // Routines endpoint fails with a network/server error
    vi.spyOn(dashboardService, "getRoutines").mockRejectedValue(
      new ApiError("Routines database connection pool timed out", 500, "DB_TIMEOUT")
    );
    vi.spyOn(dashboardService, "getReminders").mockResolvedValue(null as any);
    vi.spyOn(dashboardService, "getRecentScan").mockResolvedValue(null);
    vi.spyOn(dashboardService, "getSkinStory").mockResolvedValue(null);
    vi.spyOn(dashboardService, "getDiscoveryFeed").mockResolvedValue({
      items: [
        {
          product_id: "prod-102",
          source_id: "obf:789",
          name: "Hydrating Cleansing Foam",
          brand: "DermaPure",
          category: "Cleanser",
          ingredient_count: 12,
          ingredient_data_status: "complete",
          on_user_shelf: false,
        },
      ],
      total: 1,
      page: 1,
      page_size: 4,
      total_pages: 1,
      search_backend_used: "postgresql_catalogue",
      rule_engine_version: "1.0",
    });

    render(
      <AuthProvider>
        <DashboardPage onNavigate={vi.fn()} />
      </AuthProvider>
    );

    // Routines card shows inline retry state
    expect(
      await screen.findByText(/routines database connection pool timed out/i)
    ).toBeInTheDocument();

    // But other cards (Skin Journey, Discovery, Quick Actions) are healthy and fully usable!
    expect(screen.getByText("combination")).toBeInTheDocument();
    expect(screen.getByText("Hydrating Cleansing Foam")).toBeInTheDocument();
    expect(screen.getByText("Scan a Label")).toBeInTheDocument();

    // Clicking retry on routines card triggers reload
    const getRoutinesSpy = vi.spyOn(dashboardService, "getRoutines").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
    });

    const retryBtns = screen.getAllByRole("button", { name: /retry/i });
    fireEvent.click(retryBtns[0]);

    await waitFor(() => {
      expect(getRoutinesSpy).toHaveBeenCalled();
    });
  });

  it("stale data refresh: completing a routine invokes recordRoutineCompletion and refreshes routines", async () => {
    const routineId = "r-active-1";
    vi.spyOn(dashboardService, "getRoutines").mockResolvedValue({
      items: [
        {
          id: routineId,
          user_id: "user-1",
          name: "Morning Cleanse",
          time_of_day: "morning",
          frequency: "daily",
          days_of_week: [0, 1, 2, 3, 4, 5, 6],
          preferred_local_time: "08:00",
          user_timezone: "America/New_York",
          is_active: true,
          version: 1,
          steps: [],
          total_completions: 5,
          created_at: "2026-10-28T08:00:00Z",
          updated_at: "2026-10-28T08:00:00Z",
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });
    vi.spyOn(dashboardService, "getReminders").mockResolvedValue(null as any);
    vi.spyOn(dashboardService, "getRecentScan").mockResolvedValue(null);
    vi.spyOn(dashboardService, "getSkinStory").mockResolvedValue(null);
    vi.spyOn(dashboardService, "getDiscoveryFeed").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 4,
      total_pages: 0,
      search_backend_used: "postgresql_catalogue",
      rule_engine_version: "1.0",
    });

    const completionSpy = vi.spyOn(dashboardService, "recordRoutineCompletion").mockResolvedValue({
      id: "comp-1",
      routine_id: routineId,
      user_id: "user-1",
      routine_name_snapshot: "Morning Routine",
      routine_version_snapshot: 1,
      time_of_day_snapshot: "morning",
      completed_at: "2026-10-28T09:15:00Z",
      status: "completed",
      user_timezone: "America/New_York",
      local_date: "2026-10-28",
      local_time: "09:15",
      completed_steps_snapshot: [],
      created_at: "2026-10-28T09:15:00Z",
    });

    render(
      <AuthProvider>
        <DashboardPage onNavigate={vi.fn()} />
      </AuthProvider>
    );

    const completeBtn = await screen.findByRole("button", { name: /complete/i });
    fireEvent.click(completeBtn);

    await waitFor(() => {
      expect(completionSpy).toHaveBeenCalledWith(routineId, "morning");
    });
  });

  it("accessible navigation: profile control button and quick actions navigate correctly", async () => {
    vi.spyOn(dashboardService, "getRoutines").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    vi.spyOn(dashboardService, "getReminders").mockResolvedValue(null as any);
    vi.spyOn(dashboardService, "getRecentScan").mockResolvedValue(null);
    vi.spyOn(dashboardService, "getSkinStory").mockResolvedValue(null);
    vi.spyOn(dashboardService, "getDiscoveryFeed").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 4,
      total_pages: 0,
      search_backend_used: "postgresql_catalogue",
      rule_engine_version: "1.0",
    });

    const navigateMock = vi.fn();
    render(
      <AuthProvider>
        <DashboardPage onNavigate={navigateMock} />
      </AuthProvider>
    );

    // Profile control in header
    const profileControl = await screen.findByRole("button", { name: /open user profile/i });
    fireEvent.click(profileControl);
    expect(navigateMock).toHaveBeenCalledWith("/profile");

    // Scan a Label quick action
    const scanLabelBtn = screen.getByRole("button", { name: /scan a label/i });
    fireEvent.click(scanLabelBtn);
    expect(navigateMock).toHaveBeenCalledWith("/scan");

    // Ask AI quick action
    const askAiBtn = screen.getByRole("button", { name: /ask ai/i });
    fireEvent.click(askAiBtn);
    expect(navigateMock).toHaveBeenCalledWith("/ai/ask");
  });
});
