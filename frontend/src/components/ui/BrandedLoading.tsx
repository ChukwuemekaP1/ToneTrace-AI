import React, { useEffect, useState } from "react";
import { Sparkles, AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "./Button";

export interface BrandedLoadingProps {
  message?: string;
  timeoutMs?: number;
  onTimeout?: () => void;
  onRetry?: () => void;
  timeoutFallbackTitle?: string;
  timeoutFallbackMessage?: string;
}

export const BrandedLoading: React.FC<BrandedLoadingProps> = ({
  message = "Calibrating cosmetic science engine...",
  timeoutMs = 8000,
  onTimeout,
  onRetry,
  timeoutFallbackTitle = "Connection taking longer than expected",
  timeoutFallbackMessage = "We are having trouble resolving data from the ToneTrace backend. Please verify your connection or try again.",
}) => {
  const [timedOut, setTimedOut] = useState(false);

  useEffect(() => {
    if (timeoutMs <= 0) return;

    const timer = setTimeout(() => {
      setTimedOut(true);
      onTimeout?.();
    }, timeoutMs);

    return () => clearTimeout(timer);
  }, [timeoutMs, onTimeout]);

  if (timedOut) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-center min-h-[280px] space-y-4 animate-in fade-in duration-300">
        <div className="w-12 h-12 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400">
          <AlertCircle className="w-6 h-6" />
        </div>
        <div className="space-y-1.5 max-w-xs">
          <h3 className="text-sm font-semibold text-slate-100">{timeoutFallbackTitle}</h3>
          <p className="text-xs text-slate-400 leading-relaxed">{timeoutFallbackMessage}</p>
        </div>
        {onRetry && (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              setTimedOut(false);
              onRetry();
            }}
            leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
          >
            Retry Connection
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center p-8 text-center min-h-[280px] space-y-4 select-none">
      {/* Branded Pulse Emblem */}
      <div className="relative w-16 h-16 flex items-center justify-center">
        <div className="absolute inset-0 rounded-2xl bg-emerald-500/20 animate-ping opacity-30" />
        <div className="relative w-14 h-14 rounded-2xl bg-[#11171E] border border-emerald-500/40 shadow-glow flex items-center justify-center">
          <Sparkles className="w-6 h-6 text-emerald-400 animate-pulse" />
        </div>
      </div>

      <div className="space-y-1 max-w-xs">
        <p className="text-xs font-medium text-slate-200 tracking-wide">{message}</p>
        <p className="text-xxs text-slate-500">ToneTrace AI Evidence Engine</p>
      </div>

      {/* Subtle indicator bar */}
      <div className="w-24 h-0.5 bg-white/10 rounded-full overflow-hidden">
        <div className="w-full h-full bg-emerald-500/60 rounded-full animate-indeterminate origin-left" />
      </div>
    </div>
  );
};
