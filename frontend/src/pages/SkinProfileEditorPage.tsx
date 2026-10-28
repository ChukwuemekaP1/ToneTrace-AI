/**
 * Dedicated Skin Profile & Formulation Preferences Editor
 *
 * Route: /settings/skin-profile
 * Allows modifying skin type, concerns, goals, allergens, timezone,
 * and viewing/revoking facial scan consent using verified /me endpoints.
 */

import React, { useState, useEffect } from "react";
import {
  ArrowLeft,
  Check,
  Shield,
  Clock,
  Plus,
  Trash2,
  Camera,
  Save,
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

export interface SkinProfileEditorPageProps {
  onNavigate: (route: string) => void;
}

export const SkinProfileEditorPage: React.FC<SkinProfileEditorPageProps> = ({
  onNavigate,
}) => {
  const { refreshProfile } = useAuth();

  // Form State
  const [skinType, setSkinType] = useState<string>("");
  const [concerns, setConcerns] = useState<string[]>([]);
  const [goals, setGoals] = useState<string[]>([]);

  // Sensitivities
  const [sensitivities, setSensitivities] = useState<UserSensitivityItem[]>([]);
  const [customIngredient, setCustomIngredient] = useState("");
  const [customSeverity, setCustomSeverity] = useState("moderate");
  const [sensitivityError, setSensitivityError] = useState<string | null>(null);

  // Timezone
  const [timezone, setTimezone] = useState<string>("UTC");

  // Consent
  const [hasFacialConsent, setHasFacialConsent] = useState<boolean>(false);
  const [isUpdatingConsent, setIsUpdatingConsent] = useState<boolean>(false);
  const [consentMessage, setConsentMessage] = useState<string | null>(null);

  // Operational State
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [saveSuccess, setSaveSuccess] = useState<boolean>(false);
  const [generalError, setGeneralError] = useState<ApiError | Error | null>(null);

  const loadData = async () => {
    setIsLoading(true);
    setGeneralError(null);
    try {
      const [skinRes, sensRes, consentRes, meRes] = await Promise.allSettled([
        profileService.getSkinProfile(),
        profileService.listSensitivities(),
        profileService.listConsents(),
        profileService.getMe(),
      ]);

      if (skinRes.status === "fulfilled" && skinRes.value) {
        setSkinType(skinRes.value.skin_type || "");
        setConcerns(skinRes.value.skin_concerns || []);
        setGoals(skinRes.value.skin_goals || []);
      }

      if (sensRes.status === "fulfilled" && Array.isArray(sensRes.value)) {
        setSensitivities(sensRes.value);
      }

      if (consentRes.status === "fulfilled" && Array.isArray(consentRes.value)) {
        const scanConsent = consentRes.value.find(
          (c) => c.purpose === FACIAL_SCAN_CONSENT_PURPOSE
        );
        setHasFacialConsent(Boolean(scanConsent && scanConsent.is_granted && !scanConsent.revoked_at));
      }

      if (meRes.status === "fulfilled" && meRes.value?.profile?.timezone) {
        setTimezone(meRes.value.profile.timezone);
      } else if (typeof Intl !== "undefined" && Intl.DateTimeFormat) {
        setTimezone(Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
      }
    } catch (err) {
      setGeneralError(
        err instanceof Error ? err : new ApiError("Failed to load skin profile", 0)
      );
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
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

  const handleAddSensitivity = async (name: string, severity: string = "moderate") => {
    const trimmed = name.trim();
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
        err instanceof Error ? err.message : "Failed to record sensitivity."
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

  const handleToggleConsent = async () => {
    setIsUpdatingConsent(true);
    setConsentMessage(null);
    const targetState = !hasFacialConsent;

    try {
      const res = await profileService.updateConsent(FACIAL_SCAN_CONSENT_PURPOSE, {
        is_granted: targetState,
        policy_version: "1.0",
      });

      setHasFacialConsent(Boolean(res.is_granted && !res.revoked_at));
      setConsentMessage(
        targetState
          ? "Facial scan consent granted."
          : "Facial scan consent revoked. Associated scan media has been safely purged from storage."
      );
      await refreshProfile();
    } catch (err) {
      setGeneralError(
        err instanceof Error ? err : new Error("Failed to update privacy consent.")
      );
    } finally {
      setIsUpdatingConsent(false);
    }
  };

  const handleSaveProfile = async () => {
    setIsSaving(true);
    setSaveSuccess(false);
    setGeneralError(null);

    try {
      // 1. Update skin attributes
      await profileService.updateSkinProfile({
        skin_type: skinType || null,
        skin_concerns: concerns,
        skin_goals: goals,
      });

      // 2. Update timezone
      if (timezone) {
        await profileService.updateProfile({ timezone });
      }

      await refreshProfile();
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      setGeneralError(
        err instanceof Error ? err : new ApiError("Failed to update skin profile.", 0)
      );
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="w-full max-w-[430px] mx-auto py-8 text-center space-y-4">
        <GlassCard variant="elevated" padding="md" className="space-y-3">
          <div className="w-10 h-10 rounded-xl bg-champagne/15 border border-champagne/30 mx-auto flex items-center justify-center">
            <Sparkles className="w-5 h-5 text-champagne animate-pulse" />
          </div>
          <p className="text-xs text-slate-300">Loading your skin profile & preferences...</p>
        </GlassCard>
      </div>
    );
  }

  return (
    <div className="space-y-4 text-left pb-6">
      {/* Navigation & Header */}
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => onNavigate("/profile")}
          className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Profile</span>
        </button>
        <Chip variant="champagne" size="sm">
          Settings
        </Chip>
      </div>

      <div className="space-y-1">
        <h2 className="text-lg font-bold text-white tracking-tight">
          Skin Profile & <span className="font-serif italic font-normal text-champagne">Preferences</span>
        </h2>
        <p className="text-xs text-slate-400">
          Modify your biological skin type, sensitivities to avoid, and privacy consents.
        </p>
      </div>

      {generalError && (
        <ErrorRecovery
          error={generalError}
          title="Save Issue"
          onRetry={handleSaveProfile}
        />
      )}

      {saveSuccess && (
        <div className="p-3 rounded-xl bg-emerald-950/30 border border-emerald-500/40 text-emerald-300 text-xs flex items-center gap-2">
          <Check className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>Skin profile and preferences updated successfully.</span>
        </div>
      )}

      {/* 1. Skin Type */}
      <GlassCard variant="elevated" padding="md" className="space-y-3">
        <label id="editor-skin-type" className="block text-xs font-semibold text-slate-200">
          Skin Type
        </label>
        <div
          role="radiogroup"
          aria-labelledby="editor-skin-type"
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

      {/* 2. Concerns */}
      <GlassCard variant="default" padding="md" className="space-y-3">
        <label className="block text-xs font-semibold text-slate-200">
          Reported Skin Concerns
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

      {/* 3. Goals */}
      <GlassCard variant="default" padding="md" className="space-y-3">
        <label className="block text-xs font-semibold text-slate-200">
          Formulation Goals
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

      {/* 4. Sensitivities */}
      <GlassCard variant="default" padding="md" className="space-y-3">
        <div className="flex items-center gap-2">
          <Shield className="w-4 h-4 text-emerald-400" />
          <h3 className="text-xs font-semibold text-slate-200">Ingredient Sensitivities & Allergens</h3>
        </div>

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

        <div className="space-y-2 pt-2 border-t border-white/[0.08]">
          <div className="flex gap-2">
            <Input
              placeholder="Add ingredient avoidance..."
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

          <div className="pt-1">
            <span className="text-xxs text-slate-400 block mb-1.5">Common Allergens:</span>
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

      {/* 5. Privacy & Facial Analysis Consent Control */}
      <GlassCard variant="default" padding="md" className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Camera className="w-4 h-4 text-champagne" />
            <h3 className="text-xs font-semibold text-slate-200">Facial Scan Consent Status</h3>
          </div>
          <span
            className={`text-xxs px-2 py-0.5 rounded-full font-medium border ${
              hasFacialConsent
                ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                : "bg-slate-800 text-slate-400 border-white/10"
            }`}
          >
            {hasFacialConsent ? "Active / Granted" : "Declined / Revoked"}
          </span>
        </div>

        <p className="text-xxs text-slate-400 leading-relaxed">
          {hasFacialConsent
            ? "You have consented to AI facial skin scanning. Photos are kept in private encrypted storage. Revoking this consent immediately purges retained photo assets."
            : "Facial scanning is inactive. You can use all formulation search, shelf tracking, and routines without granting this consent."}
        </p>

        {consentMessage && (
          <div className="p-2.5 rounded-lg bg-emerald-950/20 border border-emerald-500/30 text-xxs text-emerald-300">
            {consentMessage}
          </div>
        )}

        <Button
          type="button"
          variant={hasFacialConsent ? "danger" : "secondary"}
          size="sm"
          className="w-full text-xs"
          isLoading={isUpdatingConsent}
          disabled={isUpdatingConsent}
          onClick={handleToggleConsent}
        >
          {hasFacialConsent ? "Revoke Facial Analysis Consent" : "Grant Facial Analysis Consent"}
        </Button>
      </GlassCard>

      {/* 6. Timezone Configuration */}
      <GlassCard variant="default" padding="md" className="space-y-2">
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-emerald-400" />
          <h4 className="text-xs font-semibold text-slate-200">User Timezone</h4>
        </div>
        <div className="flex items-center gap-2">
          <Input
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            placeholder="e.g. America/New_York"
            className="h-9 text-xs"
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-9 shrink-0 text-xxs"
            onClick={() => {
              if (typeof Intl !== "undefined" && Intl.DateTimeFormat) {
                setTimezone(Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
              }
            }}
          >
            Detect
          </Button>
        </div>
      </GlassCard>

      {/* Action Bar */}
      <div className="pt-2">
        <Button
          type="button"
          variant="primary"
          size="lg"
          className="w-full"
          isLoading={isSaving}
          disabled={isSaving}
          onClick={handleSaveProfile}
          leftIcon={<Save className="w-4 h-4" />}
        >
          {isSaving ? "Saving..." : "Save Profile Settings"}
        </Button>
      </div>
    </div>
  );
};
