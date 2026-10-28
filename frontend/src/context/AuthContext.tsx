/**
 * Authentication Context & Provider
 *
 * Provides reactive session state across the mobile application:
 * - Session recovery on tab load without localStorage
 * - Flashing prevention (status starts at 'initializing')
 * - Automatic refresh coordination with loop prevention
 * - Skin profile completeness detection without guessing
 * - Single-session logout and global logout-all
 */

import React, { createContext, useContext, useEffect, useState, useMemo } from "react";
import { apiClient } from "@/api/client";
import { authService } from "@/api/auth";
import { tokenStore } from "@/api/token-store";
import {
  AuthSuccessResponse,
  MeSummaryResponse,
  UserLoginRequest,
  UserRegisterRequest,
  UserResponse,
} from "@/api/types";

export type AuthStatus = "initializing" | "authenticated" | "unauthenticated";

export interface AuthContextValue {
  status: AuthStatus;
  user: UserResponse | null;
  summary: MeSummaryResponse | null;
  isOnboardingComplete: boolean | null;
  login: (payload: UserLoginRequest) => Promise<AuthSuccessResponse>;
  register: (payload: UserRegisterRequest) => Promise<AuthSuccessResponse>;
  logout: () => Promise<void>;
  logoutAll: () => Promise<void>;
  refreshSession: () => Promise<void>;
  refreshProfile: () => Promise<MeSummaryResponse>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export interface AuthProviderProps {
  children: React.ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [status, setStatus] = useState<AuthStatus>("initializing");
  const [user, setUser] = useState<UserResponse | null>(null);
  const [summary, setSummary] = useState<MeSummaryResponse | null>(null);

  // Wire up apiClient's 401 automatic refresh hook
  useEffect(() => {
    apiClient.setRefreshHandler(async () => {
      try {
        const rotated = await authService.refresh();
        return rotated.access_token;
      } catch {
        tokenStore.clear();
        setUser(null);
        setSummary(null);
        setStatus("unauthenticated");
        return null;
      }
    });
  }, []);

  // Initial session recovery
  useEffect(() => {
    let isMounted = true;

    const recoverSession = async () => {
      if (!tokenStore.hasSession()) {
        if (isMounted) {
          setStatus("unauthenticated");
        }
        return;
      }

      try {
        // Attempt rotation to verify token validity
        await authService.refresh();
        const me = await authService.getMe();
        if (isMounted) {
          setUser(me.user);
          setSummary(me);
          setStatus("authenticated");
        }
      } catch {
        // Refresh token expired, revoked, or compromised
        tokenStore.clear();
        if (isMounted) {
          setUser(null);
          setSummary(null);
          setStatus("unauthenticated");
        }
      }
    };

    recoverSession();

    return () => {
      isMounted = false;
    };
  }, []);

  const login = async (payload: UserLoginRequest): Promise<AuthSuccessResponse> => {
    const res = await authService.login(payload);
    setUser(res.user);
    try {
      const me = await authService.getMe();
      setSummary(me);
    } catch {
      setSummary({ user: res.user, sensitivities: [] });
    }
    setStatus("authenticated");
    return res;
  };

  const register = async (payload: UserRegisterRequest): Promise<AuthSuccessResponse> => {
    const res = await authService.register(payload);
    setUser(res.user);
    try {
      const me = await authService.getMe();
      setSummary(me);
    } catch {
      setSummary({ user: res.user, sensitivities: [] });
    }
    setStatus("authenticated");
    return res;
  };

  const logout = async (): Promise<void> => {
    try {
      await authService.logout();
    } finally {
      tokenStore.clear();
      setUser(null);
      setSummary(null);
      setStatus("unauthenticated");
    }
  };

  const logoutAll = async (): Promise<void> => {
    try {
      await authService.logoutAll();
    } finally {
      tokenStore.clear();
      setUser(null);
      setSummary(null);
      setStatus("unauthenticated");
    }
  };

  const refreshSession = async (): Promise<void> => {
    await authService.refresh();
    const me = await authService.getMe();
    setUser(me.user);
    setSummary(me);
    setStatus("authenticated");
  };

  const refreshProfile = async (): Promise<MeSummaryResponse> => {
    const me = await authService.getMe();
    setUser(me.user);
    setSummary(me);
    return me;
  };

  /**
   * Determine onboarding completeness strictly without guessing:
   * - If backend provided a skin_profile object:
   *   - complete: skin_type is non-null & non-empty
   *   - incomplete: skin_type is null or empty
   * - If skin_profile is not returned: returns null (incomplete info, do not guess)
   */
  const isOnboardingComplete = useMemo<boolean | null>(() => {
    if (!summary || summary.skin_profile === undefined) {
      return null;
    }
    if (summary.skin_profile === null) {
      return false;
    }
    return Boolean(
      summary.skin_profile.skin_type && summary.skin_profile.skin_type.trim() !== ""
    );
  }, [summary]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      summary,
      isOnboardingComplete,
      login,
      register,
      logout,
      logoutAll,
      refreshSession,
      refreshProfile,
    }),
    [status, user, summary, isOnboardingComplete]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = (): AuthContextValue => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};
