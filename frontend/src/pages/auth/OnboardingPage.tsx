/**
 * Calm, Welcoming Onboarding Journey
 *
 * Implements a streamlined, accessible setup flow:
 * - Serif headline accent with calm tone
 * - Chip selection for supported skin types (dry, oily, combination, normal, sensitive)
 * - Checkboxes for supported skin concerns & goals
 * - Minimal allergen / ingredient sensitivity input
 * - Separate, explicit facial-analysis consent (NOT pre-checked, optional, decline never blocks)
 * - Auto-detected browser timezone saved via verified PATCH /me
 * - Incomplete save/resume and retry without clearing user inputs
 */

import React, { useState, useEffect } from "react";
import {
  ArrowRight,
  ArrowLeft,
  Check,
  Shield,
  Clock,
  Plus,
  Trash2,
  Camera,
  Sparkles,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { profileService } from "@/api/profile";
import {
  SUPPORTED_SKIN_TYPES,
  SUPPORTED_SKIN_CONCERNS,
  SUPPORTED_SKIN_GOALS,
  COMMON_SENSITIVITIES,
  FACIAL_SCAN_CONSENT_PURPOSE,
} from "@/api/profile-constants";
import { GlassCard } from "@/components/ui/GlassCard";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Chip } from "@/components/ui/Chip";
import { ErrorRecovery } from "@/components/ui/ErrorRecovery";
import { ApiError, UserSensitivityItem } from "@/api/types";

export interface OnboardingPageProps {
  onNavigate: (route: string) => void;
}

