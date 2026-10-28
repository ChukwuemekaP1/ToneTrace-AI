import React, { useEffect, useState, useCallback } from "react";
import {
  Sparkles,
  Camera,
  Calendar,
  BookmarkCheck,
  Compass,
  MessageSquareQuote,
  Clock,
  Bell,
  BellOff,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  ChevronRight,
  ShieldCheck,
  User as UserIcon,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { dashboardService } from "@/api/dashboard";
import { profileService } from "@/api/profile";
import {
  RoutineResponse,
  ReminderPreferenceResponse,
  SkinScanResponse,
  SkinStoryResponse,
  DiscoveryProductSummaryItem,
  SkinProfileResponse,
  ApiError,
} from "@/api/types";
import { GlassCard } from "@/components/ui/GlassCard";
import { Chip } from "@/components/ui/Chip";
import { Button } from "@/components/ui/Button";

export interface DashboardPageProps {
  onNavigate: (route: string) => void;
  onNavigateTab?: (tab: "home" | "shelf" | "routines" | "profile" | "showcase") => void;
}

export const DashboardPage: React.FC<DashboardPageProps> = ({
  onNavigate,
  onNavigateTab,
}) => {
  const { user, summary } = useAuth();

  // ---------------------------------------------------------------------------
  // Card 1: Health & Journey Summary State
  // ---------------------------------------------------------------------------
  const [skinProfile, setSkinProfile] = useState<SkinProfileResponse | null>(null);
  const [localProfile, setLocalProfile] = useState<{ display_name?: string } | null>(null);
  const [sensitivitiesCount, setSensitivitiesCount] = useState<number>(0);
  const [journeyLoading, setJourneyLoading] = useState<boolean>(true);
  const [journeyError, setJourneyError] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Card 2: Routines & Reminders State
  // ---------------------------------------------------------------------------
  const [routines, setRoutines] = useState<RoutineResponse[]>([]);
  const [reminders, setReminders] = useState<ReminderPreferenceResponse | null>(null);
  const [routinesLoading, setRoutinesLoading] = useState<boolean>(true);
  const [routinesError, setRoutinesError] = useState<string | null>(null);
  const [completingRoutineId, setCompletingRoutineId] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Card 3: Recent Scan & Skin Story State
  // ---------------------------------------------------------------------------
  const [recentScan, setRecentScan] = useState<SkinScanResponse | null>(null);
  const [skinStory, setSkinStory] = useState<SkinStoryResponse | null>(null);
  const [scanLoading, setScanLoading] = useState<boolean>(true);
  const [scanError, setScanError] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Card 4: Product Discovery Feed State
  // ---------------------------------------------------------------------------
  const [discoveryProducts, setDiscoveryProducts] = useState<DiscoveryProductSummaryItem[]>([]);
  const [discoveryLoading, setDiscoveryLoading] = useState<boolean>(true);
  const [discoveryError, setDiscoveryError] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Greeting Time-of-Day Logic
  // ---------------------------------------------------------------------------
  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return "Good morning";
    if (hour < 18) return "Good afternoon";
    return "Good evening";
  };

  const displayName =
    summary?.profile?.display_name ||
    localProfile?.display_name ||
    user?.email?.split("@")[0] ||
    null;

  // ---------------------------------------------------------------------------
  // Isolated Fetchers (Each card manages its own loading, error, and retry)
  // ---------------------------------------------------------------------------

  const loadJourneyData = useCallback(async (_forceRefresh = false) => {
    setJourneyLoading(true);
    setJourneyError(null);
    try {
      const [sp, me] = await Promise.all([
        profileService.getSkinProfile().catch(() => null),
        profileService.getMe().catch(() => null),
      ]);
      setSkinProfile(sp);
      if (me) {
        if (me.profile) {
          setLocalProfile(me.profile);
        }
        if (me.sensitivities) {
          setSensitivitiesCount(me.sensitivities.length);
        }
      }
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Failed to load skin journey summary";
      setJourneyError(msg);
    } finally {
      setJourneyLoading(false);
    }
  }, []);

  const loadRoutinesData = useCallback(async (forceRefresh = false) => {
    setRoutinesLoading(true);
    setRoutinesError(null);
    try {
      const [routinesRes, remindersRes] = await Promise.all([
        dashboardService.getRoutines(forceRefresh),
        dashboardService.getReminders(forceRefresh).catch(() => null),
      ]);
      setRoutines(routinesRes.items || []);
      setReminders(remindersRes);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Failed to load routines";
      setRoutinesError(msg);
    } finally {
      setRoutinesLoading(false);
    }
  }, []);

  const loadScanData = useCallback(async (forceRefresh = false) => {
    setScanLoading(true);
    setScanError(null);
    try {
      const [scanRes, storyRes] = await Promise.all([
        dashboardService.getRecentScan(forceRefresh).catch(() => null),
        dashboardService.getSkinStory(forceRefresh).catch(() => null),
      ]);
      setRecentScan(scanRes);
      setSkinStory(storyRes);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Failed to load skin tracking history";
      setScanError(msg);
    } finally {
      setScanLoading(false);
    }
  }, []);

  const loadDiscoveryData = useCallback(async (forceRefresh = false) => {
    setDiscoveryLoading(true);
    setDiscoveryError(null);
    try {
      const res = await dashboardService.getDiscoveryFeed(forceRefresh);
      setDiscoveryProducts(res.items || []);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Failed to load discovery feed";
      setDiscoveryError(msg);
    } finally {
      setDiscoveryLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    loadJourneyData();
    loadRoutinesData();
    loadScanData();
    loadDiscoveryData();
  }, [loadJourneyData, loadRoutinesData, loadScanData, loadDiscoveryData]);

  // Handle Routine Completion Checkoff
  const handleCompleteRoutine = async (routineId: string, timeOfDay: string) => {
    setCompletingRoutineId(routineId);
    try {
      await dashboardService.recordRoutineCompletion(routineId, timeOfDay);
      // Reload routines with fresh data
      await loadRoutinesData(true);
    } catch {
      // In case of error, reload
      await loadRoutinesData(true);
    } finally {
      setCompletingRoutineId(null);
    }
  };

  // Helper to filter routines by time of day
  const morningRoutine = routines.find((r) => r.time_of_day === "morning" && r.is_active);
  const eveningRoutine = routines.find((r) => r.time_of_day === "evening" && r.is_active);

  // Check onboarding completeness
  const isOnboardingIncomplete = !skinProfile || !skinProfile.skin_type;

  return (
    <div className="space-y-4 text-left pb-10">
      {/* --------------------------------------------------------------------- */}
      {/* 1. Greeting Header with Profile Control                               */}
      {/* --------------------------------------------------------------------- */}
      <div className="flex items-start justify-between gap-3 pt-1">
        <div className="space-y-0.5">
          <h2 className="text-xl font-bold tracking-tight text-white leading-tight">
            {getGreeting()}
            {displayName ? (
              <>
                ,{" "}
                <span className="font-serif italic font-normal text-champagne">
                  {displayName}
                </span>
              </>
            ) : null}
          </h2>
          <p className="text-xs text-slate-400">
            Science-calibrated formulation checks and daily skin health companion.
          </p>
        </div>

        <button
          type="button"
          onClick={() => onNavigate("/profile")}
          aria-label="Open user profile"
          className="shrink-0 p-2.5 rounded-2xl bg-[#172027]/90 backdrop-blur-lg border border-white/12 text-slate-300 hover:text-white hover:border-emerald-500/40 transition-all shadow-glass flex items-center justify-center group"
        >
          <UserIcon className="w-4 h-4 text-emerald-400 group-hover:scale-110 transition-transform" />
        </button>
      </div>

      {/* Incomplete Onboarding Alert Banner */}
      {isOnboardingIncomplete && !journeyLoading && (
        <div className="p-3.5 rounded-2xl bg-amber-950/30 border border-amber-500/30 text-amber-200 flex items-center justify-between gap-3 shadow-glass animate-in fade-in">
          <div className="space-y-0.5">
            <div className="text-xs font-semibold flex items-center gap-1.5 text-amber-300">
              <AlertCircle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
              Skin Profile Incomplete
            </div>
            <p className="text-xxs text-amber-300/80 leading-normal">
              Select your biological skin type to calibrate formulation suitability and allergy checks.
            </p>
          </div>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => onNavigate("/onboarding")}
            className="shrink-0 text-xxs px-2.5 py-1 bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 border-amber-500/40"
          >
            Complete
          </Button>
        </div>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* 2. Health & Journey Summary Card                                      */}
      {/* --------------------------------------------------------------------- */}
      <GlassCard variant="default" className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200">
              Your Skin Journey
            </h3>
          </div>
          <button
            type="button"
            onClick={() => loadJourneyData(true)}
            aria-label="Refresh journey data"
            className="text-slate-400 hover:text-slate-200 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${journeyLoading ? "animate-spin" : ""}`} />
          </button>
        </div>

        {journeyError ? (
          <div className="p-3 rounded-xl bg-rose-950/30 border border-rose-500/30 text-rose-300 text-xs flex items-center justify-between">
            <span>{journeyError}</span>
            <button
              type="button"
              onClick={() => loadJourneyData(true)}
              className="text-xxs text-rose-300 underline font-semibold ml-2 hover:text-white"
            >
              Retry
            </button>
          </div>
        ) : journeyLoading ? (
          <div className="space-y-2 py-2 animate-pulse">
            <div className="h-4 bg-white/10 rounded w-1/2"></div>
            <div className="h-3 bg-white/5 rounded w-3/4"></div>
          </div>
        ) : (
          <div className="space-y-2.5">
            {/* Real Values Display */}
            <div className="grid grid-cols-2 gap-2 text-left">
              <div className="p-2.5 rounded-xl bg-[#0C1217] border border-white/5 space-y-0.5">
                <span className="text-xxs text-slate-400">Skin Type</span>
                <div className="text-xs font-semibold text-slate-200 capitalize">
                  {skinProfile?.skin_type ? (
                    <Chip variant="verified" size="sm">
                      {skinProfile.skin_type}
                    </Chip>
                  ) : (
                    <span className="text-slate-500 italic">Not set</span>
                  )}
                </div>
              </div>

              <div className="p-2.5 rounded-xl bg-[#0C1217] border border-white/5 space-y-0.5">
                <span className="text-xxs text-slate-400">Sensitivities to Avoid</span>
                <div className="text-xs font-semibold text-slate-200">
                  {sensitivitiesCount > 0 ? (
                    <span className="text-emerald-400 font-mono">
                      {sensitivitiesCount} {sensitivitiesCount === 1 ? "ingredient" : "ingredients"}
                    </span>
                  ) : (
                    <span className="text-slate-500">None flagged</span>
                  )}
                </div>
              </div>
            </div>

            {/* Concerns Tags */}
            {skinProfile?.skin_concerns && skinProfile.skin_concerns.length > 0 && (
              <div className="space-y-1">
                <span className="text-xxs text-slate-400">Calibrated Concerns:</span>
                <div className="flex flex-wrap gap-1">
                  {skinProfile.skin_concerns.map((c) => (
                    <Chip key={c} variant="neutral" size="sm">
                      {c.replace(/_/g, " ")}
                    </Chip>
                  ))}
                </div>
              </div>
            )}

            {/* Truthful Score Guardrail Note */}
            <div className="pt-1.5 border-t border-white/5 flex items-start gap-1.5 text-xxs text-slate-400 leading-relaxed">
              <Sparkles className="w-3.5 h-3.5 text-champagne shrink-0 mt-0.5" />
              <span>
                No composite health score is computed. Surface metrics track visual observations over time without diagnosing skin conditions.
              </span>
            </div>
          </div>
        )}
      </GlassCard>

      {/* --------------------------------------------------------------------- */}
      {/* 3. Prominent Quick Actions (Focused Hierarchy)                        */}
      {/* --------------------------------------------------------------------- */}
      <div className="space-y-2">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 px-0.5">
          Quick Actions
        </h3>

        {/* Hero Actions (Primary & Secondary Hero) */}
        <div className="grid grid-cols-2 gap-2.5">
          <button
            type="button"
            onClick={() => onNavigate("/scan")}
            className="p-3.5 rounded-2xl bg-gradient-to-br from-emerald-950/60 to-emerald-900/30 border border-emerald-500/40 shadow-glow text-left hover:border-emerald-400 transition-all group flex flex-col justify-between"
          >
            <div className="w-8 h-8 rounded-xl bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400 mb-2 group-hover:scale-105 transition-transform">
              <Camera className="w-4 h-4" />
            </div>
            <div>
              <span className="text-xs font-bold text-white block">Scan a Label</span>
              <span className="text-xxs text-emerald-300/80 leading-tight block mt-0.5">
                Extract & verify ingredients
              </span>
            </div>
          </button>

          <button
            type="button"
            onClick={() => onNavigate("/skin/track")}
            className="p-3.5 rounded-2xl bg-gradient-to-br from-champagne/15 to-transparent border border-champagne/30 shadow-glass text-left hover:border-champagne/50 transition-all group flex flex-col justify-between"
          >
            <div className="w-8 h-8 rounded-xl bg-champagne/20 border border-champagne/40 flex items-center justify-center text-champagne mb-2 group-hover:scale-105 transition-transform">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <span className="text-xs font-bold text-white block">Track Skin</span>
              <span className="text-xxs text-champagne/80 leading-tight block mt-0.5">
                Log visual skin check-in
              </span>
            </div>
          </button>
        </div>

        {/* Secondary Compact Actions (2x2 Grid) */}
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => onNavigate("/ai/ask")}
            className="p-2.5 rounded-xl bg-[#172027]/70 border border-white/8 hover:border-white/20 transition-all text-left flex items-center gap-2.5 group"
          >
            <div className="w-7 h-7 rounded-lg bg-white/5 flex items-center justify-center text-slate-300 group-hover:text-emerald-400">
              <MessageSquareQuote className="w-3.5 h-3.5" />
            </div>
            <div>
              <span className="text-xs font-semibold text-slate-200 block leading-tight">Ask AI</span>
              <span className="text-xxs text-slate-400 leading-none">Grounded inquiry</span>
            </div>
          </button>

          <button
            type="button"
            onClick={() => onNavigate("/explore")}
            className="p-2.5 rounded-xl bg-[#172027]/70 border border-white/8 hover:border-white/20 transition-all text-left flex items-center gap-2.5 group"
          >
            <div className="w-7 h-7 rounded-lg bg-white/5 flex items-center justify-center text-slate-300 group-hover:text-emerald-400">
              <Compass className="w-3.5 h-3.5" />
            </div>
            <div>
              <span className="text-xs font-semibold text-slate-200 block leading-tight">Explore Products</span>
              <span className="text-xxs text-slate-400 leading-none">Catalog search</span>
            </div>
          </button>

          <button
            type="button"
            onClick={() => (onNavigateTab ? onNavigateTab("shelf") : onNavigate("/shelf"))}
            className="p-2.5 rounded-xl bg-[#172027]/70 border border-white/8 hover:border-white/20 transition-all text-left flex items-center gap-2.5 group"
          >
            <div className="w-7 h-7 rounded-lg bg-white/5 flex items-center justify-center text-slate-300 group-hover:text-emerald-400">
              <BookmarkCheck className="w-3.5 h-3.5" />
            </div>
            <div>
              <span className="text-xs font-semibold text-slate-200 block leading-tight">My Shelf</span>
              <span className="text-xxs text-slate-400 leading-none">Active inventory</span>
            </div>
          </button>

          <button
            type="button"
            onClick={() => (onNavigateTab ? onNavigateTab("routines") : onNavigate("/routines"))}
            className="p-2.5 rounded-xl bg-[#172027]/70 border border-white/8 hover:border-white/20 transition-all text-left flex items-center gap-2.5 group"
          >
            <div className="w-7 h-7 rounded-lg bg-white/5 flex items-center justify-center text-slate-300 group-hover:text-emerald-400">
              <Calendar className="w-3.5 h-3.5" />
            </div>
            <div>
              <span className="text-xs font-semibold text-slate-200 block leading-tight">Routines</span>
              <span className="text-xxs text-slate-400 leading-none">Daily regimen</span>
            </div>
          </button>
        </div>
      </div>

      {/* --------------------------------------------------------------------- */}
      {/* 4. Routines Preview & Reminder Status Card                            */}
      {/* --------------------------------------------------------------------- */}
      <GlassCard variant="default" className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Clock className="w-4 h-4 text-emerald-400" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200">
              Daily Routines & Reminders
            </h3>
          </div>
          <button
            type="button"
            onClick={() => loadRoutinesData(true)}
            aria-label="Refresh routines"
            className="text-slate-400 hover:text-slate-200 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${routinesLoading ? "animate-spin" : ""}`} />
          </button>
        </div>

        {routinesError ? (
          <div className="p-3 rounded-xl bg-rose-950/30 border border-rose-500/30 text-rose-300 text-xs flex items-center justify-between">
            <span>{routinesError}</span>
            <button
              type="button"
              onClick={() => loadRoutinesData(true)}
              className="text-xxs text-rose-300 underline font-semibold ml-2 hover:text-white"
            >
              Retry
            </button>
          </div>
        ) : routinesLoading ? (
          <div className="space-y-2 py-2 animate-pulse">
            <div className="h-4 bg-white/10 rounded w-1/3"></div>
            <div className="h-10 bg-white/5 rounded"></div>
          </div>
        ) : (
          <div className="space-y-3">
            {/* Reminder Status Pill */}
            <div className="flex items-center justify-between p-2 rounded-xl bg-[#0C1217] border border-white/5 text-xxs">
              <div className="flex items-center gap-1.5 text-slate-300">
                {reminders?.reminders_enabled ? (
                  <Bell className="w-3.5 h-3.5 text-emerald-400" />
                ) : (
                  <BellOff className="w-3.5 h-3.5 text-slate-500" />
                )}
                <span>
                  {reminders?.reminders_enabled
                    ? `Reminders Active (Morning: ${reminders.morning_reminder_time || "08:00"} • Evening: ${reminders.evening_reminder_time || "21:00"})`
                    : "Scheduled Reminders Paused"}
                </span>
              </div>
              <button
                type="button"
                onClick={() => (onNavigateTab ? onNavigateTab("routines") : onNavigate("/routines"))}
                className="text-emerald-400 hover:underline font-medium"
              >
                Settings
              </button>
            </div>

            {/* Routines Previews */}
            {routines.length === 0 ? (
              <div className="p-3.5 rounded-xl border border-dashed border-white/10 text-center space-y-2">
                <p className="text-xs text-slate-400">
                  No routines set up yet. Create your morning or evening routine to track daily application consistency.
                </p>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => (onNavigateTab ? onNavigateTab("routines") : onNavigate("/routines"))}
                >
                  Create Routine
                </Button>
              </div>
            ) : (
              <div className="space-y-2">
                {morningRoutine && (
                  <div className="p-2.5 rounded-xl bg-[#0C1217] border border-white/5 flex items-center justify-between">
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs font-semibold text-white">{morningRoutine.name}</span>
                        <Chip variant="neutral" size="sm">
                          {morningRoutine.preferred_local_time || "Morning"}
                        </Chip>
                      </div>
                      <span className="text-xxs text-slate-400 mt-0.5 block">
                        {morningRoutine.steps?.length || 0} steps • {morningRoutine.total_completions || 0} completed
                      </span>
                    </div>

                    <Button
                      size="sm"
                      variant="primary"
                      disabled={completingRoutineId === morningRoutine.id}
                      onClick={() => handleCompleteRoutine(morningRoutine.id, "morning")}
                      className="text-xxs px-2.5 py-1"
                    >
                      {completingRoutineId === morningRoutine.id ? (
                        <RefreshCw className="w-3 h-3 animate-spin" />
                      ) : (
                        <>
                          <CheckCircle2 className="w-3 h-3 mr-1" />
                          Complete
                        </>
                      )}
                    </Button>
                  </div>
                )}

                {eveningRoutine && (
                  <div className="p-2.5 rounded-xl bg-[#0C1217] border border-white/5 flex items-center justify-between">
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs font-semibold text-white">{eveningRoutine.name}</span>
                        <Chip variant="neutral" size="sm">
                          {eveningRoutine.preferred_local_time || "Evening"}
                        </Chip>
                      </div>
                      <span className="text-xxs text-slate-400 mt-0.5 block">
                        {eveningRoutine.steps?.length || 0} steps • {eveningRoutine.total_completions || 0} completed
                      </span>
                    </div>

                    <Button
                      size="sm"
                      variant="primary"
                      disabled={completingRoutineId === eveningRoutine.id}
                      onClick={() => handleCompleteRoutine(eveningRoutine.id, "evening")}
                      className="text-xxs px-2.5 py-1"
                    >
                      {completingRoutineId === eveningRoutine.id ? (
                        <RefreshCw className="w-3 h-3 animate-spin" />
                      ) : (
                        <>
                          <CheckCircle2 className="w-3 h-3 mr-1" />
                          Complete
                        </>
                      )}
                    </Button>
                  </div>
                )}

                {!morningRoutine && !eveningRoutine && routines[0] && (
                  <div className="p-2.5 rounded-xl bg-[#0C1217] border border-white/5 flex items-center justify-between">
                    <div>
                      <span className="text-xs font-semibold text-white">{routines[0].name}</span>
                      <span className="text-xxs text-slate-400 block">
                        {routines[0].steps?.length || 0} steps
                      </span>
                    </div>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => (onNavigateTab ? onNavigateTab("routines") : onNavigate("/routines"))}
                    >
                      View
                    </Button>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </GlassCard>

      {/* --------------------------------------------------------------------- */}
      {/* 5. Recent Scan / Skin Story Entry Card                                */}
      {/* --------------------------------------------------------------------- */}
      <GlassCard variant="default" className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Camera className="w-4 h-4 text-champagne" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200">
              Recent Scan & Skin Story
            </h3>
          </div>
          <button
            type="button"
            onClick={() => loadScanData(true)}
            aria-label="Refresh scan data"
            className="text-slate-400 hover:text-slate-200 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${scanLoading ? "animate-spin" : ""}`} />
          </button>
        </div>

        {scanError ? (
          <div className="p-3 rounded-xl bg-rose-950/30 border border-rose-500/30 text-rose-300 text-xs flex items-center justify-between">
            <span>{scanError}</span>
            <button
              type="button"
              onClick={() => loadScanData(true)}
              className="text-xxs text-rose-300 underline font-semibold ml-2 hover:text-white"
            >
              Retry
            </button>
          </div>
        ) : scanLoading ? (
          <div className="space-y-2 py-2 animate-pulse">
            <div className="h-4 bg-white/10 rounded w-1/4"></div>
            <div className="h-8 bg-white/5 rounded"></div>
          </div>
        ) : recentScan ? (
          <div className="p-3 rounded-xl bg-[#0C1217] border border-white/5 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-white">
                Scan from {new Date(recentScan.created_at).toLocaleDateString()}
              </span>
              <Chip
                variant={recentScan.status === "succeeded" ? "verified" : "neutral"}
                size="sm"
              >
                {recentScan.status}
              </Chip>
            </div>

            <p className="text-xxs text-slate-400">
              Condition: {recentScan.lighting_condition.replace(/_/g, " ")} • {recentScan.camera_angle} angle
            </p>

            {skinStory?.total_succeeded_scans ? (
              <p className="text-xxs text-emerald-400">
                {skinStory.total_succeeded_scans} longitudinal visual check-ins recorded
              </p>
            ) : null}

            <div className="pt-1 flex items-center justify-end">
              <Button size="sm" variant="secondary" onClick={() => onNavigate("/skin/track")}>
                View Skin Story
              </Button>
            </div>
          </div>
        ) : (
          <div className="p-3.5 rounded-xl border border-dashed border-white/10 text-center space-y-2">
            <p className="text-xs text-slate-400">
              No Skin Story entries yet. Take your first calibrated scan to begin longitudinal tracking.
            </p>
            <Button size="sm" variant="primary" onClick={() => onNavigate("/skin/track")}>
              Track Skin
            </Button>
          </div>
        )}
      </GlassCard>

      {/* --------------------------------------------------------------------- */}
      {/* 6. Product & Ingredient Discovery Feed (Real data only)               */}
      {/* --------------------------------------------------------------------- */}
      <GlassCard variant="default" className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Compass className="w-4 h-4 text-emerald-400" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200">
              Product Formulation Discovery
            </h3>
          </div>
          <button
            type="button"
            onClick={() => loadDiscoveryData(true)}
            aria-label="Refresh discovery products"
            className="text-slate-400 hover:text-slate-200 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${discoveryLoading ? "animate-spin" : ""}`} />
          </button>
        </div>

        {discoveryError ? (
          <div className="p-3 rounded-xl bg-rose-950/30 border border-rose-500/30 text-rose-300 text-xs flex items-center justify-between">
            <span>{discoveryError}</span>
            <button
              type="button"
              onClick={() => loadDiscoveryData(true)}
              className="text-xxs text-rose-300 underline font-semibold ml-2 hover:text-white"
            >
              Retry
            </button>
          </div>
        ) : discoveryLoading ? (
          <div className="space-y-2 py-2 animate-pulse">
            <div className="h-4 bg-white/10 rounded w-1/3"></div>
            <div className="h-12 bg-white/5 rounded"></div>
          </div>
        ) : discoveryProducts.length > 0 ? (
          <div className="space-y-2">
            {discoveryProducts.slice(0, 3).map((item) => (
              <div
                key={item.product_id}
                className="p-2.5 rounded-xl bg-[#0C1217] border border-white/5 flex items-center justify-between gap-2 hover:border-white/15 transition-colors text-left"
              >
                <div className="space-y-0.5 min-w-0">
                  <div className="text-xs font-semibold text-white truncate">{item.name}</div>
                  <div className="text-xxs text-slate-400">
                    {item.brand} • {item.category}
                  </div>
                  {item.recommendation && (
                    <div className="text-xxs text-emerald-400 flex items-center gap-1">
                      <Sparkles className="w-2.5 h-2.5" />
                      <span>{item.recommendation.decision.replace(/_/g, " ")}</span>
                    </div>
                  )}
                </div>

                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => onNavigate("/explore")}
                  className="shrink-0 text-xxs px-2"
                >
                  <ChevronRight className="w-3.5 h-3.5" />
                </Button>
              </div>
            ))}

            <div className="pt-1 text-center">
              <Button
                size="sm"
                variant="secondary"
                onClick={() => onNavigate("/explore")}
                className="w-full text-xxs"
              >
                Browse All Formulations
              </Button>
            </div>
          </div>
        ) : (
          /* Honest Discovery Shortcut when no items returned */
          <div className="p-3.5 rounded-xl border border-dashed border-white/10 text-center space-y-2">
            <p className="text-xs text-slate-400">
              Search thousands of verified cosmetic products with transparent ingredient safety checks.
            </p>
            <Button size="sm" variant="secondary" onClick={() => onNavigate("/explore")}>
              Explore Products
            </Button>
          </div>
        )}
      </GlassCard>
    </div>
  );
};
