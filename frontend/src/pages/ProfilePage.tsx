/**
 * User Profile & Session Management Screen
 *
 * Displays verified account details and controls:
 * - Single-session logout (direct action without unnecessary modals)
 * - Global logout-all (revoking all active refresh sessions)
 * - Skin profile completeness indicator & link to /settings/skin-profile
 */

import React, { useState } from "react";
import {
  User,
  Mail,
  Shield,
  LogOut,
  Smartphone,
  RefreshCw,
  Sparkles,
  ChevronRight,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { GlassCard } from "@/components/ui/GlassCard";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { ErrorRecovery } from "@/components/ui/ErrorRecovery";

export interface ProfilePageProps {
  onNavigate?: (route: string) => void;
}

export const ProfilePage: React.FC<ProfilePageProps> = ({ onNavigate }) => {
  const { user, summary, isOnboardingComplete, logout, logoutAll, refreshSession } = useAuth();

  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [isLoggingOutAll, setIsLoggingOutAll] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [actionError, setActionError] = useState<Error | null>(null);

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

  const skinProfile = summary?.skin_profile;
  const sensitivities = summary?.sensitivities || [];

  return (
    <div className="space-y-4 text-left">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-bold text-white tracking-tight">Account & Profile</h2>
        <Chip variant="champagne" size="sm">Phase 1 Integration</Chip>
      </div>

      {actionError && (
        <ErrorRecovery
          error={actionError}
          title="Session Action Error"
          onRetry={() => setActionError(null)}
        />
      )}

      {/* Account Info Card */}
      <GlassCard variant="elevated" padding="md" className="space-y-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 shrink-0">
            <User className="w-5 h-5" />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold text-white truncate">
              {summary?.profile?.display_name || "ToneTrace User"}
            </h3>
            <div className="flex items-center gap-1.5 text-slate-400 text-xs truncate">
              <Mail className="w-3.5 h-3.5 shrink-0" />
              <span className="truncate">{user?.email || "No email"}</span>
            </div>
          </div>
        </div>

        <div className="pt-2 border-t border-white/[0.08] grid grid-cols-2 gap-2 text-xxs">
          <div>
            <span className="text-slate-500 block">Status</span>
            <span className="font-medium text-emerald-400 capitalize">
              {user?.account_status || "Active"}
            </span>
          </div>
          <div>
            <span className="text-slate-500 block">Timezone</span>
            <span className="font-mono text-slate-300">
              {summary?.profile?.timezone || "UTC"}
            </span>
          </div>
        </div>
      </GlassCard>

      {/* Skin Profile & Preferences Card (Deep link to /settings/skin-profile) */}
      <GlassCard variant="default" padding="md" className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-champagne" />
            <h4 className="text-xs font-semibold text-slate-200">Skin Blueprint & Preferences</h4>
          </div>
          <Chip
            variant={isOnboardingComplete ? "verified" : "caution"}
            size="sm"
          >
            {isOnboardingComplete ? "Configured" : "Incomplete"}
          </Chip>
        </div>

        <div className="grid grid-cols-3 gap-2 pt-1 text-center">
          <div className="p-2 rounded-xl bg-[#0B0F13] border border-white/5">
            <span className="text-xxs text-slate-500 block">Type</span>
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
          className="w-full mt-2 flex items-center justify-between p-2.5 rounded-xl bg-[#131B22] border border-white/10 hover:border-emerald-500/40 text-xs text-slate-200 transition-all cursor-pointer"
        >
          <div className="flex items-center gap-2">
            <Shield className="w-3.5 h-3.5 text-emerald-400" />
            <span>Edit Skin Profile & Sensitivities</span>
          </div>
          <ChevronRight className="w-4 h-4 text-slate-400" />
        </button>
      </GlassCard>

      {/* Session Security Details */}
      <GlassCard variant="default" padding="md" className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-emerald-400" />
            <h4 className="text-xs font-semibold text-slate-200">Active Session Security</h4>
          </div>
          <button
            type="button"
            onClick={handleManualRefresh}
            disabled={isRefreshing}
            className="text-slate-400 hover:text-slate-200 p-1 rounded-lg transition-colors"
            title="Refresh Token Pair"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
          </button>
        </div>

        <p className="text-xxs text-slate-400 leading-relaxed">
          Sessions rotate single-use refresh tokens upon every refresh cycle. Replay attacks trigger immediate family revocation. No tokens are written to permanent browser localStorage.
        </p>

        <div className="pt-1 space-y-2">
          {/* Direct Logout (No unnecessary modal) */}
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

          {/* Logout All Devices */}
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
    </div>
  );
};
