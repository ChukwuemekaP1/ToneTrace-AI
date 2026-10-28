/**
 * Mobile-Only Soft-Glass Register Page
 *
 * Implements accessible self-registration:
 * - Email, password (min 8 chars), and display_name (required by backend contract)
 * - Accessible labels, client-side validation, inline errors
 * - Disabled and submitting states
 * - Inline handling for 409 Email Conflict
 * - Calm error recovery panel for unexpected backend errors
 */

import React, { useState } from "react";
import { Mail, Lock, User, Sparkles, ArrowRight } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { GlassCard } from "@/components/ui/GlassCard";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { ErrorRecovery } from "@/components/ui/ErrorRecovery";
import { ApiError } from "@/api/types";

export interface RegisterPageProps {
  onNavigate: (route: string) => void;
}

interface FormErrors {
  displayName?: string;
  email?: string;
  password?: string;
}

export const RegisterPage: React.FC<RegisterPageProps> = ({ onNavigate }) => {
  const { register } = useAuth();

  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<FormErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [conflictError, setConflictError] = useState<string | null>(null);
  const [unexpectedError, setUnexpectedError] = useState<ApiError | Error | null>(null);

  // Client validation matching backend Pydantic constraints
  const validateForm = (): boolean => {
    const nextErrors: FormErrors = {};
    const trimmedName = displayName.trim();
    const trimmedEmail = email.trim();

    if (!trimmedName) {
      nextErrors.displayName = "Display name is required.";
    } else if (trimmedName.length > 100) {
      nextErrors.displayName = "Display name cannot exceed 100 characters.";
    }

    if (!trimmedEmail) {
      nextErrors.email = "Email address is required.";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedEmail)) {
      nextErrors.email = "Please enter a valid email address.";
    }

    if (!password) {
      nextErrors.password = "Password is required.";
    } else if (password.length < 8) {
      nextErrors.password = "Password must be at least 8 characters.";
    } else if (password.length > 128) {
      nextErrors.password = "Password cannot exceed 128 characters.";
    }

    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setConflictError(null);
    setUnexpectedError(null);

    if (!validateForm()) {
      return;
    }

    setSubmitting(true);
    try {
      await register({
        display_name: displayName.trim(),
        email: email.trim(),
        password,
      });
      // Newly registered users have blank skin_profile, so they will be guided to onboarding
      onNavigate("/onboarding");
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setConflictError("An account with this email address already exists. Please sign in instead.");
        } else if (err.status === 422) {
          // Server schema validation error
          const details = Array.isArray(err.details)
            ? err.details.map((d) => `${d.field || "field"}: ${d.message || "invalid"}`).join(", ")
            : err.message;
          setConflictError(`Validation error: ${details}`);
        } else {
          setUnexpectedError(err);
        }
      } else {
        setUnexpectedError(
          err instanceof Error
            ? err
            : new ApiError("Unable to complete registration at this time.", 0, "NETWORK_ERROR")
        );
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="w-full max-w-[400px] mx-auto py-2 space-y-5 text-left">
      {/* Brand Header */}
      <div className="text-center space-y-1.5 pt-2">
        <div className="inline-flex w-12 h-12 rounded-2xl bg-gradient-to-tr from-emerald-600 to-emerald-400 p-0.5 items-center justify-center shadow-glow mb-1">
          <div className="w-full h-full bg-[#090D11] rounded-[14px] flex items-center justify-center">
            <Sparkles className="w-6 h-6 text-emerald-400" />
          </div>
        </div>
        <h2 className="text-xl font-bold tracking-tight text-white">Create Account</h2>
        <p className="text-xs text-slate-400 max-w-[280px] mx-auto">
          Start tracking cosmetic formulations, avoiding personal sensitivities, and optimizing routines.
        </p>
      </div>

      {/* Calm Error Panel for unexpected backend errors */}
      {unexpectedError && (
        <ErrorRecovery
          error={unexpectedError}
          title="Registration Issue"
          onRetry={() => {
            setUnexpectedError(null);
          }}
        />
      )}

      {/* 409 Conflict or Form-level Alert */}
      {conflictError && (
        <div
          role="alert"
          aria-live="polite"
          data-testid="register-conflict-error"
          className="p-3.5 rounded-xl bg-amber-950/30 border border-amber-500/30 text-amber-200 text-xs leading-relaxed"
        >
          {conflictError}
        </div>
      )}

      {/* Soft-Glass Register Form */}
      <GlassCard variant="elevated" padding="md" className="space-y-4">
        <form onSubmit={handleSubmit} noValidate className="space-y-4">
          <Input
            id="register-display-name"
            type="text"
            label="Display Name"
            placeholder="e.g. Maya"
            value={displayName}
            disabled={submitting}
            error={errors.displayName}
            autoComplete="name"
            leftIcon={<User className="w-4 h-4" />}
            onChange={(e) => {
              setDisplayName(e.target.value);
              if (errors.displayName) setErrors((prev) => ({ ...prev, displayName: undefined }));
            }}
          />

          <Input
            id="register-email"
            type="email"
            label="Email Address"
            placeholder="you@example.com"
            value={email}
            disabled={submitting}
            error={errors.email}
            autoComplete="email"
            leftIcon={<Mail className="w-4 h-4" />}
            onChange={(e) => {
              setEmail(e.target.value);
              if (errors.email) setErrors((prev) => ({ ...prev, email: undefined }));
              if (conflictError) setConflictError(null);
            }}
          />

          <Input
            id="register-password"
            type="password"
            label="Password"
            placeholder="At least 8 characters"
            value={password}
            disabled={submitting}
            error={errors.password}
            helperText="Minimum 8 characters"
            autoComplete="new-password"
            leftIcon={<Lock className="w-4 h-4" />}
            onChange={(e) => {
              setPassword(e.target.value);
              if (errors.password) setErrors((prev) => ({ ...prev, password: undefined }));
            }}
          />

          <Button
            type="submit"
            variant="primary"
            size="lg"
            className="w-full mt-2"
            isLoading={submitting}
            disabled={submitting}
            rightIcon={<ArrowRight className="w-4 h-4" />}
          >
            {submitting ? "Creating account..." : "Create Account"}
          </Button>
        </form>
      </GlassCard>

      {/* Switch to Sign In */}
      <div className="text-center text-xs text-slate-400">
        Already have an account?{" "}
        <button
          type="button"
          onClick={() => onNavigate("/auth/login")}
          className="text-emerald-400 hover:text-emerald-300 font-semibold underline underline-offset-2 transition-colors ml-1"
        >
          Sign in
        </button>
      </div>
    </div>
  );
};