export const OnboardingPage: React.FC<OnboardingPageProps> = ({ onNavigate }) => {
  const { user, summary, refreshProfile } = useAuth();

  // Wizard step: 1 = Skin Attributes, 2 = Sensitivities, 3 = Privacy & Consent
  const [step, setStep] = useState<1 | 2 | 3>(1);

  // Form State
  const [skinType, setSkinType] = useState<string>("");
  const [concerns, setConcerns] = useState<string[]>([]);
  const [goals, setGoals] = useState<string[]>([]);

  // Sensitivities state
  const [sensitivities, setSensitivities] = useState<UserSensitivityItem[]>([]);
  const [customIngredient, setCustomIngredient] = useState("");
  const [customSeverity, setCustomSeverity] = useState("moderate");
  const [sensitivityError, setSensitivityError] = useState<string | null>(null);

  // Privacy & Consent state
  const [facialConsentGranted, setFacialConsentGranted] = useState<boolean>(false);
  const [browserTimezone, setBrowserTimezone] = useState<string>("UTC");

  // Operational State
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [generalError, setGeneralError] = useState<ApiError | Error | null>(null);

  // Load existing records first to support save & resume
  useEffect(() => {
    let isMounted = true;

    const loadExistingData = async () => {
      setIsLoading(true);
      try {
        // Resolve browser timezone
        if (typeof Intl !== "undefined" && Intl.DateTimeFormat) {
          const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
          if (tz) setBrowserTimezone(tz);
        }

        // Parallel load from verified endpoints
        const [skinRes, sensRes, consentRes] = await Promise.allSettled([
          profileService.getSkinProfile(),
          profileService.listSensitivities(),
          profileService.listConsents(),
        ]);

        if (!isMounted) return;

        if (skinRes.status === "fulfilled" && skinRes.value) {
          if (skinRes.value.skin_type) setSkinType(skinRes.value.skin_type);
          if (skinRes.value.skin_concerns) setConcerns(skinRes.value.skin_concerns);
          if (skinRes.value.skin_goals) setGoals(skinRes.value.skin_goals);
        }

        if (sensRes.status === "fulfilled" && Array.isArray(sensRes.value)) {
          setSensitivities(sensRes.value);
        }

        if (consentRes.status === "fulfilled" && Array.isArray(consentRes.value)) {
          const scanConsent = consentRes.value.find(
            (c) => c.purpose === FACIAL_SCAN_CONSENT_PURPOSE
          );
          if (scanConsent) {
            setFacialConsentGranted(Boolean(scanConsent.is_granted && !scanConsent.revoked_at));
          }
        }
      } catch (err) {
        if (isMounted) {
          setGeneralError(
            err instanceof Error ? err : new ApiError("Failed to load profile data", 0)
          );
        }
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };

    loadExistingData();

    return () => {
      isMounted = false;
    };
  }, []);

  const toggleConcern = (concernId: string) => {
    setConcerns((prev) =>
      prev.includes(concernId) ? prev.filter((c) => c !== concernId) : [...prev, concernId]
    );
  };

  const toggleGoal = (goalId: string) => {
    setGoals((prev) =>
      prev.includes(goalId) ? prev.filter((g) => g !== goalId) : [...prev, goalId]
    );
  };

  const handleAddSensitivity = async (ingredientName: string, severity: string = "moderate") => {
    const trimmed = ingredientName.trim();
    if (!trimmed) return;

    setSensitivityError(null);
    try {
      const created = await profileService.addSensitivity({
        ingredient_name: trimmed,
        severity,
      });
      setSensitivities((prev) => [...prev, created]);
      setCustomIngredient("");
    } catch (err) {
      setSensitivityError(
        err instanceof Error ? err.message : "Failed to record ingredient sensitivity."
      );
    }
  };

  const handleDeleteSensitivity = async (id: string) => {
    try {
      await profileService.deleteSensitivity(id);
      setSensitivities((prev) => prev.filter((s) => s.id !== id));
    } catch (err) {
      setGeneralError(err instanceof Error ? err : new Error("Failed to remove sensitivity."));
    }
  };

  // Save current step data without losing entered progress
  const saveCurrentData = async (): Promise<boolean> => {
    setIsSubmitting(true);
    setGeneralError(null);
    try {
      // 1. Update skin profile with verified fields
      await profileService.updateSkinProfile({
        skin_type: skinType || null,
        skin_concerns: concerns,
        skin_goals: goals,
      });

      // 2. Update timezone if resolved
      if (browserTimezone) {
        try {
          await profileService.updateProfile({ timezone: browserTimezone });
        } catch {
          // Non-fatal if timezone fails
        }
      }

      // 3. Update facial scan consent (explicitly sent if user interacted)
      await profileService.updateConsent(FACIAL_SCAN_CONSENT_PURPOSE, {
        is_granted: facialConsentGranted,
        policy_version: "1.0",
      });

      // Refresh Auth Context summary state
      await refreshProfile();
      return true;
    } catch (err) {
      setGeneralError(
        err instanceof Error ? err : new ApiError("Failed to save profile changes.", 0)
      );
      return false;
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleFinish = async () => {
    const success = await saveCurrentData();
    if (success) {
      onNavigate("/");
    }
  };

  const handleSaveAndExit = async () => {
    await saveCurrentData();
    onNavigate("/");
  };

  const displayName = summary?.profile?.display_name || user?.email?.split("@")[0] || "Friend";

  if (isLoading) {
    return (
      <div className="w-full max-w-[430px] mx-auto py-8 text-center space-y-4">
        <GlassCard variant="elevated" padding="md" className="space-y-3">
          <div className="w-10 h-10 rounded-xl bg-champagne/15 border border-champagne/30 mx-auto flex items-center justify-center">
            <Sparkles className="w-5 h-5 text-champagne animate-pulse" />
          </div>
          <p className="text-xs text-slate-300">Loading your profile preferences...</p>
        </GlassCard>
      </div>
    );
  }

  return (
    <div className="w-full max-w-[430px] mx-auto py-2 space-y-4 text-left">
      {/* Header Accent */}
      <div className="space-y-1 pt-1">
        <div className="flex items-center justify-between">
          <Chip variant="champagne" size="sm">
            Step {step} of 3
          </Chip>
          <button
            type="button"
            onClick={handleSaveAndExit}
            className="text-xxs text-slate-400 hover:text-slate-200 underline transition-colors"
          >
            Save & Exit
          </button>
        </div>
        <h2 className="text-xl font-bold tracking-tight text-white leading-tight">
          Welcome, <span className="font-serif italic font-normal text-champagne">{displayName}</span>
        </h2>
        <p className="text-xs text-slate-400 leading-relaxed">
          {step === 1 && "Select your biological skin type and primary concerns to calibrate formulation checks."}
          {step === 2 && "Add ingredients you are allergic to or prefer to avoid during product searches."}
          {step === 3 && "Review privacy settings, facial image processing, and regional timezone."}
        </p>
      </div>

      {generalError && (
        <ErrorRecovery
          error={generalError}
          title="Onboarding Save Error"
          onRetry={saveCurrentData}
        />
      )}

      {/* STEP 1: Skin Type & Concerns */}
      {step === 1 && (
        <div className="space-y-4 animate-in fade-in duration-200">
          <GlassCard variant="elevated" padding="md" className="space-y-3">
            <label id="skin-type-label" className="block text-xs font-semibold text-slate-200">
              Skin Type <span className="text-emerald-400 font-normal text-xxs">(Select one)</span>
            </label>
            <div
              role="radiogroup"
              aria-labelledby="skin-type-label"
              className="grid grid-cols-2 gap-2"
            >
              {SUPPORTED_SKIN_TYPES.map((type) => {
                const isSelected = skinType === type.id;
                return (
                  <button
                    key={type.id}
                    type="button"
                    role="radio"
                    aria-checked={isSelected}
                    onClick={() => setSkinType(type.id)}
                    className={`p-2.5 rounded-xl text-left border transition-all text-xs flex flex-col justify-between ${
                      isSelected
                        ? "bg-emerald-950/40 border-emerald-500/60 shadow-glow text-white"
                        : "bg-[#0C1217] border-white/10 hover:border-white/20 text-slate-300"
                    }`}
                  >
                    <div className="flex items-center justify-between w-full">
                      <span className="font-medium">{type.label}</span>
                      {isSelected && <Check className="w-3.5 h-3.5 text-emerald-400" />}
                    </div>
                    <span className="text-xxs text-slate-400 mt-1 line-clamp-1 leading-normal">
                      {type.description}
                    </span>
                  </button>
                );
              })}
            </div>
          </GlassCard>

          <GlassCard variant="default" padding="md" className="space-y-3">
            <label className="block text-xs font-semibold text-slate-200">
              Skin Concerns & Focus Areas <span className="text-slate-400 font-normal text-xxs">(Select all that apply)</span>
            </label>
            <div className="grid grid-cols-2 gap-2">
              {SUPPORTED_SKIN_CONCERNS.map((item) => {
                const isChecked = concerns.includes(item.id);
                return (
                  <button
                    key={item.id}
                    type="button"
                    role="checkbox"
                    aria-checked={isChecked}
                    onClick={() => toggleConcern(item.id)}
                    className={`p-2 rounded-xl border text-left text-xs transition-all flex items-center justify-between ${
                      isChecked
                        ? "bg-emerald-950/30 border-emerald-500/50 text-white"
                        : "bg-[#0B0F13] border-white/10 text-slate-300 hover:border-white/20"
                    }`}
                  >
                    <span className="truncate pr-1 text-xxs">{item.label}</span>
                    {isChecked && <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />}
                  </button>
                );
              })}
            </div>
          </GlassCard>

          <GlassCard variant="default" padding="md" className="space-y-3">
            <label className="block text-xs font-semibold text-slate-200">
              Skincare Goals <span className="text-slate-400 font-normal text-xxs">(Optional)</span>
            </label>
            <div className="grid grid-cols-2 gap-2">
              {SUPPORTED_SKIN_GOALS.map((item) => {
                const isChecked = goals.includes(item.id);
                return (
                  <button
                    key={item.id}
                    type="button"
                    role="checkbox"
                    aria-checked={isChecked}
                    onClick={() => toggleGoal(item.id)}
                    className={`p-2 rounded-xl border text-left text-xs transition-all flex items-center justify-between ${
                      isChecked
                        ? "bg-champagne/15 border-champagne/40 text-champagne-light"
                        : "bg-[#0B0F13] border-white/10 text-slate-300 hover:border-white/20"
                    }`}
                  >
                    <span className="truncate pr-1 text-xxs">{item.label}</span>
                    {isChecked && <Check className="w-3.5 h-3.5 text-champagne shrink-0" />}
                  </button>
                );
              })}
            </div>
          </GlassCard>

          <Button
            type="button"
            variant="primary"
            size="lg"
            className="w-full"
            disabled={!skinType}
            onClick={() => setStep(2)}
            rightIcon={<ArrowRight className="w-4 h-4" />}
          >
            Continue to Sensitivities
          </Button>
        </div>
      )}

      {/* STEP 2: Ingredient Sensitivities */}
      {step === 2 && (
        <div className="space-y-4 animate-in fade-in duration-200">
          <GlassCard variant="elevated" padding="md" className="space-y-3">
            <div className="flex items-center gap-2">
              <Shield className="w-4 h-4 text-emerald-400" />
              <h3 className="text-xs font-semibold text-slate-200">Known Cosmetic Sensitivities</h3>
            </div>
            <p className="text-xxs text-slate-400 leading-relaxed">
              ToneTrace will automatically flag these ingredients across product labels and catalog searches.
            </p>

            {/* Current Sensitivities List */}
            {sensitivities.length > 0 && (
              <div className="space-y-1.5 pt-1">
                {sensitivities.map((s) => (
                  <div
                    key={s.id}
                    className="flex items-center justify-between p-2 rounded-lg bg-[#0C1217] border border-white/10 text-xs"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-white font-medium">{s.ingredient_name}</span>
                      <span className="text-xxs px-1.5 py-0.5 rounded bg-rose-950/40 text-rose-300 border border-rose-500/30 capitalize">
                        {s.severity}
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleDeleteSensitivity(s.id)}
                      className="text-slate-400 hover:text-rose-400 p-1"
                      title="Remove sensitivity"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Custom Input */}
            <div className="space-y-2 pt-2 border-t border-white/[0.08]">
              <div className="flex gap-2">
                <Input
                  placeholder="Enter ingredient name (e.g. Fragrance)"
                  value={customIngredient}
                  onChange={(e) => setCustomIngredient(e.target.value)}
                  className="h-9 text-xs"
                />
                <select
                  value={customSeverity}
                  onChange={(e) => setCustomSeverity(e.target.value)}
                  className="h-9 px-2 bg-[#0B0F13] border border-white/10 rounded-xl text-xxs text-slate-200 focus-visible:outline-none"
                  aria-label="Sensitivity severity"
                >
                  <option value="low">Low</option>
                  <option value="moderate">Moderate</option>
                  <option value="high">High</option>
                  <option value="severe">Severe</option>
                </select>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  className="h-9 px-3 shrink-0"
                  disabled={!customIngredient.trim()}
                  onClick={() => handleAddSensitivity(customIngredient, customSeverity)}
                >
                  <Plus className="w-4 h-4" />
                </Button>
              </div>

              {sensitivityError && (
                <p className="text-xxs text-rose-400">{sensitivityError}</p>
              )}

              {/* Quick Add Suggestions */}
              <div className="pt-2">
                <span className="text-xxs text-slate-400 block mb-1.5">Common Allergens (Tap to Add):</span>
                <div className="flex flex-wrap gap-1.5">
                  {COMMON_SENSITIVITIES.map((name) => {
                    const alreadyAdded = sensitivities.some(
                      (s) => s.ingredient_name.toLowerCase() === name.toLowerCase()
                    );
                    if (alreadyAdded) return null;
                    return (
                      <button
                        key={name}
                        type="button"
                        onClick={() => handleAddSensitivity(name, "moderate")}
                        className="text-xxs px-2.5 py-1 rounded-full bg-[#121921] border border-white/10 text-slate-300 hover:text-white hover:border-emerald-500/40 transition-colors flex items-center gap-1"
                      >
                        <Plus className="w-2.5 h-2.5 text-emerald-400" />
                        <span>{name}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          </GlassCard>

          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="lg"
              className="w-1/3"
              onClick={() => setStep(1)}
              leftIcon={<ArrowLeft className="w-4 h-4" />}
            >
              Back
            </Button>
            <Button
              type="button"
              variant="primary"
              size="lg"
              className="w-2/3"
              onClick={() => setStep(3)}
              rightIcon={<ArrowRight className="w-4 h-4" />}
            >
              Continue to Privacy
            </Button>
          </div>
        </div>
      )}

      {/* STEP 3: Privacy, Facial Scan Consent & Timezone */}
      {step === 3 && (
        <div className="space-y-4 animate-in fade-in duration-200">
          {/* Facial Scan Consent Card (Separate from general terms, NOT pre-checked) */}
          <GlassCard variant="elevated" padding="md" className="space-y-3">
            <div className="flex items-start gap-3">
              <div className="w-9 h-9 rounded-xl bg-champagne/15 border border-champagne/30 flex items-center justify-center text-champagne shrink-0">
                <Camera className="w-4 h-4" />
              </div>
              <div className="min-w-0">
                <h3 className="text-xs font-semibold text-white">Facial Image Analysis Consent</h3>
                <span className="text-xxs text-amber-400">Optional · Explicit Consent</span>
              </div>
            </div>

            <p className="text-xxs text-slate-300 leading-relaxed bg-[#0C1217] p-2.5 rounded-xl border border-white/[0.08]">
              ToneTrace offers optional AI-assisted skin scanning. When you upload photos of your face, they are processed in private, encrypted storage solely to extract surface skin observations (e.g. redness, barrier health). Images are never sold or used for public AI model training.
            </p>

            <div className="pt-1">
              <label className="flex items-start gap-2.5 p-2 rounded-xl bg-[#11171E] border border-white/10 cursor-pointer hover:border-emerald-500/30 transition-colors">
                <input
                  type="checkbox"
                  checked={facialConsentGranted}
                  onChange={(e) => setFacialConsentGranted(e.target.checked)}
                  className="mt-0.5 rounded border-white/20 bg-slate-900 text-emerald-500 focus:ring-emerald-500 w-4 h-4"
                />
                <span className="text-xxs text-slate-200 leading-normal select-none">
                  I consent to ToneTrace analyzing my uploaded facial photos for skin formulation evaluation. (You may decline or revoke this anytime in Profile settings).
                </span>
              </label>
            </div>

            <div className="p-2 rounded-lg bg-emerald-950/20 border border-emerald-500/20 text-xxs text-emerald-300">
              Declining this consent does not block shelf tracking, routine reminders, or ingredient safety analysis.
            </div>
          </GlassCard>

          {/* Timezone Configuration */}
          <GlassCard variant="default" padding="md" className="space-y-2">
            <div className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-emerald-400" />
              <h4 className="text-xs font-semibold text-slate-200">Routine Timezone</h4>
            </div>
            <p className="text-xxs text-slate-400">
              Resolved from your browser for daily morning and evening reminders:
            </p>
            <div className="flex items-center justify-between p-2 rounded-lg bg-[#0C1217] border border-white/10 text-xs">
              <span className="font-mono text-slate-200 text-xxs">{browserTimezone}</span>
              <span className="text-xxs text-emerald-400">Auto-detected</span>
            </div>
          </GlassCard>

          <div className="flex gap-2 pt-1">
            <Button
              type="button"
              variant="outline"
              size="lg"
              className="w-1/3"
              onClick={() => setStep(2)}
              leftIcon={<ArrowLeft className="w-4 h-4" />}
            >
              Back
            </Button>
            <Button
              type="button"
              variant="champagne"
              size="lg"
              className="w-2/3"
              isLoading={isSubmitting}
              disabled={isSubmitting}
              onClick={handleFinish}
              rightIcon={<Check className="w-4 h-4" />}
            >
              Complete Setup
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};
