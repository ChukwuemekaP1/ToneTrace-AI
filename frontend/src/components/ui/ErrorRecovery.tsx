import React from "react";
import { AlertTriangle, RefreshCw, ChevronDown, ChevronUp } from "lucide-react";
import { Button } from "./Button";
import { ApiError } from "@/api/types";

export interface ErrorRecoveryProps {
  error: Error | ApiError | string | null;
  onRetry?: () => void;
  title?: string;
  className?: string;
}

export const ErrorRecovery: React.FC<ErrorRecoveryProps> = ({
  error,
  onRetry,
  title = "Something went wrong",
  className = "",
}) => {
  const [showDetails, setShowDetails] = React.useState(false);

  const message = error instanceof Error ? error.message : typeof error === "string" ? error : "An unexpected error occurred.";
  const isApiError = error instanceof ApiError;
  const errorCode = isApiError ? (error as ApiError).code : undefined;
  const requestId = isApiError ? (error as ApiError).requestId : undefined;
  const details = isApiError ? (error as ApiError).details : undefined;

  return (
    <div className={`p-6 rounded-2xl bg-rose-950/15 border border-rose-500/25 text-left space-y-4 ${className}`}>
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center text-rose-400 shrink-0">
          <AlertTriangle className="w-5 h-5" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h4 className="text-sm font-semibold text-rose-200">{title}</h4>
            {errorCode && (
              <span className="px-1.5 py-0.5 text-xxs font-mono bg-rose-500/20 text-rose-300 rounded border border-rose-500/30">
                {errorCode}
              </span>
            )}
          </div>
          <p className="text-xs text-rose-300/80 mt-1 leading-relaxed break-words">{message}</p>
        </div>
      </div>

      {Boolean(requestId || details) && (
        <div className="text-xxs">
          <button
            type="button"
            onClick={() => setShowDetails(!showDetails)}
            className="flex items-center gap-1 text-slate-400 hover:text-slate-200 font-medium transition-colors"
          >
            {showDetails ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            <span>{showDetails ? "Hide technical diagnostic details" : "Show diagnostic details"}</span>
          </button>

          {showDetails && (
            <div className="mt-2 p-3 bg-black/40 rounded-xl border border-white/5 font-mono text-slate-400 space-y-1">
              {requestId && <p><span className="text-slate-500">Request ID:</span> {requestId}</p>}
              {Boolean(details) && (
                <pre className="text-xxs whitespace-pre-wrap overflow-x-auto text-slate-300">
                  {JSON.stringify(details, null, 2)}
                </pre>
              )}
            </div>
          )}
        </div>
      )}

      {onRetry && (
        <div className="pt-1 flex items-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            onClick={onRetry}
            leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
          >
            Try Again
          </Button>
        </div>
      )}
    </div>
  );
};
