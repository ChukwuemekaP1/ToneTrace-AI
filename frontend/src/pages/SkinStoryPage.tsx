import React, { useState, useEffect, useCallback } from "react";
import {
  BookOpen,
  Calendar,
  AlertTriangle,
  Info,
  Plus,
  X,
  Camera,
  Activity,
  History,
  TrendingUp,
  TrendingDown,
  Minus,
  CheckCircle2,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { GlassCard } from "@/components/ui/GlassCard";
import { Chip } from "@/components/ui/Chip";
import { skinService } from "@/api/skin";
import {
  SkinStoryResponse,
  SkinMetricTimeline,
  SkinStoryPoint,
  SkinJournalEntryResponse,
  CreateSkinJournalEntryRequest,
  ApiError,
} from "@/api/types";

export interface SkinStoryPageProps {
  onNavigate?: (route: string) => void;
  initialMetric?: string | null;
}

export const NON_CLINICAL_DISCLAIMER =
  "Photo-based observations are for tracking visible changes, not a clinical diagnosis.";

export const TEMPORAL_CAUSATION_DISCLAIMER =
  "ToneTrace reports only surface-level visual appearance metrics and user-authored journal reflections. Temporal correlation does not imply clinical causation.";

export const COMMON_SKIN_STATES = [
  "Calm & Balanced",
  "Hydrated",
  "Dry & Tight",
  "Surface Redness",
  "Congested",
  "Sensitive",
  "Irritated",
];

export const COMMON_OBSERVATIONS = [
  "Cheek redness",
  "Smooth surface texture",
  "Visible forehead shine",
  "Dry patches",
  "Post-blemish spot mark",
  "Pore prominence",
];

export const SkinStoryPage: React.FC<SkinStoryPageProps> = ({
  onNavigate,
  initialMetric,
}) => {
  // Skin Story state
  const [skinStory, setSkinStory] = useState<SkinStoryResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filter Metric: "all" or specific metric_code
  const [activeMetricFilter, setActiveMetricFilter] = useState<string>(
    initialMetric || "all"
  );

  // Journal Entry Form Modal state
  const [isJournalModalOpen, setIsJournalModalOpen] = useState<boolean>(false);
  const [perceivedState, setPerceivedState] = useState<string>("Calm & Balanced");
  const [customState, setCustomState] = useState<string>("");
  const [selectedObs, setSelectedObs] = useState<string[]>([]);
  const [customObsInput, setCustomObsInput] = useState<string>("");
  const [routineNotes, setRoutineNotes] = useState<string>("");
  const [productsUsed, setProductsUsed] = useState<string>("");
  const [reflectionNotes, setReflectionNotes] = useState<string>("");
  const [isSavingJournal, setIsSavingJournal] = useState<boolean>(false);
  const [journalError, setJournalError] = useState<string | null>(null);
  const [journalSuccessMessage, setJournalSuccessMessage] = useState<string | null>(null);

  // Delete Scan modal from timeline
  const [scanToDeleteId, setScanToDeleteId] = useState<string | null>(null);
  const [isDeletingScan, setIsDeletingScan] = useState<boolean>(false);

  // ---------------------------------------------------------------------------
  // 1. Fetch Longitudinal Skin Story
  // ---------------------------------------------------------------------------
  const fetchSkinStory = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await skinService.getSkinStory({
        metric: activeMetricFilter === "all" ? undefined : activeMetricFilter,
        journalLimit: 15,
      });
      setSkinStory(data);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.message || "Failed to load Skin Story.");
      } else {
        setError("Network error loading longitudinal observations.");
      }
    } finally {
      setLoading(false);
    }
  }, [activeMetricFilter]);

  useEffect(() => {
    fetchSkinStory();
  }, [fetchSkinStory]);

  // ---------------------------------------------------------------------------
  // 2. Journal Reflection Creation
  // ---------------------------------------------------------------------------
  const handleToggleObservation = (obs: string) => {
    setSelectedObs((prev) =>
      prev.includes(obs) ? prev.filter((o) => o !== obs) : [...prev, obs]
    );
  };

  const handleAddCustomObservation = () => {
    const trimmed = customObsInput.trim();
    if (trimmed && !selectedObs.includes(trimmed)) {
      setSelectedObs((prev) => [...prev, trimmed]);
      setCustomObsInput("");
    }
  };

  const handleSaveJournal = async (e: React.FormEvent) => {
    e.preventDefault();
    const finalState = customState.trim() || perceivedState;
    if (!finalState.trim() || isSavingJournal) return;

    setIsSavingJournal(true);
    setJournalError(null);

    const productsList = productsUsed
      .split(",")
      .map((p) => p.trim())
      .filter((p) => p.length > 0);

    const payload: CreateSkinJournalEntryRequest = {
      perceived_skin_state: finalState,
      self_reported_observations: selectedObs,
      routine_notes: routineNotes.trim() || null,
      products_used: productsList,
      notes: reflectionNotes.trim() || null,
    };

    try {
      const newEntry = await skinService.createJournalEntry(payload);
      // Append to current journal entries in state
      setSkinStory((prev) =>
        prev
          ? {
              ...prev,
              recent_journal_entries: [
                newEntry,
                ...prev.recent_journal_entries.filter((e) => e.id !== newEntry.id),
              ],
            }
          : prev
      );

      setJournalSuccessMessage("Journal reflection logged successfully.");
      setTimeout(() => {
        setIsJournalModalOpen(false);
        setJournalSuccessMessage(null);
        // Reset form
        setPerceivedState("Calm & Balanced");
        setCustomState("");
        setSelectedObs([]);
        setRoutineNotes("");
        setProductsUsed("");
        setReflectionNotes("");
      }, 1000);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setJournalError(err.message || "Failed to record journal reflection.");
      } else {
        setJournalError("Network error while recording journal entry.");
      }
    } finally {
      setIsSavingJournal(false);
    }
  };

  // ---------------------------------------------------------------------------
  // 3. Scan Deletion
  // ---------------------------------------------------------------------------
  const handleConfirmDeleteScan = async () => {
    if (!scanToDeleteId || isDeletingScan) return;

    setIsDeletingScan(true);
    try {
      await skinService.deleteScan(scanToDeleteId);
      setScanToDeleteId(null);
      // Refresh story to purge observations from timelines
      fetchSkinStory();
    } catch {
      setScanToDeleteId(null);
    } finally {
      setIsDeletingScan(false);
    }
  };

  // Filtered Timelines
  const displayedTimelines = skinStory?.metric_timelines.filter((tl) =>
    activeMetricFilter === "all" ? true : tl.metric_code === activeMetricFilter
  ) || [];

  return (
    <div className="space-y-4 text-left pb-16">
      {/* ------------------------------------------------------------------- */}
      {/* 1. Header & Actions                                                 */}
      {/* ------------------------------------------------------------------- */}
      <div className="space-y-1 pt-1">
        <div className="flex items-center justify-between">
          <div>
            <h1 aria-label="Skin Story" className="text-xl font-bold tracking-tight text-white leading-tight">
              Skin <span className="font-serif italic font-normal text-champagne">Story</span>
            </h1>
            <p className="text-xs text-slate-400">
              Longitudinal visual appearance tracking & journal reflections.
            </p>
          </div>

          <div className="flex items-center gap-1.5">
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setIsJournalModalOpen(true)}
              aria-label="New journal reflection"
              className="flex items-center gap-1 text-xxs px-2.5"
            >
              <BookOpen className="w-3.5 h-3.5 text-emerald-400" />
              <span>Log Journal</span>
            </Button>

            {onNavigate && (
              <Button
                size="sm"
                variant="primary"
                onClick={() => onNavigate("/skin/scan")}
                aria-label="Take new skin scan"
                className="flex items-center gap-1 text-xxs font-bold px-2.5"
              >
                <Camera className="w-3.5 h-3.5" />
                <span>New Scan</span>
              </Button>
            )}
          </div>
        </div>

        {/* Non-Diagnostic Policy Banner */}
        <div className="p-3 rounded-2xl bg-[#0C1217] border border-white/8 text-slate-300 text-xxs space-y-1">
          <div className="flex items-center gap-1.5 font-semibold text-white">
            <Info className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
            <span>Non-Clinical Tracking Framework</span>
          </div>
          <p className="leading-relaxed text-slate-400">{NON_CLINICAL_DISCLAIMER}</p>
          <p className="leading-relaxed text-[10px] text-slate-500 italic pt-0.5">
            {TEMPORAL_CAUSATION_DISCLAIMER}
          </p>
        </div>
      </div>

      {/* ------------------------------------------------------------------- */}
      {/* 2. Metric Filter Tabs                                               */}
      {/* ------------------------------------------------------------------- */}
      {skinStory && skinStory.metric_timelines.length > 0 && (
        <div className="flex items-center gap-1 overflow-x-auto pb-1 no-scrollbar pt-1">
          <button
            type="button"
            onClick={() => setActiveMetricFilter("all")}
            className={`px-3 py-1.5 text-xxs font-medium rounded-xl capitalize whitespace-nowrap transition-all shrink-0 ${
              activeMetricFilter === "all"
                ? "bg-emerald-500 text-slate-950 font-bold shadow-glow"
                : "bg-white/[0.04] border border-white/8 text-slate-300 hover:border-white/20"
            }`}
          >
            All Observations
          </button>

          {skinStory.metric_timelines.map((tl) => (
            <button
              key={tl.metric_code}
              type="button"
              onClick={() => setActiveMetricFilter(tl.metric_code)}
              className={`px-3 py-1.5 text-xxs font-medium rounded-xl capitalize whitespace-nowrap transition-all shrink-0 ${
                activeMetricFilter === tl.metric_code
                  ? "bg-emerald-500 text-slate-950 font-bold shadow-glow"
                  : "bg-white/[0.04] border border-white/8 text-slate-300 hover:border-white/20"
              }`}
            >
              {tl.metric_label.split("&")[0].trim()}
            </button>
          ))}
        </div>
      )}

      {/* Global Error Banner */}
      {error && (
        <div className="p-3.5 rounded-2xl bg-rose-950/40 border border-rose-500/40 text-rose-200 text-xxs flex items-center justify-between">
          <span>{error}</span>
          <button
            type="button"
            onClick={fetchSkinStory}
            className="underline font-semibold text-rose-300 hover:text-white"
          >
            Retry
          </button>
        </div>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* 3. Longitudinal Timelines & Charts                                  */}
      {/* ------------------------------------------------------------------- */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2].map((n) => (
            <GlassCard key={n} variant="default" className="p-4 space-y-3 animate-pulse">
              <div className="h-4 bg-white/10 rounded w-1/3"></div>
              <div className="h-28 bg-white/5 rounded"></div>
            </GlassCard>
          ))}
        </div>
      ) : displayedTimelines.length === 0 ? (
        /* Empty State */
        <div className="p-6 rounded-3xl bg-[#11171E]/80 border border-white/8 text-center space-y-3.5">
          <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 mx-auto flex items-center justify-center">
            <History className="w-6 h-6" />
          </div>

          <div className="space-y-1">
            <h3 className="text-sm font-bold text-white">No Skin Story Observations Yet</h3>
            <p className="text-xxs text-slate-400 max-w-xs mx-auto leading-normal">
              Capture your first facial scan to establish an optical baseline for surface redness,
              texture, spots, and pore metrics over time.
            </p>
          </div>

          <div className="pt-2 flex items-center justify-center gap-2">
            {onNavigate && (
              <Button
                size="sm"
                variant="primary"
                onClick={() => onNavigate("/skin/scan")}
                className="font-bold flex items-center gap-1"
              >
                <Camera className="w-3.5 h-3.5" />
                <span>Start First Skin Scan</span>
              </Button>
            )}

            <Button
              size="sm"
              variant="secondary"
              onClick={() => setIsJournalModalOpen(true)}
              className="text-xxs"
            >
              Write Journal Reflection
            </Button>
          </div>
        </div>
      ) : (
        /* Render Metric Timelines */
        <div className="space-y-4">
          {displayedTimelines.map((timeline: SkinMetricTimeline) => {
            const comparablePoints = timeline.points.filter((p) => p.is_comparable_to_baseline);
            const hasMultipleComparable = comparablePoints.length >= 2;

            return (
              <GlassCard key={timeline.metric_code} variant="default" className="p-4 space-y-3 text-left">
                {/* Timeline Header */}
                <div className="flex items-start justify-between gap-2">
                  <div className="space-y-0.5">
                    <h2 className="text-xs font-bold text-white tracking-tight">
                      {timeline.metric_label}
                    </h2>
                    <span className="text-[10px] text-slate-400 block font-mono">
                      Baseline: {timeline.baseline_provider || "Standard"} •{" "}
                      {timeline.baseline_model_version || "v1.0"}
                    </span>
                  </div>

                  {/* Net Observed Delta Badge */}
                  <div className="flex items-center gap-1.5 shrink-0">
                    {timeline.observation_classification === "visual_metric_increase" ? (
                      <Chip variant="verified" size="sm" className="flex items-center gap-1 text-emerald-300">
                        <TrendingUp className="w-3 h-3" />
                        <span>
                          {timeline.net_observed_delta !== null
                            ? `+${timeline.net_observed_delta}`
                            : "Increase"}
                        </span>
                      </Chip>
                    ) : timeline.observation_classification === "visual_metric_decrease" ? (
                      <Chip variant="caution" size="sm" className="flex items-center gap-1 text-amber-300">
                        <TrendingDown className="w-3 h-3" />
                        <span>
                          {timeline.net_observed_delta !== null
                            ? `${timeline.net_observed_delta}`
                            : "Decrease"}
                        </span>
                      </Chip>
                    ) : timeline.observation_classification === "visual_metric_stable" ? (
                      <Chip variant="neutral" size="sm" className="flex items-center gap-1 text-slate-300">
                        <Minus className="w-3 h-3" />
                        <span>Stable</span>
                      </Chip>
                    ) : (
                      <Chip variant="neutral" size="sm" className="text-slate-400 text-[10px]">
                        Single / Insufficient Data
                      </Chip>
                    )}
                  </div>
                </div>

                {/* Non-clinical interpretation note from server */}
                {timeline.non_clinical_interpretation && (
                  <p className="text-[11px] text-slate-300 leading-normal bg-[#090D11] p-2.5 rounded-xl border border-white/5">
                    {timeline.non_clinical_interpretation}
                  </p>
                )}

                {/* Compatibility Warnings from Backend */}
                {timeline.compatibility_warnings && timeline.compatibility_warnings.length > 0 && (
                  <div className="p-2 rounded-xl bg-amber-950/30 border border-amber-500/30 text-amber-200 text-xxs space-y-1">
                    {timeline.compatibility_warnings.map((w, i) => (
                      <div key={i} className="flex items-center gap-1 text-[11px]">
                        <AlertTriangle className="w-3 h-3 shrink-0 text-amber-400" />
                        <span>{w}</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* ----------------------------------------------------------- */}
                {/* Charting: Line Chart ONLY when Multiple Comparable Points    */}
                {/* ----------------------------------------------------------- */}
                {hasMultipleComparable ? (
                  <div className="space-y-1.5 pt-1">
                    <div className="flex items-center justify-between text-xxs text-slate-400 px-1">
                      <span className="font-semibold text-slate-300 flex items-center gap-1">
                        <Activity className="w-3 h-3 text-emerald-400" />
                        <span>Comparable Visual Score Trend</span>
                      </span>
                      <span className="font-mono text-[10px]">Scale: 0 - 100</span>
                    </div>

                    {/* SVG Line Chart */}
                    <div className="p-3 rounded-2xl bg-[#090D11] border border-white/6 overflow-hidden">
                      <svg
                        viewBox="0 0 320 100"
                        className="w-full h-24 overflow-visible"
                        role="img"
                        aria-label={`Visual trend line chart for ${timeline.metric_label}`}
                      >
                        {/* Background Guide Lines */}
                        <line x1="0" y1="20" x2="320" y2="20" stroke="rgba(255,255,255,0.06)" strokeDasharray="3 3" />
                        <line x1="0" y1="50" x2="320" y2="50" stroke="rgba(255,255,255,0.06)" strokeDasharray="3 3" />
                        <line x1="0" y1="80" x2="320" y2="80" stroke="rgba(255,255,255,0.06)" strokeDasharray="3 3" />

                        {/* Chart Line connecting comparable points */}
                        {(() => {
                          const pts = comparablePoints;
                          const minX = 20;
                          const maxX = 300;
                          const stepX = (maxX - minX) / Math.max(pts.length - 1, 1);
                          const coords = pts.map((p, idx) => {
                            const x = minX + idx * stepX;
                            // Clamp value between 0 and 100, invert Y (0 is at y=85, 100 is at y=15)
                            const val = Math.max(0, Math.min(100, p.display_value));
                            const y = 85 - (val / 100) * 70;
                            return { x, y, point: p };
                          });

                          const polylinePoints = coords.map((c) => `${c.x},${c.y}`).join(" ");

                          return (
                            <>
                              <polyline
                                fill="none"
                                stroke="#10b981"
                                strokeWidth="2.5"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                points={polylinePoints}
                              />
                              {coords.map((c, idx) => (
                                <g key={idx}>
                                  <circle
                                    cx={c.x}
                                    cy={c.y}
                                    r="4"
                                    className="fill-slate-950 stroke-emerald-400 stroke-2"
                                  />
                                  <text
                                    x={c.x}
                                    y={c.y - 7}
                                    textAnchor="middle"
                                    className="fill-slate-200 text-[9px] font-mono font-bold"
                                  >
                                    {c.point.display_value}
                                  </text>
                                  <text
                                    x={c.x}
                                    y="96"
                                    textAnchor="middle"
                                    className="fill-slate-500 text-[8px] font-mono"
                                  >
                                    {new Date(c.point.observed_at).toLocaleDateString([], {
                                      month: "numeric",
                                      day: "numeric",
                                    })}
                                  </text>
                                </g>
                              ))}
                            </>
                          );
                        })()}
                      </svg>
                    </div>
                  </div>
                ) : (
                  /* Discrete Observation Fallback (Insufficent data for line) */
                  <div className="p-3 rounded-2xl bg-[#090D11] border border-white/6 space-y-1.5 text-xxs">
                    <div className="flex items-center gap-1.5 text-slate-400">
                      <Info className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      <span className="font-semibold text-slate-300">
                        Discrete Historical Observations
                      </span>
                    </div>
                    <p className="text-[10px] text-slate-400 leading-normal">
                      A continuous line chart requires at least 2 comparable observations using the
                      same optical engine and lighting calibration.
                    </p>
                  </div>
                )}

                {/* Discrete Data Points Breakdown */}
                <div className="space-y-1.5 pt-1">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 block">
                    Recorded Observations ({timeline.points.length})
                  </span>

                  <div className="space-y-1">
                    {timeline.points.map((pt: SkinStoryPoint) => (
                      <div
                        key={pt.observation_id}
                        className="p-2 rounded-xl bg-[#0C1217] border border-white/5 flex items-center justify-between text-xxs"
                      >
                        <div className="space-y-0.5">
                          <div className="flex items-center gap-1.5">
                            <span className="font-semibold text-white">
                              {new Date(pt.observed_at).toLocaleDateString()} at{" "}
                              {new Date(pt.observed_at).toLocaleTimeString([], {
                                hour: "2-digit",
                                minute: "2-digit",
                              })}
                            </span>

                            {pt.is_comparable_to_baseline ? (
                              <span className="px-1.5 py-0.2 rounded bg-emerald-500/10 text-emerald-400 font-mono text-[9px]">
                                Comparable
                              </span>
                            ) : (
                              <span className="px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-400 font-mono text-[9px]">
                                Non-comparable
                              </span>
                            )}
                          </div>

                          {pt.incompatibility_reason && (
                            <span className="text-[10px] text-amber-300/80 block">
                              {pt.incompatibility_reason}
                            </span>
                          )}
                        </div>

                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold text-emerald-400 text-xs">
                            {pt.display_value}
                            <span className="text-[10px] text-slate-500">
                              {pt.unit === "score_0_100" ? "/100" : ` ${pt.unit}`}
                            </span>
                          </span>

                          <button
                            type="button"
                            onClick={() => setScanToDeleteId(pt.scan_id)}
                            aria-label={`Delete scan from ${new Date(pt.observed_at).toLocaleDateString()}`}
                            className="p-1 text-slate-500 hover:text-rose-400 transition-colors"
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </GlassCard>
            );
          })}
        </div>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* 4. Skin Story Journal Reflections Section                          */}
      {/* ------------------------------------------------------------------- */}
      <div className="space-y-3 pt-3 border-t border-white/8 text-left">
        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <h2 className="text-sm font-bold text-white tracking-tight">
              Skin Journal Reflections
            </h2>
            <p className="text-xxs text-slate-400">
              Personal qualitative observations, product changes & daily context.
            </p>
          </div>

          <Button
            size="sm"
            variant="secondary"
            onClick={() => setIsJournalModalOpen(true)}
            className="text-xxs flex items-center gap-1 font-semibold"
          >
            <Plus className="w-3 h-3" />
            <span>New Entry</span>
          </Button>
        </div>

        {skinStory?.recent_journal_entries && skinStory.recent_journal_entries.length > 0 ? (
          <div className="space-y-2">
            {skinStory.recent_journal_entries.map((entry: SkinJournalEntryResponse) => (
              <GlassCard key={entry.id} variant="default" className="p-3.5 space-y-2 text-xxs text-left">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <Calendar className="w-3.5 h-3.5 text-emerald-400" />
                    <span className="font-semibold text-white">
                      {new Date(entry.recorded_at).toLocaleDateString()}
                    </span>
                  </div>

                  <Chip variant="verified" size="sm">
                    {entry.perceived_skin_state}
                  </Chip>
                </div>

                {/* Observations list */}
                {entry.self_reported_observations && entry.self_reported_observations.length > 0 && (
                  <div className="flex flex-wrap gap-1 pt-0.5">
                    {entry.self_reported_observations.map((obs, idx) => (
                      <span
                        key={idx}
                        className="px-2 py-0.5 rounded-md bg-white/5 border border-white/5 text-[10px] text-slate-300"
                      >
                        {obs}
                      </span>
                    ))}
                  </div>
                )}

                {/* Routine / Product Notes */}
                {entry.routine_notes && (
                  <div className="text-[11px] text-slate-300 pt-1 leading-normal">
                    <strong className="text-white block font-medium">Routine Notes:</strong>
                    <span>{entry.routine_notes}</span>
                  </div>
                )}

                {/* Personal Reflection */}
                {entry.notes && (
                  <p className="text-[10px] text-slate-400 italic pt-0.5 leading-normal">
                    "{entry.notes}"
                  </p>
                )}
              </GlassCard>
            ))}
          </div>
        ) : (
          <div className="p-4 rounded-2xl bg-[#090D11] border border-white/6 text-center text-slate-400 text-xxs space-y-1">
            <p>No journal reflections logged yet.</p>
            <button
              type="button"
              onClick={() => setIsJournalModalOpen(true)}
              className="text-emerald-400 hover:underline font-semibold"
            >
              Log your first daily skin reflection
            </button>
          </div>
        )}
      </div>

      {/* ------------------------------------------------------------------- */}
      {/* 5. Create Journal Entry Modal                                       */}
      {/* ------------------------------------------------------------------- */}
      {isJournalModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200"
          role="dialog"
          aria-modal="true"
          aria-labelledby="journal-modal-title"
        >
          <div className="w-full sm:max-w-lg bg-[#0E141B] border border-white/12 rounded-t-3xl sm:rounded-3xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh] text-left">
            <div className="p-4 sm:p-5 border-b border-white/8 flex items-center justify-between shrink-0 bg-[#0C1217]/90">
              <div className="space-y-0.5">
                <h2 id="journal-modal-title" className="text-sm font-bold text-white tracking-tight">
                  Log Skin Reflection
                </h2>
                <p className="text-xxs text-slate-400">
                  Record qualitative feelings, routine changes & self-reported notes.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setIsJournalModalOpen(false)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/5"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSaveJournal} className="p-4 sm:p-5 overflow-y-auto space-y-4 text-xs">
              {journalSuccessMessage && (
                <div className="p-2.5 rounded-xl bg-emerald-950/40 border border-emerald-500/40 text-emerald-300 text-xxs flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                  <span>{journalSuccessMessage}</span>
                </div>
              )}

              {journalError && (
                <div className="p-2.5 rounded-xl bg-rose-950/40 border border-rose-500/40 text-rose-300 text-xxs">
                  {journalError}
                </div>
              )}

              {/* Perceived Skin State Selector */}
              <div className="space-y-1.5">
                <label className="text-xxs font-semibold text-slate-300 block">
                  Perceived Overall Skin State *
                </label>
                <div className="flex flex-wrap gap-1.5">
                  {COMMON_SKIN_STATES.map((st) => (
                    <button
                      key={st}
                      type="button"
                      onClick={() => {
                        setPerceivedState(st);
                        setCustomState("");
                      }}
                      className={`px-2.5 py-1 text-xxs rounded-lg font-medium transition-all ${
                        perceivedState === st && !customState
                          ? "bg-emerald-500 text-slate-950 font-bold"
                          : "bg-white/5 text-slate-300 border border-white/8 hover:border-white/20"
                      }`}
                    >
                      {st}
                    </button>
                  ))}
                </div>
                <input
                  type="text"
                  value={customState}
                  onChange={(e) => setCustomState(e.target.value)}
                  placeholder="Or enter custom state (e.g. Mildly tight post-flight)"
                  className="w-full text-xs p-2 rounded-xl bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500 mt-1"
                />
              </div>

              {/* Self-reported Observations Chips */}
              <div className="space-y-1.5">
                <label className="text-xxs font-semibold text-slate-300 block">
                  Specific Surface Observations
                </label>
                <div className="flex flex-wrap gap-1.5">
                  {COMMON_OBSERVATIONS.map((obs) => {
                    const isSelected = selectedObs.includes(obs);
                    return (
                      <button
                        key={obs}
                        type="button"
                        onClick={() => handleToggleObservation(obs)}
                        className={`px-2.5 py-1 text-xxs rounded-lg font-medium transition-all ${
                          isSelected
                            ? "bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 font-semibold"
                            : "bg-white/5 text-slate-400 border border-white/8 hover:text-white"
                        }`}
                      >
                        {isSelected ? `✓ ${obs}` : `+ ${obs}`}
                      </button>
                    );
                  })}
                </div>

                <div className="flex gap-1.5 pt-1">
                  <input
                    type="text"
                    value={customObsInput}
                    onChange={(e) => setCustomObsInput(e.target.value)}
                    placeholder="Add specific observation..."
                    className="flex-1 text-xs p-2 rounded-xl bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={handleAddCustomObservation}
                    disabled={!customObsInput.trim()}
                  >
                    Add
                  </Button>
                </div>
              </div>

              {/* Routine Notes */}
              <div className="space-y-1">
                <label className="text-xxs font-semibold text-slate-300 block">
                  Routine Context / Changes
                </label>
                <input
                  type="text"
                  value={routineNotes}
                  onChange={(e) => setRoutineNotes(e.target.value)}
                  placeholder="e.g. Skipped exfoliant today; added barrier moisturizer"
                  className="w-full text-xs p-2 rounded-xl bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                />
              </div>

              {/* Products Used */}
              <div className="space-y-1">
                <label className="text-xxs font-semibold text-slate-300 block">
                  Products Used (comma-separated)
                </label>
                <input
                  type="text"
                  value={productsUsed}
                  onChange={(e) => setProductsUsed(e.target.value)}
                  placeholder="e.g. Centella Cleanser, B5 Serum, Mineral SPF"
                  className="w-full text-xs p-2 rounded-xl bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                />
              </div>

              {/* Reflection Notes */}
              <div className="space-y-1">
                <label className="text-xxs font-semibold text-slate-300 block">
                  Personal Reflection
                </label>
                <textarea
                  rows={3}
                  value={reflectionNotes}
                  onChange={(e) => setReflectionNotes(e.target.value)}
                  placeholder="How does your skin feel physically today? Any lifestyle factors (sleep, hydration, weather)?"
                  className="w-full text-xs p-2.5 rounded-xl bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div className="pt-2 border-t border-white/8 flex items-center justify-end gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => setIsJournalModalOpen(false)}
                  disabled={isSavingJournal}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  disabled={isSavingJournal}
                  className="font-bold"
                >
                  {isSavingJournal ? "Saving..." : "Save Reflection"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* 6. Delete Scan Confirmation Modal                                   */}
      {/* ------------------------------------------------------------------- */}
      {scanToDeleteId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/85 backdrop-blur-md animate-in fade-in duration-150"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-timeline-scan-title"
        >
          <div className="w-full max-w-sm bg-[#0E141B] border border-rose-500/30 rounded-2xl p-5 shadow-2xl text-center space-y-3">
            <div className="w-10 h-10 rounded-full bg-rose-950/50 border border-rose-500/40 text-rose-400 mx-auto flex items-center justify-center">
              <Trash2 className="w-5 h-5" />
            </div>

            <div className="space-y-1">
              <h3 id="delete-timeline-scan-title" className="text-sm font-bold text-white">
                Delete Visual Scan?
              </h3>
              <p className="text-xxs text-slate-400 leading-normal">
                This will delete the selected scan, remove its observations from this longitudinal
                timeline, and purge the stored photo from cloud storage.
              </p>
            </div>

            <div className="pt-2 flex items-center justify-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setScanToDeleteId(null)}
                disabled={isDeletingScan}
              >
                Keep Scan
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleConfirmDeleteScan}
                disabled={isDeletingScan}
                className="bg-rose-600 hover:bg-rose-500 text-white font-bold"
              >
                {isDeletingScan ? "Deleting..." : "Yes, Delete"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
