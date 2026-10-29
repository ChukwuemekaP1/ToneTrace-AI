import React, { useState, useEffect, useCallback } from "react";
import {
  Calendar,
  Plus,
  CheckCircle2,
  Bell,
  BellOff,
  Trash2,
  Edit3,
  X,
  History,
  ArrowUp,
  ArrowDown,
  Sun,
  Moon,
  Info,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { GlassCard } from "@/components/ui/GlassCard";
import { Chip } from "@/components/ui/Chip";
import { routineService, isValidUuid } from "@/api/routines";
import { shelfService } from "@/api/shelf";
import {
  RoutineResponse,
  RoutineStepInput,
  RoutineCreateRequest,
  RoutineUpdateRequest,
  RoutineCompletionResponse,
  ReminderPreferenceResponse,
  ReminderPreferenceUpdateRequest,
  ShelfItemResponse,
  ApiError,
} from "@/api/types";

export interface RoutinesPageProps {
  onNavigate: (route: string) => void;
  initialRoutineId?: string | null;
}

interface StepFormItem {
  step_order: number;
  user_product_id?: string | null;
  step_label?: string | null;
  custom_instruction?: string | null;
  frequency: "every_session" | "daily" | "alternate_days" | "twice_weekly" | "weekly" | "as_needed";
  wait_time_seconds?: number | null;
}

export const RoutinesPage: React.FC<RoutinesPageProps> = ({ onNavigate, initialRoutineId }) => {
  // Routines state
  const [routines, setRoutines] = useState<RoutineResponse[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Time of Day Filter: "all", "morning", "evening", "midday", "weekly"
  const [activeSlot, setActiveSlot] = useState<string>("all");

  // Reminders state
  const [reminders, setReminders] = useState<ReminderPreferenceResponse | null>(null);
  const [isReminderModalOpen, setIsReminderModalOpen] = useState<boolean>(false);
  const [reminderSavedMessage, setReminderSavedMessage] = useState<string | null>(null);

  // Reminder form state
  const [reminderEnabled, setReminderEnabled] = useState<boolean>(true);
  const [morningTime, setMorningTime] = useState<string>("08:00");
  const [morningEnabled, setMorningEnabled] = useState<boolean>(true);
  const [eveningTime, setEveningTime] = useState<string>("21:00");
  const [eveningEnabled, setEveningEnabled] = useState<boolean>(true);
  const [quietHoursEnabled, setQuietHoursEnabled] = useState<boolean>(true);
  const [quietStart, setQuietStart] = useState<string>("22:30");
  const [quietEnd, setQuietEnd] = useState<string>("07:00");
  const [isSavingReminders, setIsSavingReminders] = useState<boolean>(false);
  const [reminderError, setReminderError] = useState<string | null>(null);

  // Routine Completion state
  const [completingId, setCompletingId] = useState<string | null>(null);
  const [completionSuccess, setCompletionSuccess] = useState<{
    routineId: string;
    message: string;
  } | null>(null);

  // Routine History state
  const [historyRoutine, setHistoryRoutine] = useState<RoutineResponse | null>(null);
  const [historyItems, setHistoryItems] = useState<RoutineCompletionResponse[]>([]);
  const [historyLoading, setHistoryLoading] = useState<boolean>(false);

  // Routine Builder (Create/Edit) state
  const [isBuilderOpen, setIsBuilderOpen] = useState<boolean>(false);
  const [editingRoutine, setEditingRoutine] = useState<RoutineResponse | null>(null);
  const [routineName, setRoutineName] = useState<string>("");
  const [routineDesc, setRoutineDesc] = useState<string>("");
  const [routineSlot, setRoutineSlot] = useState<"morning" | "evening" | "midday" | "weekly" | "custom">(
    "morning"
  );
  const [routineFreq, setRoutineFreq] = useState<"daily" | "every_other_day" | "weekly" | "custom_days">(
    "daily"
  );
  const [routinePrefTime, setRoutinePrefTime] = useState<string>("08:00");
  const [builderSteps, setBuilderSteps] = useState<StepFormItem[]>([]);
  const [isSavingRoutine, setIsSavingRoutine] = useState<boolean>(false);
  const [builderError, setBuilderError] = useState<string | null>(null);

  // Shelf items for linking
  const [userShelfItems, setUserShelfItems] = useState<ShelfItemResponse[]>([]);

  // Delete Routine confirmation
  const [deleteConfirmRoutine, setDeleteConfirmRoutine] = useState<RoutineResponse | null>(null);
  const [isDeletingRoutine, setIsDeletingRoutine] = useState<boolean>(false);

  // ---------------------------------------------------------------------------
  // 1. Load Routines & Reminders
  // ---------------------------------------------------------------------------
  const fetchRoutines = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await routineService.listRoutines({
        time_of_day: activeSlot === "all" ? undefined : activeSlot,
      });
      setRoutines(res.items || []);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.message || "Failed to load routines.");
      } else {
        setError("Network error loading skincare routines.");
      }
    } finally {
      setLoading(false);
    }
  }, [activeSlot]);

  const fetchReminders = useCallback(async () => {
    try {
      const res = await routineService.getReminders();
      setReminders(res);
      setReminderEnabled(res.reminders_enabled);
      setMorningEnabled(res.morning_reminder_enabled);
      setMorningTime(res.morning_reminder_time || "08:00");
      setEveningEnabled(res.evening_reminder_enabled);
      setEveningTime(res.evening_reminder_time || "21:00");
      setQuietHoursEnabled(res.quiet_hours_enabled);
      setQuietStart(res.quiet_hours_start || "22:30");
      setQuietEnd(res.quiet_hours_end || "07:00");
    } catch {
      // Non-blocking if reminders cannot be loaded
    }
  }, []);

  const loadShelfForBuilder = useCallback(async () => {
    try {
      const res = await shelfService.listShelfItems({ page_size: 50 });
      setUserShelfItems(res.items || []);
    } catch {
      setUserShelfItems([]);
    }
  }, []);

  useEffect(() => {
    fetchRoutines();
  }, [fetchRoutines]);

  useEffect(() => {
    fetchReminders();
  }, [fetchReminders]);

  useEffect(() => {
    loadShelfForBuilder();
  }, [loadShelfForBuilder]);

  // Deep-link routine if valid initialRoutineId passed
  useEffect(() => {
    if (initialRoutineId && isValidUuid(initialRoutineId)) {
      routineService
        .getRoutine(initialRoutineId)
        .then((r) => {
          handleOpenHistory(r);
        })
        .catch(() => {});
    }
  }, [initialRoutineId]);

  // ---------------------------------------------------------------------------
  // 2. Routine Completion Tracking
  // ---------------------------------------------------------------------------
  const handleCompleteRoutine = async (routine: RoutineResponse) => {
    if (completingId) return;

    setCompletingId(routine.id);
    setCompletionSuccess(null);

    // Generate unique idempotency key
    const idempotencyKey = `comp_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;

    try {
      const res = await routineService.recordCompletion(routine.id, {
        status: "completed",
        idempotency_key: idempotencyKey,
      });

      // Update local count and state strictly from server result
      setRoutines((prev) =>
        prev.map((r) =>
          r.id === routine.id ? { ...r, total_completions: r.total_completions + 1 } : r
        )
      );

      setCompletionSuccess({
        routineId: routine.id,
        message: `Completed session recorded for ${res.local_date} at ${res.local_time} (${res.user_timezone})`,
      });

      setTimeout(() => {
        setCompletionSuccess(null);
      }, 5000);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.message || "Failed to record routine completion.");
      } else {
        setError("Network error while recording completion.");
      }
    } finally {
      setCompletingId(null);
    }
  };

  // ---------------------------------------------------------------------------
  // 3. Routine Completion History
  // ---------------------------------------------------------------------------
  const handleOpenHistory = async (routine: RoutineResponse) => {
    setHistoryRoutine(routine);
    setHistoryItems([]);
    setHistoryLoading(true);

    try {
      const res = await routineService.listCompletions(routine.id, 1, 20);
      setHistoryItems(res.items || []);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.message || "Could not retrieve completion history.");
      }
    } finally {
      setHistoryLoading(false);
    }
  };

  // ---------------------------------------------------------------------------
  // 4. Routine Builder (Create & Edit)
  // ---------------------------------------------------------------------------
  const handleOpenCreateBuilder = () => {
    setEditingRoutine(null);
    setRoutineName("");
    setRoutineDesc("");
    setRoutineSlot("morning");
    setRoutineFreq("daily");
    setRoutinePrefTime("08:00");
    setBuilderSteps([
      {
        step_order: 1,
        custom_instruction: "Gentle cleanse on damp skin",
        step_label: "Cleanser Step",
        frequency: "every_session",
      },
    ]);
    setBuilderError(null);
    setIsBuilderOpen(true);
  };

  const handleOpenEditBuilder = (routine: RoutineResponse) => {
    setEditingRoutine(routine);
    setRoutineName(routine.name);
    setRoutineDesc(routine.description || "");
    setRoutineSlot(
      (routine.time_of_day as "morning" | "evening" | "midday" | "weekly" | "custom") || "morning"
    );
    setRoutineFreq(
      (routine.frequency as "daily" | "every_other_day" | "weekly" | "custom_days") || "daily"
    );
    setRoutinePrefTime(routine.preferred_local_time || "08:00");
    setBuilderSteps(
      routine.steps.map((s) => ({
        step_order: s.step_order,
        user_product_id: s.user_product_id,
        step_label: s.step_label,
        custom_instruction: s.custom_instruction,
        frequency: (s.frequency as StepFormItem["frequency"]) || "every_session",
        wait_time_seconds: s.wait_time_seconds,
      }))
    );
    setBuilderError(null);
    setIsBuilderOpen(true);
  };

  const handleAddStepToBuilder = () => {
    setBuilderSteps((prev) => [
      ...prev,
      {
        step_order: prev.length + 1,
        custom_instruction: "",
        frequency: "every_session",
      },
    ]);
  };

  const handleRemoveStepFromBuilder = (index: number) => {
    setBuilderSteps((prev) => {
      const next = prev.filter((_, idx) => idx !== index);
      // Re-index step_order
      return next.map((item, idx) => ({ ...item, step_order: idx + 1 }));
    });
  };

  const handleMoveStep = (index: number, direction: "up" | "down") => {
    setBuilderSteps((prev) => {
      const targetIndex = direction === "up" ? index - 1 : index + 1;
      if (targetIndex < 0 || targetIndex >= prev.length) return prev;

      const next = [...prev];
      const item = next[index];
      next.splice(index, 1);
      next.splice(targetIndex, 0, item);

      return next.map((s, idx) => ({ ...s, step_order: idx + 1 }));
    });
  };

  const handleSaveRoutine = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!routineName.trim()) {
      setBuilderError("Routine name is required.");
      return;
    }

    if (builderSteps.length === 0) {
      setBuilderError("Routine must include at least one step.");
      return;
    }

    // Ensure every step has an instruction or product reference
    for (const step of builderSteps) {
      if (!step.user_product_id && !step.custom_instruction?.trim()) {
        setBuilderError(`Step #${step.step_order} must reference a shelf product or instruction.`);
        return;
      }
    }

    setIsSavingRoutine(true);
    setBuilderError(null);

    const formattedSteps: RoutineStepInput[] = builderSteps.map((s, idx) => ({
      step_order: idx + 1,
      user_product_id: s.user_product_id || null,
      custom_instruction: s.custom_instruction?.trim() || null,
      step_label: s.step_label?.trim() || null,
      frequency: s.frequency,
      wait_time_seconds: s.wait_time_seconds || null,
      is_active: true,
    }));

    try {
      if (editingRoutine) {
        const updatePayload: RoutineUpdateRequest = {
          name: routineName.trim(),
          description: routineDesc.trim() || null,
          time_of_day: routineSlot,
          frequency: routineFreq,
          preferred_local_time: routinePrefTime || null,
          steps: formattedSteps,
        };
        const updated = await routineService.updateRoutine(editingRoutine.id, updatePayload);
        setRoutines((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
      } else {
        const createPayload: RoutineCreateRequest = {
          name: routineName.trim(),
          description: routineDesc.trim() || null,
          time_of_day: routineSlot,
          frequency: routineFreq,
          preferred_local_time: routinePrefTime || null,
          steps: formattedSteps,
        };
        const created = await routineService.createRoutine(createPayload);
        setRoutines((prev) => [created, ...prev]);
      }

      setIsBuilderOpen(false);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setBuilderError(err.message || "Failed to save skincare routine.");
      } else {
        setBuilderError("Network issue while saving routine.");
      }
    } finally {
      setIsSavingRoutine(false);
    }
  };

  // ---------------------------------------------------------------------------
  // 5. Delete Routine
  // ---------------------------------------------------------------------------
  const handleConfirmDeleteRoutine = async () => {
    if (!deleteConfirmRoutine) return;

    setIsDeletingRoutine(true);
    try {
      await routineService.deleteRoutine(deleteConfirmRoutine.id);
      setRoutines((prev) => prev.filter((r) => r.id !== deleteConfirmRoutine.id));
      setDeleteConfirmRoutine(null);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.message || "Could not delete routine.");
      } else {
        setError("Network error deleting routine.");
      }
    } finally {
      setIsDeletingRoutine(false);
    }
  };

  // ---------------------------------------------------------------------------
  // 6. Reminder Settings
  // ---------------------------------------------------------------------------
  const handleSaveReminders = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSavingReminders(true);
    setReminderError(null);
    setReminderSavedMessage(null);

    const payload: ReminderPreferenceUpdateRequest = {
      reminders_enabled: reminderEnabled,
      morning_reminder_enabled: morningEnabled,
      morning_reminder_time: morningTime,
      evening_reminder_enabled: eveningEnabled,
      evening_reminder_time: eveningTime,
      quiet_hours_enabled: quietHoursEnabled,
      quiet_hours_start: quietStart,
      quiet_hours_end: quietEnd,
    };

    try {
      const updated = await routineService.updateReminders(payload);
      setReminders(updated);
      setReminderSavedMessage("Reminder preferences saved to backend.");
      setTimeout(() => {
        setIsReminderModalOpen(false);
        setReminderSavedMessage(null);
      }, 1500);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setReminderError(err.message || "Failed to update reminder settings.");
      } else {
        setReminderError("Network issue while saving reminder preferences.");
      }
    } finally {
      setIsSavingReminders(false);
    }
  };

  return (
    <div className="space-y-4 text-left pb-16">
      {/* ------------------------------------------------------------------- */}
      {/* 1. Header & Reminder Pill                                           */}
      {/* ------------------------------------------------------------------- */}
      <div className="space-y-2 pt-1">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-white leading-tight">
              Routines &{" "}
              <span className="font-serif italic font-normal text-champagne">Reminders</span>
            </h1>
            <p className="text-xs text-slate-400">
              Personalized regimen steps, execution tracking & schedule preferences.
            </p>
          </div>

          <div className="flex items-center gap-1.5">
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setIsReminderModalOpen(true)}
              aria-label="Reminder schedule settings"
              className="flex items-center gap-1 px-2.5"
            >
              <Bell className="w-3.5 h-3.5 text-emerald-400" />
              <span>Reminders</span>
            </Button>

            <Button
              size="sm"
              variant="primary"
              onClick={handleOpenCreateBuilder}
              aria-label="Create new routine"
              className="flex items-center gap-1 px-2.5 font-bold"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>New Routine</span>
            </Button>
          </div>
        </div>

        {/* Reminder Status Pill */}
        {reminders && (
          <div className="flex items-center justify-between p-2.5 rounded-xl bg-[#0C1217] border border-white/5 text-xxs">
            <div className="flex items-center gap-2 text-slate-300">
              {reminders.reminders_enabled ? (
                <Bell className="w-3.5 h-3.5 text-emerald-400" />
              ) : (
                <BellOff className="w-3.5 h-3.5 text-slate-500" />
              )}
              <span>
                {reminders.reminders_enabled
                  ? `Scheduled Reminders: Morning ${reminders.morning_reminder_time} • Evening ${reminders.evening_reminder_time} (${reminders.effective_timezone})`
                  : "Scheduled reminders are currently paused."}
              </span>
            </div>

            <button
              type="button"
              onClick={() => setIsReminderModalOpen(true)}
              className="text-emerald-400 hover:underline font-semibold"
            >
              Settings
            </button>
          </div>
        )}

        {/* Time-of-Day Filter Chips */}
        <div className="flex items-center gap-1 overflow-x-auto pb-1 no-scrollbar pt-1">
          {["all", "morning", "evening", "midday", "weekly"].map((slot) => (
            <button
              key={slot}
              type="button"
              onClick={() => setActiveSlot(slot)}
              className={`px-3 py-1.5 text-xxs font-medium rounded-xl capitalize whitespace-nowrap transition-all shrink-0 ${
                activeSlot === slot
                  ? "bg-emerald-500 text-slate-950 font-bold shadow-glow"
                  : "bg-white/[0.04] border border-white/8 text-slate-300 hover:border-white/20"
              }`}
            >
              {slot === "all" ? "All Slots" : `${slot} Routines`}
            </button>
          ))}
        </div>
      </div>

      {/* Global Error Banner */}
      {error && (
        <div className="p-3.5 rounded-2xl bg-rose-950/40 border border-rose-500/40 text-rose-200 text-xxs flex items-center justify-between">
          <span>{error}</span>
          <button
            type="button"
            onClick={fetchRoutines}
            className="underline font-semibold text-rose-300 hover:text-white"
          >
            Retry
          </button>
        </div>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* 2. Routines Feed & Step Management                                  */}
      {/* ------------------------------------------------------------------- */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2].map((n) => (
            <GlassCard key={n} variant="default" className="p-4 space-y-3 animate-pulse">
              <div className="h-4 bg-white/10 rounded w-1/3"></div>
              <div className="h-10 bg-white/5 rounded"></div>
            </GlassCard>
          ))}
        </div>
      ) : routines.length === 0 ? (
        /* Empty State */
        <div className="p-6 rounded-3xl bg-[#11171E]/80 border border-white/8 text-center space-y-3.5">
          <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 mx-auto flex items-center justify-center">
            <Calendar className="w-6 h-6" />
          </div>

          <div className="space-y-1">
            <h3 className="text-sm font-bold text-white">
              {activeSlot === "all" ? "No skincare routines yet" : `No ${activeSlot} routines found`}
            </h3>
            <p className="text-xxs text-slate-400 max-w-xs mx-auto leading-normal">
              Build your morning or evening routine to order steps, track daily completions, and
              configure schedule preferences.
            </p>
          </div>

          <div className="pt-2 flex items-center justify-center gap-2">
            <Button size="sm" variant="primary" onClick={handleOpenCreateBuilder}>
              Create First Routine
            </Button>
            {onNavigate && (
              <Button size="sm" variant="secondary" onClick={() => onNavigate("/shelf")}>
                Browse Shelf
              </Button>
            )}
          </div>
        </div>
      ) : (
        /* Populated Routines List */
        <div className="space-y-3">
          {routines.map((routine) => (
            <GlassCard key={routine.id} variant="default" className="p-4 space-y-3 text-left">
              {/* Routine Header */}
              <div className="flex items-start justify-between gap-2">
                <div className="space-y-0.5">
                  <div className="flex items-center gap-1.5">
                    {routine.time_of_day === "morning" ? (
                      <Sun className="w-3.5 h-3.5 text-amber-400" />
                    ) : routine.time_of_day === "evening" ? (
                      <Moon className="w-3.5 h-3.5 text-indigo-400" />
                    ) : (
                      <Calendar className="w-3.5 h-3.5 text-emerald-400" />
                    )}
                    <h2 className="text-xs font-bold text-white tracking-tight">{routine.name}</h2>
                  </div>

                  {routine.description && (
                    <p className="text-xxs text-slate-400 leading-normal">{routine.description}</p>
                  )}
                </div>

                <div className="flex items-center gap-1.5 shrink-0">
                  <Chip variant="neutral" size="sm" className="capitalize">
                    {routine.time_of_day}
                  </Chip>

                  {routine.preferred_local_time && (
                    <Chip variant="neutral" size="sm" className="font-mono text-slate-400">
                      {routine.preferred_local_time}
                    </Chip>
                  )}
                </div>
              </div>

              {/* Ordered Steps Sequence (Shown strictly in backend order) */}
              <div className="space-y-1.5 pt-1">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 block">
                  Steps Sequence ({routine.steps.length})
                </span>

                <div className="space-y-1">
                  {routine.steps
                    .sort((a, b) => a.step_order - b.step_order)
                    .map((step) => (
                      <div
                        key={step.id}
                        className="p-2 rounded-xl bg-[#0C1217] border border-white/5 flex items-center justify-between gap-2 text-xxs"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="w-5 h-5 rounded-md bg-white/5 border border-white/10 font-mono text-slate-400 font-bold flex items-center justify-center shrink-0">
                            {step.step_order}
                          </span>
                          <div className="min-w-0">
                            <span className="font-semibold text-white block truncate">
                              {step.step_label}
                            </span>
                            {step.custom_instruction && (
                              <span className="text-[10px] text-slate-400 block truncate">
                                {step.custom_instruction}
                              </span>
                            )}
                          </div>
                        </div>

                        {step.wait_time_seconds ? (
                          <span className="text-[10px] font-mono text-emerald-400 shrink-0">
                            Wait {Math.round(step.wait_time_seconds / 60)}m
                          </span>
                        ) : null}
                      </div>
                    ))}
                </div>
              </div>

              {/* Completion Success Toast */}
              {completionSuccess?.routineId === routine.id && (
                <div className="p-2 rounded-xl bg-emerald-950/40 border border-emerald-500/40 text-emerald-300 text-xxs flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                  <span>{completionSuccess.message}</span>
                </div>
              )}

              {/* Routine Card Footer Actions */}
              <div className="pt-2 border-t border-white/5 flex items-center justify-between text-xxs">
                <div className="flex items-center gap-3 text-slate-400">
                  <span>
                    Completions:{" "}
                    <span className="font-semibold text-white font-mono">
                      {routine.total_completions}
                    </span>
                  </span>

                  <button
                    type="button"
                    onClick={() => handleOpenHistory(routine)}
                    className="flex items-center gap-1 hover:text-emerald-400 transition-colors"
                  >
                    <History className="w-3 h-3" />
                    <span>View Logs</span>
                  </button>
                </div>

                <div className="flex items-center gap-1.5">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => handleOpenEditBuilder(routine)}
                    aria-label={`Edit routine ${routine.name}`}
                    className="p-1.5 text-slate-400 hover:text-white"
                  >
                    <Edit3 className="w-3.5 h-3.5" />
                  </Button>

                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setDeleteConfirmRoutine(routine)}
                    aria-label={`Delete routine ${routine.name}`}
                    className="p-1.5 text-slate-400 hover:text-rose-400"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>

                  <Button
                    size="sm"
                    variant="primary"
                    onClick={() => handleCompleteRoutine(routine)}
                    disabled={completingId === routine.id}
                    className="flex items-center gap-1 font-bold text-xxs px-2.5"
                  >
                    {completingId === routine.id ? (
                      <>
                        <Loader2 className="w-3 h-3 animate-spin" />
                        <span>Recording...</span>
                      </>
                    ) : (
                      <>
                        <CheckCircle2 className="w-3 h-3" />
                        <span>Complete Routine</span>
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </GlassCard>
          ))}
        </div>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* 3. Routine Completion History Modal                                 */}
      {/* ------------------------------------------------------------------- */}
      {historyRoutine && (
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200"
          role="dialog"
          aria-modal="true"
          aria-labelledby="history-modal-title"
        >
          <div className="w-full sm:max-w-lg bg-[#0E141B] border border-white/12 rounded-t-3xl sm:rounded-3xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh] text-left">
            <div className="p-4 sm:p-5 border-b border-white/8 flex items-center justify-between shrink-0 bg-[#0C1217]/90">
              <div className="space-y-0.5">
                <h2 id="history-modal-title" className="text-sm font-bold text-white tracking-tight">
                  Completion History
                </h2>
                <p className="text-xxs text-slate-400">{historyRoutine.name}</p>
              </div>

              <button
                type="button"
                onClick={() => setHistoryRoutine(null)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/5"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-4 sm:p-5 overflow-y-auto space-y-3 text-xs">
              {historyLoading ? (
                <div className="py-8 text-center text-slate-400 text-xxs">
                  Loading immutable completion logs...
                </div>
              ) : historyItems.length === 0 ? (
                <div className="p-6 text-center space-y-2 text-slate-400 text-xxs">
                  <History className="w-6 h-6 text-slate-500 mx-auto" />
                  <p>No completion sessions logged yet for this routine.</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {historyItems.map((item) => (
                    <div
                      key={item.id}
                      className="p-3 rounded-xl bg-[#11171E] border border-white/8 space-y-1.5 text-xxs"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-white">
                          {item.local_date} at {item.local_time}
                        </span>
                        <Chip variant="verified" size="sm" className="capitalize">
                          {item.status}
                        </Chip>
                      </div>

                      <div className="text-[10px] text-slate-500">
                        Timezone: {item.user_timezone} • Version #{item.routine_version_snapshot}
                      </div>

                      {item.notes && (
                        <p className="text-slate-300 italic pt-0.5">{item.notes}</p>
                      )}

                      {item.completed_steps_snapshot && item.completed_steps_snapshot.length > 0 && (
                        <div className="flex flex-wrap gap-1 pt-1">
                          {item.completed_steps_snapshot.map((step, idx) => (
                            <span
                              key={idx}
                              className="px-2 py-0.5 rounded-md bg-white/5 border border-white/5 text-[10px] text-slate-300"
                            >
                              {step.step_order}. {step.step_label}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              <div className="pt-2">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => setHistoryRoutine(null)}
                  className="w-full"
                >
                  Close History
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* 4. Routine Builder Modal (Create & Edit)                            */}
      {/* ------------------------------------------------------------------- */}
      {isBuilderOpen && (
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200"
          role="dialog"
          aria-modal="true"
          aria-labelledby="builder-modal-title"
        >
          <div className="w-full sm:max-w-lg bg-[#0E141B] border border-white/12 rounded-t-3xl sm:rounded-3xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh] text-left">
            <div className="p-4 sm:p-5 border-b border-white/8 flex items-center justify-between shrink-0 bg-[#0C1217]/90">
              <h2 id="builder-modal-title" className="text-sm font-bold text-white tracking-tight">
                {editingRoutine ? "Edit Skincare Routine" : "Build New Routine"}
              </h2>
              <button
                type="button"
                onClick={() => setIsBuilderOpen(false)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/5"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSaveRoutine} className="p-4 sm:p-5 overflow-y-auto space-y-4 text-xs">
              {builderError && (
                <div className="p-2.5 rounded-xl bg-rose-950/40 border border-rose-500/40 text-rose-300 text-xxs">
                  {builderError}
                </div>
              )}

              <div className="space-y-1">
                <label htmlFor="routine-title-input" className="text-xxs font-semibold text-slate-300 block">
                  Routine Title *
                </label>
                <input
                  id="routine-title-input"
                  type="text"
                  value={routineName}
                  onChange={(e) => setRoutineName(e.target.value)}
                  placeholder="e.g. Morning Barrier Defense"
                  required
                  className="w-full text-xs p-2.5 rounded-xl bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div className="grid grid-cols-3 gap-2">
                <div className="space-y-1">
                  <label htmlFor="routine-slot-select" className="text-xxs font-semibold text-slate-300 block">
                    Time Slot
                  </label>
                  <select
                    id="routine-slot-select"
                    aria-label="Time Slot"
                    value={routineSlot}
                    onChange={(e) =>
                      setRoutineSlot(
                        e.target.value as "morning" | "evening" | "midday" | "weekly" | "custom"
                      )
                    }
                    className="w-full text-xs p-2 rounded-xl bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                  >
                    <option value="morning">Morning</option>
                    <option value="evening">Evening</option>
                    <option value="midday">Midday</option>
                    <option value="weekly">Weekly</option>
                    <option value="custom">Custom</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <label htmlFor="routine-cadence-select" className="text-xxs font-semibold text-slate-300 block">
                    Cadence
                  </label>
                  <select
                    id="routine-cadence-select"
                    aria-label="Cadence"
                    value={routineFreq}
                    onChange={(e) =>
                      setRoutineFreq(
                        e.target.value as "daily" | "every_other_day" | "weekly" | "custom_days"
                      )
                    }
                    className="w-full text-xs p-2 rounded-xl bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                  >
                    <option value="daily">Daily</option>
                    <option value="every_other_day">Every Other Day</option>
                    <option value="weekly">Weekly</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <label htmlFor="routine-target-time" className="text-xxs font-semibold text-slate-300 block">
                    Target Time
                  </label>
                  <input
                    id="routine-target-time"
                    aria-label="Target Time"
                    type="time"
                    value={routinePrefTime}
                    onChange={(e) => setRoutinePrefTime(e.target.value)}
                    className="w-full text-xs p-2 rounded-xl bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                  />
                </div>
              </div>

              {/* Ordered Steps Manager */}
              <div className="space-y-2 pt-2 border-t border-white/8">
                <div className="flex items-center justify-between">
                  <span className="text-xxs font-bold uppercase tracking-wider text-slate-400">
                    Routine Steps ({builderSteps.length})
                  </span>
                  <button
                    type="button"
                    onClick={handleAddStepToBuilder}
                    className="text-xxs text-emerald-400 hover:underline flex items-center gap-1 font-semibold"
                  >
                    <Plus className="w-3 h-3" />
                    <span>Add Step</span>
                  </button>
                </div>

                <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                  {builderSteps.map((step, idx) => (
                    <div
                      key={idx}
                      className="p-2.5 rounded-xl bg-[#11171E] border border-white/8 space-y-2 text-xxs"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono font-bold text-slate-400">Step #{idx + 1}</span>

                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            onClick={() => handleMoveStep(idx, "up")}
                            disabled={idx === 0}
                            aria-label={`Move step ${idx + 1} up`}
                            className="p-1 text-slate-500 hover:text-white disabled:opacity-20"
                          >
                            <ArrowUp className="w-3 h-3" />
                          </button>
                          <button
                            type="button"
                            onClick={() => handleMoveStep(idx, "down")}
                            disabled={idx === builderSteps.length - 1}
                            aria-label={`Move step ${idx + 1} down`}
                            className="p-1 text-slate-500 hover:text-white disabled:opacity-20"
                          >
                            <ArrowDown className="w-3 h-3" />
                          </button>
                          <button
                            type="button"
                            onClick={() => handleRemoveStepFromBuilder(idx)}
                            aria-label={`Remove step ${idx + 1}`}
                            className="p-1 text-slate-500 hover:text-rose-400"
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </div>
                      </div>

                      {/* Shelf Item Link (Optional) */}
                      {userShelfItems.length > 0 && (
                        <div className="space-y-0.5">
                          <label htmlFor={`step-shelf-${idx}`} className="text-[10px] text-slate-400 block">
                            Link to Shelf Product (Optional)
                          </label>
                          <select
                            id={`step-shelf-${idx}`}
                            aria-label={`Step ${idx + 1} shelf link`}
                            value={step.user_product_id || ""}
                            onChange={(e) => {
                              const val = e.target.value || null;
                              const matched = userShelfItems.find((p) => p.id === val);
                              setBuilderSteps((prev) => {
                                const next = [...prev];
                                next[idx] = {
                                  ...next[idx],
                                  user_product_id: val,
                                  step_label: matched ? matched.display_name : next[idx].step_label,
                                };
                                return next;
                              });
                            }}
                            className="w-full text-xs p-1.5 rounded-lg bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                          >
                            <option value="">-- No shelf link (Custom instruction) --</option>
                            {userShelfItems.map((shelfProd) => (
                              <option key={shelfProd.id} value={shelfProd.id}>
                                {shelfProd.display_brand} - {shelfProd.display_name}
                              </option>
                            ))}
                          </select>
                        </div>
                      )}

                      {/* Custom Instruction */}
                      <div className="space-y-0.5">
                        <label htmlFor={`step-inst-${idx}`} className="text-[10px] text-slate-400 block">
                          Step Instruction
                        </label>
                        <input
                          id={`step-inst-${idx}`}
                          aria-label={`Step ${idx + 1} instruction`}
                          type="text"
                          value={step.custom_instruction || ""}
                          onChange={(e) => {
                            const val = e.target.value;
                            setBuilderSteps((prev) => {
                              const next = [...prev];
                              next[idx] = {
                                ...next[idx],
                                custom_instruction: val,
                                step_label: next[idx].step_label || val,
                              };
                              return next;
                            });
                          }}
                          placeholder="e.g. Apply 2-3 drops to face and neck"
                          className="w-full text-xs p-1.5 rounded-lg bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="pt-2 border-t border-white/8 flex items-center justify-end gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => setIsBuilderOpen(false)}
                  disabled={isSavingRoutine}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  disabled={isSavingRoutine}
                  className="font-bold"
                >
                  {isSavingRoutine ? "Saving..." : "Save Routine"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* 5. Reminder Preferences Modal                                       */}
      {/* ------------------------------------------------------------------- */}
      {isReminderModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200"
          role="dialog"
          aria-modal="true"
          aria-labelledby="reminder-modal-title"
        >
          <div className="w-full sm:max-w-lg bg-[#0E141B] border border-white/12 rounded-t-3xl sm:rounded-3xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh] text-left">
            <div className="p-4 sm:p-5 border-b border-white/8 flex items-center justify-between shrink-0 bg-[#0C1217]/90">
              <div className="space-y-0.5">
                <h2 id="reminder-modal-title" className="text-sm font-bold text-white tracking-tight">
                  Reminder Preferences
                </h2>
                <p className="text-xxs text-slate-400">
                  Daily notification schedules and quiet-hour settings.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setIsReminderModalOpen(false)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/5"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSaveReminders} className="p-4 sm:p-5 overflow-y-auto space-y-4 text-xs">
              {/* Notification Provider Transparency Notice */}
              <div className="p-3 rounded-xl bg-indigo-950/30 border border-indigo-500/30 text-indigo-200 text-xxs space-y-1">
                <div className="flex items-center gap-1.5 font-semibold text-indigo-300">
                  <Info className="w-3.5 h-3.5 shrink-0" />
                  <span>Notification Delivery Status</span>
                </div>
                <p className="text-indigo-200/90 leading-normal">
                  Schedule preferences are saved to your account. External push/email notifications
                  require a registered delivery worker. Simulated adapter:{" "}
                  <code className="font-mono text-indigo-300">
                    {reminders?.active_notification_provider || "local_test_recorder"}
                  </code>
                  .
                </p>
              </div>

              {reminderSavedMessage && (
                <div className="p-2.5 rounded-xl bg-emerald-950/40 border border-emerald-500/40 text-emerald-300 text-xxs">
                  {reminderSavedMessage}
                </div>
              )}

              {reminderError && (
                <div className="p-2.5 rounded-xl bg-rose-950/40 border border-rose-500/40 text-rose-300 text-xxs">
                  {reminderError}
                </div>
              )}

              {/* Master Switch */}
              <label className="flex items-center justify-between p-3 rounded-xl bg-[#11171E] border border-white/8 cursor-pointer">
                <div>
                  <span className="text-xs font-bold text-white block">Enable Routine Reminders</span>
                  <span className="text-xxs text-slate-400 block mt-0.5">
                    Allow ToneTrace to evaluate daily schedule check-ins
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={reminderEnabled}
                  onChange={(e) => setReminderEnabled(e.target.checked)}
                  className="rounded border-white/20 text-emerald-500 focus:ring-0 w-4 h-4"
                />
              </label>

              {/* Morning & Evening Times */}
              <div className="grid grid-cols-2 gap-2.5">
                <div className="p-3 rounded-xl bg-[#11171E] border border-white/8 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xxs font-bold text-white">Morning Slot</span>
                    <input
                      type="checkbox"
                      checked={morningEnabled}
                      onChange={(e) => setMorningEnabled(e.target.checked)}
                      className="rounded border-white/20 text-emerald-500 w-3.5 h-3.5"
                    />
                  </div>
                  <input
                    type="time"
                    value={morningTime}
                    onChange={(e) => setMorningTime(e.target.value)}
                    disabled={!morningEnabled}
                    className="w-full text-xs p-2 rounded-lg bg-[#090D11] border border-white/10 text-white disabled:opacity-30 focus:outline-none focus:border-emerald-500"
                  />
                </div>

                <div className="p-3 rounded-xl bg-[#11171E] border border-white/8 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xxs font-bold text-white">Evening Slot</span>
                    <input
                      type="checkbox"
                      checked={eveningEnabled}
                      onChange={(e) => setEveningEnabled(e.target.checked)}
                      className="rounded border-white/20 text-emerald-500 w-3.5 h-3.5"
                    />
                  </div>
                  <input
                    type="time"
                    value={eveningTime}
                    onChange={(e) => setEveningTime(e.target.value)}
                    disabled={!eveningEnabled}
                    className="w-full text-xs p-2 rounded-lg bg-[#090D11] border border-white/10 text-white disabled:opacity-30 focus:outline-none focus:border-emerald-500"
                  />
                </div>
              </div>

              {/* Quiet Hours */}
              <div className="p-3 rounded-xl bg-[#11171E] border border-white/8 space-y-2.5">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-xs font-bold text-white block">Quiet Hours</span>
                    <span className="text-xxs text-slate-400 block mt-0.5">
                      Suppress reminders during sleep intervals
                    </span>
                  </div>
                  <input
                    type="checkbox"
                    checked={quietHoursEnabled}
                    onChange={(e) => setQuietHoursEnabled(e.target.checked)}
                    className="rounded border-white/20 text-emerald-500 w-4 h-4"
                  />
                </div>

                {quietHoursEnabled && (
                  <div className="grid grid-cols-2 gap-2 pt-1">
                    <div className="space-y-1">
                      <label className="text-[10px] text-slate-400 block">Start Quiet</label>
                      <input
                        type="time"
                        value={quietStart}
                        onChange={(e) => setQuietStart(e.target.value)}
                        className="w-full text-xs p-1.5 rounded-lg bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-[10px] text-slate-400 block">End Quiet</label>
                      <input
                        type="time"
                        value={quietEnd}
                        onChange={(e) => setQuietEnd(e.target.value)}
                        className="w-full text-xs p-1.5 rounded-lg bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                      />
                    </div>
                  </div>
                )}
              </div>

              <div className="pt-2 border-t border-white/8 flex items-center justify-end gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => setIsReminderModalOpen(false)}
                  disabled={isSavingReminders}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  disabled={isSavingReminders}
                  className="font-bold"
                >
                  {isSavingReminders ? "Saving..." : "Save Preferences"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* 6. Delete Routine Confirmation Dialog                               */}
      {/* ------------------------------------------------------------------- */}
      {deleteConfirmRoutine && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/85 backdrop-blur-md animate-in fade-in duration-150"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-routine-dialog-title"
        >
          <div className="w-full max-w-sm bg-[#0E141B] border border-rose-500/30 rounded-2xl p-5 shadow-2xl text-center space-y-3">
            <div className="w-10 h-10 rounded-full bg-rose-950/50 border border-rose-500/40 text-rose-400 mx-auto flex items-center justify-center">
              <Trash2 className="w-5 h-5" />
            </div>

            <div className="space-y-1">
              <h3 id="delete-routine-dialog-title" className="text-sm font-bold text-white">
                Delete Skincare Routine?
              </h3>
              <p className="text-xxs text-slate-400 leading-normal">
                Are you sure you want to delete{" "}
                <span className="font-semibold text-white">"{deleteConfirmRoutine.name}"</span>?
                Historical completion logs will be preserved.
              </p>
            </div>

            <div className="pt-2 flex items-center justify-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setDeleteConfirmRoutine(null)}
                disabled={isDeletingRoutine}
              >
                Keep Routine
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleConfirmDeleteRoutine}
                disabled={isDeletingRoutine}
                className="bg-rose-600 hover:bg-rose-500 text-white font-bold"
              >
                {isDeletingRoutine ? "Deleting..." : "Yes, Delete"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
