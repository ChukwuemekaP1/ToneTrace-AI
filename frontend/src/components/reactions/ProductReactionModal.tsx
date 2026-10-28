import React, { useState, useEffect } from "react";
import {
  AlertTriangle,
  ShieldAlert,
  CheckCircle2,
  X,
  Package,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { routineService } from "@/api/routines";
import { shelfService } from "@/api/shelf";
import {
  ReactionType,
  ReactionSeverity,
  SafetyAwareReactionResponse,
  ShelfItemResponse,
  StandaloneReactionCreateRequest,
  ApiError,
} from "@/api/types";

export interface ProductReactionModalProps {
  isOpen: boolean;
  onClose: () => void;
  onReactionCreated?: (reaction: SafetyAwareReactionResponse) => void;
  initialUserProductId?: string | null;
  initialProductId?: string | null;
  initialProductName?: string | null;
}

export const REACTION_TYPES: { value: ReactionType; label: string }[] = [
  { value: "irritation", label: "Skin Irritation" },
  { value: "redness", label: "Surface Redness" },
  { value: "breakout", label: "Breakout / Acne" },
  { value: "dryness", label: "Dryness / Tightness" },
  { value: "stinging", label: "Stinging / Burning" },
  { value: "allergic_suspect", label: "Suspected Allergy" },
  { value: "well_tolerated", label: "Well Tolerated" },
  { value: "no_visible_change", label: "No Change" },
];

export const REACTION_SEVERITIES: { value: ReactionSeverity; label: string }[] = [
  { value: "none", label: "None" },
  { value: "mild", label: "Mild" },
  { value: "moderate", label: "Moderate" },
  { value: "severe", label: "Severe" },
];

export const COMMON_SYMPTOMS = [
  "Redness",
  "Burning sensation",
  "Itching",
  "Stinging",
  "Dry patches",
  "Swelling",
  "Hives / Welts",
  "Blistering",
  "Flaking / Peeling",
];

export const CLIENT_URGENT_CARE_GUIDANCE =
  "URGENT CARE GUIDANCE: You reported a severe or rapidly worsening reaction. Stop using the suspected product(s) immediately, gently rinse the area with cool water if appropriate, and seek prompt evaluation from a qualified healthcare professional or urgent care clinic. If you experience facial, lip, tongue, or throat swelling, difficulty breathing, dizziness, blistering, or widespread hives, seek emergency medical services immediately.";

export const REACTION_DISCLAIMER_COPY =
  "User-reported observation only. Recording a reaction does not prove that a product or ingredient caused a symptom and is never a medical diagnosis of an allergic reaction or contact dermatitis.";

export const ProductReactionModal: React.FC<ProductReactionModalProps> = ({
  isOpen,
  onClose,
  onReactionCreated,
  initialUserProductId,
  initialProductId,
  initialProductName,
}) => {
  // Target Product
  const [userProductId, setUserProductId] = useState<string | null>(initialUserProductId || null);
  const [productId, setProductId] = useState<string | null>(initialProductId || null);
  const [shelfItems, setShelfItems] = useState<ShelfItemResponse[]>([]);
  const [isLoadingShelf, setIsLoadingShelf] = useState<boolean>(false);

  // Form Fields
  const [reactionType, setReactionType] = useState<ReactionType>("irritation");
  const [severity, setSeverity] = useState<ReactionSeverity>("mild");
  const [selectedSymptoms, setSelectedSymptoms] = useState<string[]>(["Redness"]);
  const [isRapidlyWorsening, setIsRapidlyWorsening] = useState<boolean>(false);
  const [suspectedIngredients, setSuspectedIngredients] = useState<string>("");
  const [notes, setNotes] = useState<string>("");

  // Submission State
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submittedReaction, setSubmittedReaction] = useState<SafetyAwareReactionResponse | null>(null);

  // Load shelf items if product reference not provided
  useEffect(() => {
    if (isOpen && !initialUserProductId && !initialProductId) {
      setIsLoadingShelf(true);
      shelfService
        .listShelfItems({ page: 1, page_size: 50 })
        .then((res) => {
          setShelfItems(res.items);
          if (res.items.length > 0 && !userProductId) {
            setUserProductId(res.items[0].id);
            if (res.items[0].product_id) {
              setProductId(res.items[0].product_id);
            }
          }
        })
        .catch(() => {
          // Non-blocking
        })
        .finally(() => setIsLoadingShelf(false));
    }
  }, [isOpen, initialUserProductId, initialProductId, userProductId]);

  if (!isOpen) return null;

  const toggleSymptom = (symptom: string) => {
    setSelectedSymptoms((prev) =>
      prev.includes(symptom) ? prev.filter((s) => s !== symptom) : [...prev, symptom]
    );
  };

  const isUrgentCondition =
    severity === "severe" ||
    isRapidlyWorsening ||
    selectedSymptoms.some((s) =>
      ["Swelling", "Hives / Welts", "Blistering"].includes(s)
    );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;

    if (!userProductId && !productId) {
      setSubmitError("Please select a shelf product or catalog item to link this reaction to.");
      return;
    }

    setIsSubmitting(true);
    setSubmitError(null);

    const suspectedList = suspectedIngredients
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s.length > 0);

    const payload: StandaloneReactionCreateRequest = {
      user_product_id: userProductId || undefined,
      product_id: productId || undefined,
      reaction_type: reactionType,
      severity: severity,
      symptoms: selectedSymptoms,
      is_rapidly_worsening: isRapidlyWorsening,
      suspected_ingredient_names: suspectedList,
      notes: notes.trim() || undefined,
      observed_at: new Date().toISOString(),
    };

    try {
      const result = await routineService.createReaction(payload);
      setSubmittedReaction(result);
      onReactionCreated?.(result);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setSubmitError(err.message || "Failed to record product reaction.");
      } else {
        setSubmitError("Failed to record reaction. Please check your connection and try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleFinish = () => {
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in"
      role="dialog"
      aria-modal="true"
      aria-labelledby="reaction-modal-title"
    >
      <div className="bg-[#0C1217] border border-white/12 rounded-2xl max-w-md w-full max-h-[90vh] overflow-y-auto p-4 space-y-4 shadow-card text-left scrollbar-thin scrollbar-thumb-white/10">
        {/* Header */}
        <div className="flex items-start justify-between gap-2 border-b border-white/8 pb-3">
          <div>
            <div className="flex items-center gap-1.5 text-rose-400 font-semibold text-xs">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>Safety & Tolerance Log</span>
            </div>
            <h2 id="reaction-modal-title" className="text-base font-bold text-white mt-0.5 tracking-tight">
              Report Product Reaction
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1 rounded-md text-sm transition-colors"
            aria-label="Close reaction dialog"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Success / Confirmation State */}
        {submittedReaction ? (
          <div className="space-y-4 py-2 text-center animate-in fade-in">
            <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mx-auto text-emerald-400">
              <CheckCircle2 className="w-6 h-6" />
            </div>

            <div className="space-y-1">
              <h3 className="text-sm font-bold text-white">Reaction Logged Successfully</h3>
              <p className="text-xs text-slate-300">
                Your report has been saved and will inform future suitability assessments.
              </p>
            </div>

            {/* Urgent Care Notice if returned or severe */}
            {submittedReaction.requires_urgent_care_guidance && (
              <div className="p-3 rounded-xl bg-rose-500/15 border border-rose-500/30 text-rose-200 text-xxs space-y-1 text-left leading-relaxed">
                <div className="flex items-center gap-1.5 font-bold text-rose-300 text-xs">
                  <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0" />
                  <span>Immediate Safety Guidance</span>
                </div>
                <p>
                  {submittedReaction.urgent_care_guidance || CLIENT_URGENT_CARE_GUIDANCE}
                </p>
              </div>
            )}

            {/* Epistemic disclaimer */}
            <div className="p-3 rounded-xl bg-[#080D11] border border-white/6 text-xxs text-slate-400 text-left leading-relaxed">
              <span className="font-semibold text-slate-300">Non-Diagnostic Note: </span>
              {submittedReaction.epistemic_disclaimer || REACTION_DISCLAIMER_COPY}
            </div>

            <Button
              type="button"
              variant="primary"
              size="md"
              className="w-full text-xs font-bold"
              onClick={handleFinish}
            >
              Done
            </Button>
          </div>
        ) : (
          /* Input Form */
          <form onSubmit={handleSubmit} className="space-y-4 text-xs">
            {submitError && (
              <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/25 text-rose-300 text-xxs flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
                <span>{submitError}</span>
              </div>
            )}

            {/* Product Target */}
            <div className="space-y-1">
              <label htmlFor="reaction-product-select" className="text-xxs font-semibold uppercase tracking-wider text-slate-400 block">
                Target Product
              </label>

              {initialProductName ? (
                <div className="p-2.5 rounded-xl bg-white/[0.04] border border-white/10 flex items-center gap-2 text-white">
                  <Package className="w-4 h-4 text-emerald-400 shrink-0" />
                  <span className="font-medium truncate">{initialProductName}</span>
                </div>
              ) : (
                <select
                  id="reaction-product-select"
                  aria-label="Select product for reaction"
                  value={userProductId || ""}
                  onChange={(e) => {
                    const selId = e.target.value;
                    setUserProductId(selId);
                    const item = shelfItems.find((s) => s.id === selId);
                    if (item && item.product_id) setProductId(item.product_id);
                  }}
                  disabled={isLoadingShelf || shelfItems.length === 0}
                  className="w-full p-2.5 rounded-xl bg-surface-elevated border border-white/10 text-xs text-white outline-none focus:border-emerald-500/50"
                >
                  {shelfItems.length === 0 ? (
                    <option value="">{isLoadingShelf ? "Loading shelf items..." : "No shelf items available"}</option>
                  ) : (
                    shelfItems.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.display_brand} {item.display_name} ({item.status})
                      </option>
                    ))
                  )}
                </select>
              )}
            </div>

            {/* Reaction Type */}
            <div className="space-y-1.5">
              <label className="text-xxs font-semibold uppercase tracking-wider text-slate-400 block">
                Observed Reaction
              </label>
              <div className="flex flex-wrap gap-1.5">
                {REACTION_TYPES.map((rt) => {
                  const isSelected = reactionType === rt.value;
                  return (
                    <button
                      key={rt.value}
                      type="button"
                      onClick={() => setReactionType(rt.value)}
                      className={`px-2.5 py-1 text-xxs rounded-lg transition-all border ${
                        isSelected
                          ? "bg-rose-500/20 text-rose-300 border-rose-500/40 font-semibold"
                          : "bg-white/[0.04] text-slate-400 border-white/8 hover:text-white"
                      }`}
                    >
                      {rt.label}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Severity */}
            <div className="space-y-1.5">
              <label className="text-xxs font-semibold uppercase tracking-wider text-slate-400 block">
                Perceived Severity
              </label>
              <div className="grid grid-cols-4 gap-1.5">
                {REACTION_SEVERITIES.map((sev) => {
                  const isSelected = severity === sev.value;
                  return (
                    <button
                      key={sev.value}
                      type="button"
                      onClick={() => setSeverity(sev.value)}
                      className={`py-1.5 text-xxs font-medium rounded-lg capitalize transition-all border text-center ${
                        isSelected
                          ? sev.value === "severe"
                            ? "bg-rose-500 text-white font-bold border-rose-400 shadow-glow"
                            : "bg-emerald-500/20 text-emerald-300 border-emerald-500/40 font-semibold"
                          : "bg-white/[0.04] text-slate-400 border-white/8 hover:text-white"
                      }`}
                    >
                      {sev.label}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Symptoms Multi-Select */}
            <div className="space-y-1.5">
              <label className="text-xxs font-semibold uppercase tracking-wider text-slate-400 block">
                Symptoms Experienced
              </label>
              <div className="flex flex-wrap gap-1.5">
                {COMMON_SYMPTOMS.map((symptom) => {
                  const isSelected = selectedSymptoms.includes(symptom);
                  return (
                    <button
                      key={symptom}
                      type="button"
                      onClick={() => toggleSymptom(symptom)}
                      className={`px-2.5 py-1 text-xxs rounded-lg transition-all border ${
                        isSelected
                          ? "bg-amber-500/20 text-amber-300 border-amber-500/40 font-semibold"
                          : "bg-white/[0.04] text-slate-400 border-white/8 hover:text-white"
                      }`}
                    >
                      {isSelected ? "✓ " : ""}{symptom}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Rapidly Worsening Flag */}
            <div className="p-3 rounded-xl bg-white/[0.03] border border-white/8">
              <label className="flex items-start gap-2.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={isRapidlyWorsening}
                  onChange={(e) => setIsRapidlyWorsening(e.target.checked)}
                  className="mt-0.5 rounded border-white/20 bg-surface text-rose-500 focus:ring-rose-500"
                />
                <div className="text-xxs space-y-0.5">
                  <span className="font-semibold text-white block">
                    Reaction is rapidly worsening or spreading
                  </span>
                  <p className="text-slate-400 text-[10px]">
                    Check this if swelling, burning, or discomfort is escalating quickly.
                  </p>
                </div>
              </label>
            </div>

            {/* Urgent Care Guidance Banner */}
            {isUrgentCondition && (
              <div className="p-3 rounded-xl bg-rose-500/15 border border-rose-500/30 text-rose-200 text-xxs space-y-1 leading-relaxed animate-in fade-in">
                <div className="flex items-center gap-1.5 font-bold text-rose-300 text-xs">
                  <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0" />
                  <span>Immediate Medical Care Notice</span>
                </div>
                <p>{CLIENT_URGENT_CARE_GUIDANCE}</p>
              </div>
            )}

            {/* Suspected Ingredients */}
            <div className="space-y-1">
              <label htmlFor="reaction-suspected-ingredients" className="text-xxs font-semibold uppercase tracking-wider text-slate-400 block">
                Suspected Ingredients (optional)
              </label>
              <input
                id="reaction-suspected-ingredients"
                type="text"
                value={suspectedIngredients}
                onChange={(e) => setSuspectedIngredients(e.target.value)}
                placeholder="e.g. Fragrance, Glycolic Acid, Retinol"
                className="w-full p-2.5 rounded-xl bg-surface-elevated border border-white/10 text-xs text-white placeholder-slate-500 outline-none focus:border-emerald-500/50"
              />
              <p className="text-[10px] text-slate-500">
                Comma-separated list of ingredients you suspect may be involved.
              </p>
            </div>

            {/* Notes */}
            <div className="space-y-1">
              <label htmlFor="reaction-notes-input" className="text-xxs font-semibold uppercase tracking-wider text-slate-400 block">
                Context & Notes (optional)
              </label>
              <textarea
                id="reaction-notes-input"
                rows={2}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Describe when symptoms began, what other products were used, etc."
                className="w-full p-2.5 rounded-xl bg-surface-elevated border border-white/10 text-xs text-white placeholder-slate-500 outline-none focus:border-emerald-500/50 resize-none"
              />
            </div>

            {/* Non-Diagnostic Disclaimer */}
            <div className="p-2.5 rounded-xl bg-[#080D11] border border-white/6 text-xxs text-slate-400 leading-relaxed">
              <span className="font-semibold text-slate-300">Non-Clinical Note: </span>
              {REACTION_DISCLAIMER_COPY}
            </div>

            {/* Submit & Cancel Buttons */}
            <div className="flex items-center gap-2 pt-1">
              <Button
                type="button"
                variant="ghost"
                size="md"
                onClick={onClose}
                disabled={isSubmitting}
                className="w-1/3 text-xs"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="primary"
                size="md"
                disabled={isSubmitting || (!userProductId && !productId)}
                isLoading={isSubmitting}
                className="w-2/3 text-xs font-bold"
              >
                {isSubmitting ? "Recording..." : "Record Reaction"}
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
