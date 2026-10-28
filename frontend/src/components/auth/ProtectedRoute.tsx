/**
 * Protected Route Component
 *
 * Ensures private user data never flashes before session status is fully resolved.
 * Automatically coordinates redirects to /auth/login for expired or unauthenticated sessions,
 * and /onboarding if the verified skin profile indicates incomplete onboarding.
 */

import React from "react";
import { useAuth } from "@/context/AuthContext";
import { BrandedLoading } from "@/components/ui/BrandedLoading";

export interface ProtectedRouteProps {
  children: React.ReactNode;
  onNavigate: (route: string) => void;
  allowIncompleteOnboarding?: boolean;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  children,
  onNavigate,
  allowIncompleteOnboarding = false,
}) => {
  const { status, isOnboardingComplete } = useAuth();

  React.useEffect(() => {
    if (status === "unauthenticated") {
      onNavigate("/auth/login");
    } else if (
      status === "authenticated" &&
      isOnboardingComplete === false &&
      !allowIncompleteOnboarding
    ) {
      onNavigate("/onboarding");
    }
  }, [status, isOnboardingComplete, allowIncompleteOnboarding, onNavigate]);

  if (status === "initializing") {
    return (
      <div
        data-testid="protected-route-loading"
        className="min-h-[50vh] flex flex-col items-center justify-center p-6 text-center"
      >
        <BrandedLoading
          message="Restoring secure session..."
        />
      </div>
    );
  }

  if (status === "unauthenticated") {
    return null; // Prevents flashing private content while redirect triggers
  }

  if (isOnboardingComplete === false && !allowIncompleteOnboarding) {
    return null; // Prevents flashing dashboard before onboarding navigation completes
  }

  return <>{children}</>;
};
