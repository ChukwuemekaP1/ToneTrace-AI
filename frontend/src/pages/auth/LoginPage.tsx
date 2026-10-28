/**
 * Mobile-Only Soft-Glass Login Page
 *
 * Implements accessible labels, client-side validation, inline field errors,
 * disabled/submitting states, generic credential failure copy, and a calm
 * error recovery panel for unexpected network or server failures.
 */

import React, { useState } from "react";
import { Mail, Lock, Sparkles, ArrowRight } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { GlassCard } from "@/components/ui/GlassCard";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { ErrorRecovery } from "@/components/ui/ErrorRecovery";
import { ApiError } from "@/api/types";

export interface LoginPageProps {
  onNavigate: (route: string) => void;
}

interface FormErrors {
  email?: string;
  password?: string;
}

export const LoginPage: React.FC<LoginPageProps> = ({ onNavigate }) => {
  const { login } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<FormErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [unexpectedError, setUnexpectedError] = useState<ApiError | Error | null>(null);

  // Client validation
  const validateForm = (): boolean => {
    const nextErrors: FormErrors = {};
    const trimmedEmail = email.trim();

    if (!trimmedEmail) {
      nextErrors.email = "Email address is required.";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedEmail)) {
      nextErrors.email = "Please enter a valid email address.";
    }

    if (!password) {
      nextErrors.password = "Password is required.";
    } else if (password.length < 8) {
      nextErrors.password = "Password must be at least 8 characters.";
    }

    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setAuthError(null);
    setUnexpectedError(null);

    if (!validateForm()) {
      return;
    }

    setSubmitting(true);
    try {
      await login({
        email: email.trim(),
        password,
        device_label: "ToneTrace Mobile Web",
      });
      // Navigation will be coordinated by ProtectedRoute or caller
      onNavigate("/");
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          // Generic credential failure copy - protects against user enumeration
          setAuthError("Invalid email or password. Please verify your credentials and try again.");
        } else if (err.status === 429) {
          setUnexpectedError(
            new ApiError("Too many login attempts. Please wait a minute and try again.", 429, "RATE_LIMITED")
          );
        } else {
          setUnexpectedError(err);
        }
      } else {
        setUnexpectedError(
          err instanceof Error
            ? err
            : new ApiError("Unable to connect to the authentication server.", 0, "NETWORK_ERROR")
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
        <h2 className="text-xl font-bold tracking-tight text-white">Sign In</h2>
        <p className="text-xs text-slate-400 max-w-[280px] mx-auto">
          Access your personalized formulation shelf, daily routines, and grounded AI insights.
        </p>
      </div>

      {/* Calm Error Panel for unexpected network or server errors */}
      {unexpectedError && (
        <ErrorRecovery
          error={unexpectedError}
          title="Sign-In Error"
          onRetry={() => {
            setUnexpectedError(null);
          }}
        />
      )}

      {/* Generic Credential Error Notification */}
      {authError && (
        <div
          role="alert"
          aria-live="polite"
          data-testid="login-auth-error"
          className="p-3.5 rounded-xl bg-rose-950/30 border border-rose-500/30 text-rose-300 text-xs leading-relaxed"
        >
          {authError}
        </div>
      )}

      {/* Soft-Glass Login Form */}
      <GlassCard variant="elevated" padding="md" className="space-y-4">
        <form onSubmit={handleSubmit} noValidate className="space-y-4">
          <Input
            id="login-email"
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
              if (authError) setAuthError(null);
            }}
          />

          <Input
            id="login-password"
            type="password"
            label="Password"
            placeholder="••••••••"
            value={password}
            disabled={submitting}
            error={errors.password}
            autoComplete="current-password"
            leftIcon={<Lock className="w-4 h-4" />}
            onChange={(e) => {
              setPassword(e.target.value);
              if (errors.password) setErrors((prev) => ({ ...prev, password: undefined }));
              if (authError) setAuthError(null);
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
            {submitting ? "Signing in..." : "Sign In"}
          </Button>
        </form>
      </GlassCard>

      {/* Switch to Registration */}
      <div className="text-center text-xs text-slate-400">
        Don&apos;t have an account?{" "}
        <button
          type="button"
          onClick={() => onNavigate("/auth/register")}
          className="text-emerald-400 hover:text-emerald-300 font-semibold underline underline-offset-2 transition-colors ml-1"
        >
          Create account
        </button>
      </div>
    </div>
  );
};
