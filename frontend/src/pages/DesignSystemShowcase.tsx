import React, { useState } from "react";
import {
  Sparkles,
  ShieldCheck,
  Search,
  Flame,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { GlassCard } from "@/components/ui/GlassCard";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import { BrandedLoading } from "@/components/ui/BrandedLoading";
import { ErrorRecovery } from "@/components/ui/ErrorRecovery";
import { EmptyState } from "@/components/ui/EmptyState";
import { ApiError } from "@/api/types";

export const DesignSystemShowcase: React.FC = () => {
  const [activeSection, setActiveSection] = useState<string>("all");
  const [demoInput, setDemoInput] = useState("");
  const [demoError, setDemoError] = useState("");
  const [showLoadingDemo, setShowLoadingDemo] = useState(false);
  const [showSimulatedError, setShowSimulatedError] = useState(false);

  const mockApiError = new ApiError(
    "Cosmetic formula verification failed: Invalid INCI nomenclature",
    422,
    "VALIDATION_ERROR",
    "req_test_8f2a1b9c",
    [{ field: "ingredients -> 0 -> inci_name", message: "Unknown chemical derivative" }]
  );

  return (
    <div className="space-y-6 text-left">
      {/* Intro Header */}
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <Chip variant="champagne" size="sm" showDot>
            Design System 1.0
          </Chip>
          <span className="text-xxs text-slate-400 font-mono">Mobile Baseline: 390px</span>
        </div>
        <h2 className="text-lg font-bold text-white tracking-tight">Component & Token Showcase</h2>
        <p className="text-xs text-slate-400 leading-relaxed">
          Living design specifications, tactile primitives, and error fallbacks for ToneTrace AI.
        </p>
      </div>

      {/* Section Filter Pills */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 no-scrollbar">
        {["all", "tokens", "buttons", "chips", "cards", "inputs", "feedback"].map((sec) => (
          <button
            key={sec}
            onClick={() => setActiveSection(sec)}
            className={`px-2.5 py-1 text-xxs font-medium rounded-lg uppercase tracking-wider transition-colors shrink-0 ${
              activeSection === sec
                ? "bg-emerald-500 text-slate-950 font-bold"
                : "bg-white/5 text-slate-400 hover:text-white"
            }`}
          >
            {sec}
          </button>
        ))}
      </div>

      {/* 1. Design Tokens */}
      {(activeSection === "all" || activeSection === "tokens") && (
        <section className="space-y-3">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
            1. Design Tokens & Palette
          </h3>
          <GlassCard variant="default" className="space-y-3">
            <div className="grid grid-cols-2 gap-2 text-xxs">
              <div className="p-2.5 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-300">
                <div className="font-bold">Emerald / Clinical</div>
                <div className="text-emerald-400/80 font-mono">#10B981</div>
              </div>
              <div className="p-2.5 rounded-xl bg-champagne/15 border border-champagne/30 text-champagne">
                <div className="font-bold">Champagne / Luxury</div>
                <div className="text-champagne/80 font-mono">#E0C39E</div>
              </div>
              <div className="p-2.5 rounded-xl bg-amber-500/15 border border-amber-500/30 text-amber-300">
                <div className="font-bold">Amber / Caution</div>
                <div className="text-amber-400/80 font-mono">#F59E0B</div>
              </div>
              <div className="p-2.5 rounded-xl bg-rose-500/15 border border-rose-500/30 text-rose-300">
                <div className="font-bold">Rose / Reaction</div>
                <div className="text-rose-400/80 font-mono">#EF4444</div>
              </div>
            </div>

            <div className="pt-2 border-t border-white/5 text-xxs text-slate-400 space-y-1">
              <div className="flex justify-between">
                <span>Type Scale:</span>
                <span className="font-mono text-slate-300">11px / 12px / 14px / 16px / 20px / 24px</span>
              </div>
              <div className="flex justify-between">
                <span>Radii:</span>
                <span className="font-mono text-slate-300">sm(6) / md(10) / lg(14) / xl(18) / 2xl(24)</span>
              </div>
              <div className="flex justify-between">
                <span>Focus Ring:</span>
                <span className="font-mono text-emerald-400">ring-2 ring-emerald-500/60 offset-2</span>
              </div>
            </div>
          </GlassCard>
        </section>
      )}

      {/* 2. Buttons */}
      {(activeSection === "all" || activeSection === "buttons") && (
        <section className="space-y-3">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
            2. Button Variants & States
          </h3>
          <GlassCard variant="default" className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <Button variant="primary" size="sm" leftIcon={<Sparkles className="w-3.5 h-3.5" />}>
                Primary Clinical
              </Button>
              <Button variant="champagne" size="sm">
                Luxury Accent
              </Button>
              <Button variant="secondary" size="sm">
                Secondary
              </Button>
              <Button variant="outline" size="sm">
                Outline
              </Button>
              <Button variant="danger" size="sm" leftIcon={<Flame className="w-3.5 h-3.5" />}>
                Danger
              </Button>
            </div>

            <div className="pt-2 border-t border-white/5 flex items-center gap-3">
              <Button variant="primary" size="md" isLoading>
                Analyzing
              </Button>
              <Button variant="secondary" size="md" disabled>
                Disabled
              </Button>
            </div>
          </GlassCard>
        </section>
      )}

      {/* 3. Chips */}
      {(activeSection === "all" || activeSection === "chips") && (
        <section className="space-y-3">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
            3. Clinical Status Chips
          </h3>
          <GlassCard variant="default" className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <Chip variant="verified" showDot>
                Evidence-Verified
              </Chip>
              <Chip variant="caution" showDot>
                Potential Irritant
              </Chip>
              <Chip variant="adverse" showDot>
                Reported Reaction
              </Chip>
              <Chip variant="champagne" showDot>
                Active Complex
              </Chip>
              <Chip variant="neutral">INCI Listing</Chip>
            </div>
          </GlassCard>
        </section>
      )}

      {/* 4. Glass Cards */}
      {(activeSection === "all" || activeSection === "cards") && (
        <section className="space-y-3">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
            4. Glassmorphic Containers
          </h3>
          <div className="space-y-2.5">
            <GlassCard variant="default">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                <h4 className="text-xs font-semibold text-white">Default Scientific Glass Card</h4>
              </div>
              <p className="text-xxs text-slate-400 mt-1">
                Translucent background with subtle border and standard backdrop blur.
              </p>
            </GlassCard>

            <GlassCard variant="accent">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-semibold text-emerald-300">Accent Highlight Container</h4>
                <Chip variant="verified" size="sm">
                  Active
                </Chip>
              </div>
              <p className="text-xxs text-emerald-200/70 mt-1">
                Subtle emerald gradient glow used for grounded AI findings and verified matches.
              </p>
            </GlassCard>

            <GlassCard variant="interactive">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-200">Interactive Tap Card</span>
                <span className="text-xxs text-emerald-400">Tap to inspect →</span>
              </div>
            </GlassCard>
          </div>
        </section>
      )}

      {/* 5. Inputs */}
      {(activeSection === "all" || activeSection === "inputs") && (
        <section className="space-y-3">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
            5. Form Inputs & Validation
          </h3>
          <GlassCard variant="default" className="space-y-3">
            <Input
              label="Product or Ingredient Search"
              placeholder="e.g. Niacinamide, CeraVe Hydrating..."
              value={demoInput}
              onChange={(e) => {
                setDemoInput(e.target.value);
                if (e.target.value.toLowerCase().includes("error")) {
                  setDemoError("Demonstration: Test validation message triggered.");
                } else {
                  setDemoError("");
                }
              }}
              error={demoError}
              helperText="Type 'error' to trigger simulated validation state."
              leftIcon={<Search className="w-4 h-4" />}
            />
          </GlassCard>
        </section>
      )}

      {/* 6. Feedback, Skeletons & Recovery */}
      {(activeSection === "all" || activeSection === "feedback") && (
        <section className="space-y-3">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
            6. Loading, Skeletons & Recovery Fallbacks
          </h3>

          <GlassCard variant="default" className="space-y-3">
            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-xs font-medium text-slate-300">Shimmer Skeleton Loaders</span>
              </div>
              <div className="space-y-1.5">
                <Skeleton variant="text" width="60%" />
                <Skeleton variant="text" />
                <div className="flex items-center gap-2 pt-1">
                  <Skeleton variant="circular" width={28} height={28} />
                  <Skeleton variant="text" width="40%" />
                </div>
              </div>
            </div>

            <div className="pt-3 border-t border-white/5 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-300">Branded Loading Demo</span>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setShowLoadingDemo(!showLoadingDemo)}
                >
                  {showLoadingDemo ? "Hide Loading" : "Trigger Loading"}
                </Button>
              </div>

              {showLoadingDemo && (
                <div className="p-3 bg-[#080C0F] rounded-xl border border-white/5">
                  <BrandedLoading
                    message="Auditing European Commission CosIng database..."
                    timeoutMs={4000}
                    onRetry={() => setShowLoadingDemo(true)}
                  />
                </div>
              )}
            </div>

            <div className="pt-3 border-t border-white/5 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-300">Error State Demo</span>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setShowSimulatedError(!showSimulatedError)}
                >
                  {showSimulatedError ? "Hide Error" : "Trigger Error"}
                </Button>
              </div>

              {showSimulatedError && (
                <ErrorRecovery
                  error={mockApiError}
                  title="Formulation Verification Blocked"
                  onRetry={() => setShowSimulatedError(false)}
                />
              )}
            </div>
          </GlassCard>

          {/* Empty State */}
          <EmptyState
            title="No Products On Your Shelf"
            description="Scan an ingredient label with OCR or search the catalog to add verified formulations to your routine."
            actionLabel="Scan Cosmetic Label"
            onAction={() => alert("Scan action triggered (showcase demo)")}
          />
        </section>
      )}
    </div>
  );
};
