import React, { useEffect, useState } from "react";
import {
  ShieldCheck,
  Activity,
  ArrowRight,
  Database,
  Search,
  BookOpen,
} from "lucide-react";
import { apiClient } from "@/api/client";
import { GlassCard } from "@/components/ui/GlassCard";
import { Chip } from "@/components/ui/Chip";
import { Button } from "@/components/ui/Button";
import { BrandedLoading } from "@/components/ui/BrandedLoading";
import { ErrorRecovery } from "@/components/ui/ErrorRecovery";
import { ApiError } from "@/api/types";

interface BackendStatus {
  connected: boolean;
  live: boolean;
  details?: Record<string, unknown> | null;
}

export interface AppHomeProps {
  onNavigateTab: (tab: "home" | "shelf" | "routines" | "profile" | "showcase") => void;
  onHealthChange?: (healthy: boolean) => void;
}

export const AppHome: React.FC<AppHomeProps> = ({ onNavigateTab, onHealthChange }) => {
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [status, setStatus] = useState<BackendStatus | null>(null);

  const fetchBackendStatus = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.checkHealth();
      setStatus({
        connected: res.live,
        live: res.live,
        details: (res.details as Record<string, unknown>) || null,
      });
      onHealthChange?.(res.live);
    } catch (err) {
      const apiErr =
        err instanceof Error
          ? err
          : new ApiError("Failed to probe ToneTrace backend health", 0, "NETWORK_ERROR");
      setError(apiErr);
      setStatus({ connected: false, live: false });
      onHealthChange?.(false);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBackendStatus();
  }, []);

  if (loading) {
    return (
      <BrandedLoading
        message="Verifying connection to ToneTrace FastAPI backend..."
        timeoutMs={6000}
        onRetry={fetchBackendStatus}
        timeoutFallbackTitle="Backend connection timed out"
        timeoutFallbackMessage="Unable to reach the FastAPI backend at /health/live within 6 seconds. Please ensure the backend is running on port 8000."
      />
    );
  }

  if (error || (status && !status.connected)) {
    return (
      <div className="space-y-4">
        <ErrorRecovery
          error={error || new Error("FastAPI backend is currently offline or unreachable")}
          title="ToneTrace Backend Connectivity Issue"
          onRetry={fetchBackendStatus}
        />

        <GlassCard variant="default" className="text-left space-y-2">
          <h4 className="text-xs font-semibold text-slate-200">Local Development Checklist</h4>
          <ul className="text-xxs text-slate-400 space-y-1 list-disc pl-4">
            <li>Ensure backend is running: <code className="text-slate-300 font-mono">.venv\Scripts\python -m app.main</code></li>
            <li>Default FastAPI URL: <code className="text-slate-300 font-mono">http://localhost:8000</code></li>
            <li>CORS allowed origins: <code className="text-slate-300 font-mono">http://localhost:3000</code></li>
          </ul>
        </GlassCard>

        <div className="pt-2">
          <Button
            variant="secondary"
            className="w-full"
            onClick={() => onNavigateTab("showcase")}
          >
            Open Design System Showcase
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5 text-left">
      {/* Welcome Card */}
      <GlassCard variant="accent" className="space-y-3">
        <div className="flex items-center justify-between">
          <Chip variant="verified" size="sm" showDot>
            System Online
          </Chip>
          <span className="text-xxs text-slate-400 font-mono">FastAPI + Neon</span>
        </div>

        <div>
          <h2 className="text-base font-bold text-white tracking-tight">
            Scientific Skincare Intelligence
          </h2>
          <p className="text-xs text-slate-300 mt-1 leading-relaxed">
            ToneTrace AI pairs cosmetic formulation science, regulatory CosIng databases, and
            grounded dermatological explanations.
          </p>
        </div>

        <div className="pt-1 flex items-center gap-2">
          <Button
            size="sm"
            variant="primary"
            onClick={() => onNavigateTab("showcase")}
            rightIcon={<ArrowRight className="w-3.5 h-3.5" />}
          >
            Explore Design Showcase
          </Button>
        </div>
      </GlassCard>

      {/* Backend Infrastructure Overview */}
      <div className="space-y-2">
        <div className="flex items-center justify-between px-0.5">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
            Verified Subsystems
          </h3>
          <span className="text-xxs text-emerald-400 font-mono">10 Modules Live</span>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <GlassCard variant="default" padding="sm" className="space-y-1">
            <div className="flex items-center gap-1.5 text-emerald-400">
              <Database className="w-3.5 h-3.5" />
              <span className="text-xs font-semibold text-slate-200">Neon Postgres</span>
            </div>
            <p className="text-xxs text-slate-400">Authoritative store & BYTEA media</p>
          </GlassCard>

          <GlassCard variant="default" padding="sm" className="space-y-1">
            <div className="flex items-center gap-1.5 text-emerald-400">
              <Search className="w-3.5 h-3.5" />
              <span className="text-xs font-semibold text-slate-200">Catalog Search</span>
            </div>
            <p className="text-xxs text-slate-400">Elasticsearch 8.x + DB fallback</p>
          </GlassCard>

          <GlassCard variant="default" padding="sm" className="space-y-1">
            <div className="flex items-center gap-1.5 text-champagne">
              <BookOpen className="w-3.5 h-3.5" />
              <span className="text-xs font-semibold text-slate-200">Evidence</span>
            </div>
            <p className="text-xxs text-slate-400">EC CosIng & PubMed abstracts</p>
          </GlassCard>

          <GlassCard variant="default" padding="sm" className="space-y-1">
            <div className="flex items-center gap-1.5 text-amber-400">
              <ShieldCheck className="w-3.5 h-3.5" />
              <span className="text-xs font-semibold text-slate-200">Safe Routines</span>
            </div>
            <p className="text-xxs text-slate-400">Urgent-care reaction guardrails</p>
          </GlassCard>
        </div>
      </div>

      {/* Epistemic Transparency Disclaimer */}
      <div className="p-3.5 rounded-xl bg-white/[0.03] border border-white/5 space-y-1">
        <div className="flex items-center gap-1.5 text-slate-300">
          <Activity className="w-3.5 h-3.5 text-emerald-400" />
          <span className="text-xxs font-semibold uppercase tracking-wider">
            Epistemic Disclaimer
          </span>
        </div>
        <p className="text-xxs text-slate-400 leading-relaxed">
          ToneTrace does not provide medical diagnoses or replace licensed dermatological consultation. Efficacy cannot be inferred from ingredient names alone, and cosmetic scans reflect non-clinical visual observations.
        </p>
      </div>
    </div>
  );
};
