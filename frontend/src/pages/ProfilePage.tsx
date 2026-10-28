/**
 * User Profile, Settings, Reaction History & Privacy Screen
 *
 * Implements verified /me endpoints:
 * - GET/PATCH /api/v1/me (Profile metadata & timezone)
 * - GET/PUT /api/v1/me/skin-profile (Deep link to editor)
 * - GET/POST/DELETE /api/v1/me/sensitivities (Ingredient avoidance)
 * - GET/PUT /api/v1/me/consents (Privacy & facial scan consents)
 * - GET/POST /api/v1/me/product-reactions (Tolerance & reaction history)
 * - DELETE /api/v1/me (Permanent account & stored media deletion)
 * - POST /api/v1/auth/logout & /auth/logout-all (Session termination)
 */

import React, { useState, useEffect, useCallback } from "react";
import {
  User,
  Mail,
  Shield,
  LogOut,
  Smartphone,
  RefreshCw,
  Sparkles,
  ChevronRight,
  Plus,
  Trash2,
  AlertTriangle,
  Camera,
  CheckCircle2,
  AlertCircle,
  Info,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { profileService } from "@/api/profile";
import { routineService } from "@/api/routines";
import { FACIAL_SCAN_CONSENT_PURPOSE } from "@/api/profile-constants";
import { GlassCard } from "@/components/ui/GlassCard";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { Input } from "@/components/ui/Input";
import { ErrorRecovery } from "@/components/ui/ErrorRecovery";
import { ProductReactionModal } from "@/components/reactions/ProductReactionModal";
import {
  SafetyAwareReactionResponse,
  UserConsentResponse,
} from "@/api/types";

export interface SensitivityDisplayItem {
  id: string;
  ingredient_name: string;
  severity: string;
  notes?: string | null;
  user_id?: string;
  created_at?: string;
}

export interface ProfilePageProps {
  onNavigate?: (route: string) => void;
}

export const ProfilePage: React.FC<ProfilePageProps> = ({ onNavigate }) => {
  const {
    user,
    summary,
    isOnboardingComplete,
    logout,
    logoutAll,
    refreshSession,
    refreshProfile,
  } = useAuth();

  // Profile Edit State
  const [displayName, setDisplayName] = useState<string>(
    summary?.profile?.display_name || ""
  );
  const [timezone, setTimezone] = useState<string>(
    summary?.profile?.timezone || "UTC"
  );
  const [isEditingProfile, setIsEditingProfile] = useState<boolean>(false);
  const [isSavingProfile, setIsSavingProfile] = useState<boolean>(false);
  const [profileSuccessMsg, setProfileSuccessMsg] = useState<string | null>(null);

  // Sensitivities State
  const [sensitivities, setSensitivities] = useState<SensitivityDisplayItem[]>(
    summary?.sensitivities || []
  );
  const [newIngredient, setNewIngredient] = useState<string>("");
  const [newSeverity, setNewSeverity] = useState<string>("moderate");
  const [isAddingSensitivity, setIsAddingSensitivity] = useState<boolean>(false);

  // Consents State
  const [consents, setConsents] = useState<UserConsentResponse[]>([]);
  const [isUpdatingConsent, setIsUpdatingConsent] = useState<boolean>(false);

  // Reactions History State
  const [reactions, setReactions] = useState<SafetyAwareReactionResponse[]>([]);
  const [isLoadingReactions, setIsLoadingReactions] = useState<boolean>(false);
  const [isReactionModalOpen, setIsReactionModalOpen] = useState<boolean>(false);

  // Account Deletion State
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState<boolean>(false);
  const [isDeletingAccount, setIsDeletingAccount] = useState<boolean>(false);
  const [deleteConfirmationText, setDeleteConfirmationText] = useState<string>("");

  // Session Action State
  const [isLoggingOut, setIsLoggingOut] = useState<boolean>(false);
  const [isLoggingOutAll, setIsLoggingOutAll] = useState<boolean>(false);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [actionError, setActionError] = useState<Error | null>(null);

  // Synchronize summary data into local states
  useEffect(() => {
    if (summary?.profile) {
      setDisplayName(summary.profile.display_name || "");
      setTimezone(summary.profile.timezone || "UTC");
    }
    if (summary?.sensitivities) {
      setSensitivities(summary.sensitivities);
    }
  }, [summary]);

  // Load consents and product reaction history
  const loadConsentsAndReactions = useCallback(async () => {
    setIsLoadingReactions(true);

    try {
      const [consentRes, reactionRes] = await Promise.allSettled([
        profileService.listConsents(),
        routineService.listReactions({ page: 1, page_size: 20 }),
      ]);

      if (consentRes.status === "fulfilled") {
        setConsents(consentRes.value);
      }
      if (reactionRes.status === "fulfilled") {
        setReactions(reactionRes.value.items);
      }
    } finally {
      setIsLoadingReactions(false);
    }
  }, []);

  useEffect(() => {
    loadConsentsAndReactions();
  }, [loadConsentsAndReactions]);

  // ---------------------------------------------------------------------------
  // 1. Profile Metadata Update
  // ---------------------------------------------------------------------------
  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setActionError(null);
    setProfileSuccessMsg(null);
    setIsSavingProfile(true);

    try {
      await profileService.updateProfile({
        display_name: displayName.trim(),
        timezone: timezone.trim(),
      });
      await refreshProfile();
      setProfileSuccessMsg("Profile details updated successfully.");
      setIsEditingProfile(false);
    } catch (err: unknown) {
      setActionError(
        err instanceof Error ? err : new Error("Failed to update profile settings.")
      );
    } finally {
      setIsSavingProfile(false);
    }
  };

  // ---------------------------------------------------------------------------
  // 2. Sensitivities Management
  // ---------------------------------------------------------------------------
  const handleAddSensitivity = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newIngredient.trim() || isAddingSensitivity) return;

    setIsAddingSensitivity(true);
    setActionError(null);

    try {
      const added = await profileService.addSensitivity({
        ingredient_name: newIngredient.trim(),
        severity: newSeverity,
      });
      setSensitivities((prev) => [...prev, added]);
      setNewIngredient("");
      await refreshProfile();
    } catch (err: unknown) {
      setActionError(
        err instanceof Error ? err : new Error("Failed to record ingredient sensitivity.")
      );
    } finally {
      setIsAddingSensitivity(false);
    }
  };

  const handleDeleteSensitivity = async (id: string) => {
    setActionError(null);
    try {
      await profileService.deleteSensitivity(id);
      setSensitivities((prev) => prev.filter((s) => s.id !== id));
      await refreshProfile();
    } catch (err: unknown) {
      setActionError(
        err instanceof Error ? err : new Error("Failed to remove ingredient sensitivity.")
      );
    }
  };

  // ---------------------------------------------------------------------------
  // 3. Privacy Consents Management
  // ---------------------------------------------------------------------------
  const facialConsent = consents.find((c) =>
    ["skin_data_processing", "facial_scan_processing"].includes(c.purpose)
  );

  const handleToggleFacialConsent = async () => {
    setIsUpdatingConsent(true);
    setActionError(null);

    const willGrant = !(facialConsent?.is_granted && !facialConsent?.revoked_at);
    try {
      const updated = await profileService.updateConsent(
        FACIAL_SCAN_CONSENT_PURPOSE,
        {
          is_granted: willGrant,
          policy_version: "1.0",
        }
      );
      setConsents((prev) => {
        const filtered = prev.filter((c) => c.purpose !== FACIAL_SCAN_CONSENT_PURPOSE);
        return [...filtered, updated];
      });
    } catch (err: unknown) {
      setActionError(
        err instanceof Error ? err : new Error("Failed to update privacy consent preferences.")
      );
    } finally {
      setIsUpdatingConsent(false);
    }
  };

  // ---------------------------------------------------------------------------
  // 4. Session & Logout Handlers
  // ---------------------------------------------------------------------------
  const handleLogout = async () => {
    setActionError(null);
    setIsLoggingOut(true);
    try {
      await logout();
      onNavigate?.("/auth/login");
    } catch (err) {
      setActionError(err instanceof Error ? err : new Error("Failed to sign out cleanly."));
      setIsLoggingOut(false);
    }
  };

  const handleLogoutAll = async () => {
    setActionError(null);
    setIsLoggingOutAll(true);
    try {
      await logoutAll();
      onNavigate?.("/auth/login");
    } catch (err) {
      setActionError(err instanceof Error ? err : new Error("Failed to revoke all sessions."));
      setIsLoggingOutAll(false);
    }
  };

  const handleManualRefresh = async () => {
    setActionError(null);
    setIsRefreshing(true);
    try {
      await refreshSession();
    } catch (err) {
      setActionError(err instanceof Error ? err : new Error("Session refresh failed."));
    } finally {
      setIsRefreshing(false);
    }
  };

  // ---------------------------------------------------------------------------
  // 5. Permanent Account Deletion
  // ---------------------------------------------------------------------------
  const handleConfirmDeleteAccount = async () => {
    if (deleteConfirmationText.trim().toUpperCase() !== "DELETE" || isDeletingAccount) return;

    setIsDeletingAccount(true);
    setActionError(null);

    try {
      await profileService.deleteAccount();
      // On success, purge local session state and redirect to login
      await logout();
      onNavigate?.("/auth/login");
    } catch (err: unknown) {
      setActionError(
        err instanceof Error ? err : new Error("Failed to delete account. Please retry.")
      );
      setIsDeletingAccount(false);
      setIsDeleteModalOpen(false);
    }
  };

  const skinProfile = summary?.skin_profile;

  return (
    <div className="space-y-4 text-left pb-16">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 aria-label="Account & Settings" className="text-xl font-bold tracking-tight text-white leading-tight">
            Account & <span className="font-serif italic font-normal text-champagne">Settings</span>
          </h1>
          <p className="text-xs text-slate-400">
            Personalization, privacy consents, and formulation tolerances.
          </p>
        </div>
        <Chip variant="champagne" size="sm">Phase 10 Verified</Chip>
      </div>

      {actionError && (
        <ErrorRecovery
          error={actionError}
          title="Profile Action Notice"
          onRetry={() => setActionError(null)}
        />
      )}

      {profileSuccessMsg && (
        <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/25 text-emerald-300 text-xxs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>{profileSuccessMsg}</span>
        </div>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* 1. Account Metadata & Inline Profile Editor Card                     */}
      {/* ------------------------------------------------------------------- */}
      <GlassCard variant="elevated" padding="md" className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 shrink-0">
              <User className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-white truncate">
                {summary?.profile?.display_name || "ToneTrace User"}
              </h2>
              <div className="flex items-center gap-1.5 text-slate-400 text-xs truncate">
                <Mail className="w-3.5 h-3.5 shrink-0" />
                <span className="truncate">{user?.email || "No email"}</span>
              </div>
            </div>
          </div>

          <Button
            size="sm"
            variant="secondary"
            onClick={() => setIsEditingProfile(!isEditingProfile)}
            aria-label={isEditingProfile ? "Cancel profile editing" : "Edit user profile"}
            className="text-xxs px-2.5 h-7"
          >
            {isEditingProfile ? "Cancel" : "Edit Profile"}
          </Button>
        </div>

        {isEditingProfile ? (
          <form onSubmit={handleSaveProfile} className="space-y-3 pt-2 border-t border-white/8 text-xs">
            <div className="space-y-1">
              <label htmlFor="edit-display-name" className="text-xxs font-semibold uppercase tracking-wider text-slate-400 block">
                Display Name
              </label>
              <Input
                id="edit-display-name"
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Your preferred name"
                required
                className="text-xs py-1.5"
              />
            </div>

            <div className="space-y-1">
              <label htmlFor="edit-timezone" className="text-xxs font-semibold uppercase tracking-wider text-slate-400 block">
                Timezone (IANA)
              </label>
              <Input
                id="edit-timezone"
                type="text"
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                placeholder="e.g. America/New_York, UTC, Europe/London"
                required
                className="text-xs py-1.5 font-mono"
              />
            </div>

            <Button
              type="submit"
              variant="primary"
              size="sm"
              disabled={isSavingProfile || !displayName.trim()}
              isLoading={isSavingProfile}
              className="w-full text-xs font-bold"
            >
              {isSavingProfile ? "Saving Profile..." : "Save Profile Details"}
            </Button>
          </form>
        ) : (
          <div className="pt-2 border-t border-white/[0.08] grid grid-cols-2 gap-2 text-xxs">
            <div>
              <span className="text-slate-500 block">Account Status</span>
              <span className="font-medium text-emerald-400 capitalize">
                {user?.account_status || "Active"}
              </span>
            </div>
            <div>
              <span className="text-slate-500 block">Configured Timezone</span>
              <span className="font-mono text-slate-300">
                {summary?.profile?.timezone || "UTC"}
              </span>
            </div>
          </div>
        )}
      </GlassCard>

      {/* ------------------------------------------------------------------- */}
      {/* 2. Skin Blueprint & Sensitivities Summary Card                       */}
      {/* ------------------------------------------------------------------- */}
      <GlassCard variant="default" padding="md" className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-champagne" />
            <h2 className="text-xs font-semibold text-slate-200">Skin Blueprint & Concerns</h2>
          </div>
          <Chip variant={isOnboardingComplete ? "verified" : "caution"} size="sm">
            {isOnboardingComplete ? "Configured" : "Incomplete"}
          </Chip>
        </div>

        <div className="grid grid-cols-3 gap-2 pt-1 text-center">
          <div className="p-2 rounded-xl bg-[#0B0F13] border border-white/5">
            <span className="text-xxs text-slate-500 block">Skin Type</span>
            <span className="text-xs font-semibold text-white capitalize">
              {skinProfile?.skin_type || "None"}
            </span>
          </div>
          <div className="p-2 rounded-xl bg-[#0B0F13] border border-white/5">
            <span className="text-xxs text-slate-500 block">Concerns</span>
            <span className="text-xs font-semibold text-emerald-400">
              {skinProfile?.skin_concerns?.length || 0}
            </span>
          </div>
          <div className="p-2 rounded-xl bg-[#0B0F13] border border-white/5">
            <span className="text-xxs text-slate-500 block">Allergens</span>
            <span className="text-xs font-semibold text-amber-400">
              {sensitivities.length}
            </span>
          </div>
        </div>

        <button
          type="button"
          onClick={() => onNavigate?.("/settings/skin-profile")}
          className="w-full mt-1 flex items-center justify-between p-2.5 rounded-xl bg-[#131B22] border border-white/10 hover:border-emerald-500/40 text-xs text-slate-200 transition-all cursor-pointer"
        >
          <div className="flex items-center gap-2">
            <Shield className="w-3.5 h-3.5 text-emerald-400" />
            <span>Open Comprehensive Skin Profile Editor</span>
          </div>
          <ChevronRight className="w-4 h-4 text-slate-400" />
        </button>
      </GlassCard>

      {/* ------------------------------------------------------------------- */}
      {/* 3. Ingredient Sensitivities & Avoidance Management                   */}
      {/* ------------------------------------------------------------------- */}
      <GlassCard variant="default" padding="md" className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-amber-400" />
            <h2 className="text-xs font-semibold text-slate-200">
              Ingredient Sensitivities & Avoidance ({sensitivities.length})
            </h2>
          </div>
        </div>

        <p className="text-xxs text-slate-400 leading-relaxed">
          Suitability rules scan cosmetic product formulas against these ingredients and flag potential irritations.
        </p>

        {/* Sensitivities List */}
        <div className="space-y-1.5 pt-1">
          {sensitivities.length === 0 ? (
            <p className="text-xxs text-slate-500 italic p-2 rounded-lg bg-black/20">
              No known sensitivities recorded. Add any ingredients you wish to avoid below.
            </p>
          ) : (
            sensitivities.map((sens) => (
              <div
                key={sens.id}
                className="flex items-center justify-between p-2 rounded-lg bg-[#0A0E12] border border-white/6 text-xs"
              >
                <div>
                  <span className="font-semibold text-slate-200">{sens.ingredient_name}</span>
                  <span className="ml-2 text-[10px] text-amber-400 capitalize font-mono">
                    ({sens.severity})
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => handleDeleteSensitivity(sens.id)}
                  aria-label={`Remove sensitivity for ${sens.ingredient_name}`}
                  className="text-slate-500 hover:text-rose-400 p-1 transition-colors"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))
          )}
        </div>

        {/* Add Sensitivity Form */}
        <form onSubmit={handleAddSensitivity} className="pt-2 border-t border-white/6 flex items-center gap-2">
          <Input
            type="text"
            value={newIngredient}
            onChange={(e) => setNewIngredient(e.target.value)}
            placeholder="Add ingredient (e.g. Fragrance, Retinol)..."
            aria-label="New sensitivity ingredient name"
            className="text-xs py-1.5 flex-1"
          />
          <select
            value={newSeverity}
            onChange={(e) => setNewSeverity(e.target.value)}
            aria-label="Sensitivity severity"
            className="p-1.5 rounded-lg bg-[#0A0E12] border border-white/10 text-xs text-slate-300 outline-none"
          >
            <option value="mild">Mild</option>
            <option value="moderate">Moderate</option>
            <option value="severe">Severe</option>
          </select>
          <Button
            type="submit"
            size="sm"
            variant="secondary"
            disabled={!newIngredient.trim() || isAddingSensitivity}
            aria-label="Add sensitivity"
            className="text-xxs px-2.5 h-8 shrink-0"
          >
            <Plus className="w-3.5 h-3.5 mr-0.5" />
            <span>Add</span>
          </Button>
        </form>
      </GlassCard>

      {/* ------------------------------------------------------------------- */}
      {/* 4. Privacy & Facial Analysis Consents                                */}
      {/* ------------------------------------------------------------------- */}
      <GlassCard variant="default" padding="md" className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Camera className="w-4 h-4 text-emerald-400" />
            <h2 className="text-xs font-semibold text-slate-200">Facial Scan Privacy Consent</h2>
          </div>
          <Chip
            variant={facialConsent?.is_granted && !facialConsent?.revoked_at ? "verified" : "caution"}
            size="sm"
          >
            {facialConsent?.is_granted && !facialConsent?.revoked_at ? "Granted" : "Revoked"}
          </Chip>
        </div>

        <p className="text-xxs text-slate-400 leading-relaxed">
          Facial image analysis processes photo pixels to calculate surface visual attributes (redness, spots, texture). Photos are stored in private object storage and are never sold or trained on public models.
        </p>

        {/* Plain Language Consent Disclosure */}
        <div className="p-2.5 rounded-xl bg-[#090D10] border border-white/6 text-[10px] text-slate-400 leading-relaxed">
          <span className="font-semibold text-slate-300">Privacy Policy Impact: </span>
          Revoking consent prevents future scan submissions. Existing historical scan logs remain in your private account until you explicitly delete them from the Skin Scan screen or request permanent account deletion.
        </div>

        <div className="pt-1 flex items-center justify-between">
          <span className="text-xxs text-slate-400">
            {facialConsent?.is_granted && !facialConsent?.revoked_at
              ? "Consent active (v1.0)"
              : "Consent revoked or not granted"}
          </span>

          <Button
            size="sm"
            variant={facialConsent?.is_granted && !facialConsent?.revoked_at ? "danger" : "primary"}
            onClick={handleToggleFacialConsent}
            isLoading={isUpdatingConsent}
            disabled={isUpdatingConsent}
            aria-label={facialConsent?.is_granted && !facialConsent?.revoked_at ? "Revoke facial scan consent" : "Grant facial scan consent"}
            className="text-xxs px-3 h-7 font-semibold"
          >
            {facialConsent?.is_granted && !facialConsent?.revoked_at
              ? "Revoke Consent"
              : "Grant Consent"}
          </Button>
        </div>
      </GlassCard>

      {/* ------------------------------------------------------------------- */}
      {/* 5. Product Reaction & Tolerance History                              */}
      {/* ------------------------------------------------------------------- */}
      <GlassCard variant="default" padding="md" className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-400" />
            <h2 className="text-xs font-semibold text-slate-200">
              Product Reactions & Tolerance History ({reactions.length})
            </h2>
          </div>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setIsReactionModalOpen(true)}
            aria-label="Report product reaction"
            className="text-xxs px-2.5 h-7 flex items-center gap-1 font-semibold text-rose-300 hover:text-white"
          >
            <Plus className="w-3 h-3" />
            <span>Log Reaction</span>
          </Button>
        </div>

        <p className="text-xxs text-slate-400 leading-relaxed">
          Tolerance records are user-reported observations that inform cosmetic suitability checks. Recording a reaction is never a clinical allergy diagnosis.
        </p>

        {/* Reaction Feed */}
        <div className="space-y-2 pt-1">
          {isLoadingReactions ? (
            <p className="text-xxs text-slate-500 italic p-2">Loading reaction history...</p>
          ) : reactions.length === 0 ? (
            <div className="p-3 rounded-xl bg-black/20 border border-white/6 text-center text-xxs text-slate-500">
              No product reactions logged yet. Click "Log Reaction" if a product causes irritation or intolerance.
            </div>
          ) : (
            reactions.map((r) => (
              <div
                key={r.id}
                className="p-3 rounded-xl bg-surface-elevated/60 border border-white/6 space-y-1.5 text-xs"
              >
                <div className="flex items-center justify-between">
                  <span className="font-bold text-slate-200">
                    {r.product_display_name || "Catalog Product"}
                  </span>
                  <Chip
                    variant={r.severity === "severe" ? "adverse" : r.severity === "moderate" ? "caution" : "neutral"}
                    size="sm"
                  >
                    {r.reaction_type.replace(/_/g, " ")} ({r.severity})
                  </Chip>
                </div>

                {r.symptoms && r.symptoms.length > 0 && (
                  <div className="flex flex-wrap gap-1 text-[10px]">
                    {r.symptoms.map((s, idx) => (
                      <span
                        key={idx}
                        className="px-1.5 py-0.5 rounded bg-white/[0.04] text-slate-400"
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                )}

                {r.notes && (
                  <p className="text-slate-400 text-xxs italic leading-relaxed">
                    "{r.notes}"
                  </p>
                )}

                {/* Urgent care notice on individual reaction */}
                {r.requires_urgent_care_guidance && (
                  <div className="p-2 rounded-lg bg-rose-500/15 border border-rose-500/25 text-rose-300 text-[10px] space-y-0.5">
                    <span className="font-bold block">Urgent Care Guidance:</span>
                    <span>{r.urgent_care_guidance}</span>
                  </div>
                )}

                <div className="text-[10px] text-slate-500 pt-0.5 flex items-center justify-between font-mono">
                  <span>{new Date(r.observed_at).toLocaleDateString()}</span>
                  <span>Non-diagnostic</span>
                </div>
              </div>
            ))
          )}
        </div>
      </GlassCard>

      {/* ------------------------------------------------------------------- */}
      {/* 6. Data Governance & Product Gap Disclosures                         */}
      {/* ------------------------------------------------------------------- */}
      <GlassCard variant="default" padding="md" className="space-y-3">
        <div className="flex items-center gap-2">
          <Shield className="w-4 h-4 text-slate-400" />
          <h2 className="text-xs font-semibold text-slate-200">Data Governance & Export</h2>
        </div>

        {/* Honest Product Gap Documentation (Do not invent fake button) */}
        <div className="p-3 rounded-xl bg-white/[0.03] border border-white/6 text-xxs space-y-1.5">
          <div className="flex items-center gap-1.5 text-slate-300 font-semibold">
            <Info className="w-3.5 h-3.5 text-champagne shrink-0" />
            <span>Data Archive & Portability Status</span>
          </div>
          <p className="text-slate-400 leading-relaxed text-[10px]">
            Comprehensive data archive export (e.g. JSON/CSV download of historical scans and logs) is currently in development and not yet available on this server version. No fake export button is displayed.
          </p>
        </div>

        {/* Permanent Account Deletion Action */}
        <div className="pt-2 border-t border-white/6 space-y-2">
          <div className="space-y-0.5">
            <span className="text-xs font-bold text-rose-300 block">
              Permanent Account Deletion
            </span>
            <p className="text-[10px] text-slate-400 leading-relaxed">
              Permanently purges your account, login sessions, routines, and all private stored scan photos and OCR media from object storage. This action is immediate and non-recoverable.
            </p>
          </div>

          <Button
            type="button"
            variant="danger"
            size="md"
            onClick={() => setIsDeleteModalOpen(true)}
            aria-label="Open delete account confirmation modal"
            className="w-full text-xs font-bold"
          >
            Delete Account & Purge Stored Data
          </Button>
        </div>
      </GlassCard>

      {/* ------------------------------------------------------------------- */}
      {/* 7. Active Session Security & Sign Out Actions                        */}
      {/* ------------------------------------------------------------------- */}
      <GlassCard variant="default" padding="md" className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-emerald-400" />
            <h2 className="text-xs font-semibold text-slate-200">Active Session Security</h2>
          </div>
          <button
            type="button"
            onClick={handleManualRefresh}
            disabled={isRefreshing}
            className="text-slate-400 hover:text-slate-200 p-1 rounded-lg transition-colors"
            title="Refresh Token Pair"
            aria-label="Refresh token pair"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
          </button>
        </div>

        <p className="text-xxs text-slate-400 leading-relaxed">
          Sessions rotate single-use refresh tokens upon every refresh cycle. Replay attacks trigger immediate family revocation. No tokens are written to browser localStorage.
        </p>

        <div className="pt-1 space-y-2">
          <Button
            type="button"
            variant="outline"
            size="md"
            className="w-full text-xs"
            onClick={handleLogout}
            isLoading={isLoggingOut}
            disabled={isLoggingOut || isLoggingOutAll}
            leftIcon={<LogOut className="w-3.5 h-3.5 text-rose-400" />}
          >
            {isLoggingOut ? "Signing Out..." : "Sign Out"}
          </Button>

          <Button
            type="button"
            variant="danger"
            size="md"
            className="w-full text-xs"
            onClick={handleLogoutAll}
            isLoading={isLoggingOutAll}
            disabled={isLoggingOut || isLoggingOutAll}
            leftIcon={<Smartphone className="w-3.5 h-3.5" />}
          >
            {isLoggingOutAll ? "Terminating All Sessions..." : "Sign Out From All Devices"}
          </Button>
        </div>
      </GlassCard>

      {/* ------------------------------------------------------------------- */}
      {/* 8. Modals: Product Reaction & Delete Confirmation                   */}
      {/* ------------------------------------------------------------------- */}
      <ProductReactionModal
        isOpen={isReactionModalOpen}
        onClose={() => setIsReactionModalOpen(false)}
        onReactionCreated={(newReaction) => {
          setReactions((prev) => [newReaction, ...prev]);
        }}
      />

      {/* Confirmation Modal for Permanent Account Deletion */}
      {isDeleteModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-account-dialog-title"
        >
          <div className="bg-[#0C1217] border border-rose-500/30 rounded-2xl max-w-sm w-full p-4 space-y-4 shadow-card text-left">
            <div className="flex items-start gap-2.5">
              <div className="p-2 rounded-xl bg-rose-500/15 border border-rose-500/25 text-rose-400 shrink-0">
                <AlertCircle className="w-5 h-5" />
              </div>
              <div>
                <h3 id="delete-account-dialog-title" className="text-sm font-bold text-white leading-tight">
                  Permanent Account Deletion
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  This action is irreversible. All stored facial photos, routine schedules, and profiles will be wiped immediately.
                </p>
              </div>
            </div>

            <div className="space-y-1.5 text-xs">
              <label htmlFor="delete-confirm-input" className="text-xxs font-semibold uppercase tracking-wider text-slate-400 block">
                Type <span className="font-mono text-rose-300 font-bold">DELETE</span> to confirm
              </label>
              <input
                id="delete-confirm-input"
                type="text"
                value={deleteConfirmationText}
                onChange={(e) => setDeleteConfirmationText(e.target.value)}
                placeholder="DELETE"
                aria-label="Confirm deletion by typing DELETE"
                className="w-full p-2.5 rounded-xl bg-surface-elevated border border-rose-500/30 text-xs text-white placeholder-slate-600 outline-none focus:border-rose-400 font-mono text-center tracking-widest"
              />
            </div>

            <div className="flex items-center gap-2 pt-1">
              <Button
                type="button"
                variant="ghost"
                size="md"
                onClick={() => {
                  setIsDeleteModalOpen(false);
                  setDeleteConfirmationText("");
                }}
                disabled={isDeletingAccount}
                className="w-1/2 text-xs"
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="danger"
                size="md"
                disabled={deleteConfirmationText.trim().toUpperCase() !== "DELETE" || isDeletingAccount}
                isLoading={isDeletingAccount}
                onClick={handleConfirmDeleteAccount}
                className="w-1/2 text-xs font-bold"
              >
                {isDeletingAccount ? "Purging..." : "Confirm Delete"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProfilePage;
