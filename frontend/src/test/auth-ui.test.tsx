import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { LoginPage } from "../pages/auth/LoginPage";
import { RegisterPage } from "../pages/auth/RegisterPage";
import { ProtectedRoute } from "../components/auth/ProtectedRoute";
import { AuthProvider } from "../context/AuthContext";
import { authService } from "../api/auth";
import { tokenStore } from "../api/token-store";
import { ApiError } from "../api/types";

describe("Auth UI Components & ProtectedRoute Guard", () => {
  beforeEach(() => {
    tokenStore.clear();
    window.sessionStorage.clear();
    vi.restoreAllMocks();
  });

  describe("LoginPage", () => {
    it("renders accessible labels and fields", () => {
      render(
        <AuthProvider>
          <LoginPage onNavigate={vi.fn()} />
        </AuthProvider>
      );

      expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
    });

    it("displays inline field errors on empty or invalid submission", async () => {
      render(
        <AuthProvider>
          <LoginPage onNavigate={vi.fn()} />
        </AuthProvider>
      );

      fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

      expect(await screen.findByText(/email address is required/i)).toBeInTheDocument();
      expect(await screen.findByText(/password is required/i)).toBeInTheDocument();

      // Enter invalid email
      fireEvent.change(screen.getByLabelText(/email address/i), {
        target: { value: "invalid-email" },
      });
      fireEvent.change(screen.getByLabelText(/password/i), {
        target: { value: "123" },
      });

      fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

      expect(await screen.findByText(/please enter a valid email address/i)).toBeInTheDocument();
      expect(await screen.findByText(/password must be at least 8 characters/i)).toBeInTheDocument();
    });

    it("displays generic credential failure copy on 401 response", async () => {
      vi.spyOn(authService, "login").mockRejectedValue(
        new ApiError("Invalid email or password.", 401, "AUTHENTICATION_ERROR")
      );

      render(
        <AuthProvider>
          <LoginPage onNavigate={vi.fn()} />
        </AuthProvider>
      );

      fireEvent.change(screen.getByLabelText(/email address/i), {
        target: { value: "test@example.com" },
      });
      fireEvent.change(screen.getByLabelText(/password/i), {
        target: { value: "WrongPass123!" },
      });

      fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

      expect(
        await screen.findByText(/invalid email or password\. please verify your credentials and try again/i)
      ).toBeInTheDocument();
    });

    it("displays calm error panel on unexpected network failure", async () => {
      vi.spyOn(authService, "login").mockRejectedValue(
        new ApiError("Network connection lost", 0, "NETWORK_ERROR")
      );

      render(
        <AuthProvider>
          <LoginPage onNavigate={vi.fn()} />
        </AuthProvider>
      );

      fireEvent.change(screen.getByLabelText(/email address/i), {
        target: { value: "test@example.com" },
      });
      fireEvent.change(screen.getByLabelText(/password/i), {
        target: { value: "ValidPass123!" },
      });

      fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

      expect(await screen.findByText(/sign-in error/i)).toBeInTheDocument();
      expect(screen.getByText(/network connection lost/i)).toBeInTheDocument();
    });
  });

  describe("RegisterPage", () => {
    it("renders accessible inputs and validates client fields", async () => {
      render(
        <AuthProvider>
          <RegisterPage onNavigate={vi.fn()} />
        </AuthProvider>
      );

      expect(screen.getByLabelText(/display name/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/password/i)).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: /create account/i }));

      expect(await screen.findByText(/display name is required/i)).toBeInTheDocument();
      expect(await screen.findByText(/email address is required/i)).toBeInTheDocument();
      expect(await screen.findByText(/password is required/i)).toBeInTheDocument();
    });

    it("displays inline conflict notification when email is already registered (409)", async () => {
      vi.spyOn(authService, "register").mockRejectedValue(
        new ApiError("An account with this email address already exists.", 409, "CONFLICT")
      );

      render(
        <AuthProvider>
          <RegisterPage onNavigate={vi.fn()} />
        </AuthProvider>
      );

      fireEvent.change(screen.getByLabelText(/display name/i), {
        target: { value: "Existing User" },
      });
      fireEvent.change(screen.getByLabelText(/email address/i), {
        target: { value: "exists@example.com" },
      });
      fireEvent.change(screen.getByLabelText(/password/i), {
        target: { value: "Password123!" },
      });

      fireEvent.click(screen.getByRole("button", { name: /create account/i }));

      expect(
        await screen.findByText(/an account with this email address already exists/i)
      ).toBeInTheDocument();
    });
  });

  describe("ProtectedRoute Guard & Content Flashing Prevention", () => {
    it("shows loading screen while session is initializing and prevents flashing private content", () => {
      // With no session token, default state starts at initializing briefly
      render(
        <AuthProvider>
          <ProtectedRoute onNavigate={vi.fn()}>
            <div data-testid="private-user-data">Sensitive Routine Secrets</div>
          </ProtectedRoute>
        </AuthProvider>
      );

      // Verify private content is NOT rendered while session is indeterminate
      expect(screen.queryByTestId("private-user-data")).not.toBeInTheDocument();
    });

    it("redirects unauthenticated users to /auth/login without flashing", async () => {
      const navigateMock = vi.fn();

      render(
        <AuthProvider>
          <ProtectedRoute onNavigate={navigateMock}>
            <div data-testid="private-user-data">Sensitive Routine Secrets</div>
          </ProtectedRoute>
        </AuthProvider>
      );

      await waitFor(() => {
        expect(navigateMock).toHaveBeenCalledWith("/auth/login");
      });

      expect(screen.queryByTestId("private-user-data")).not.toBeInTheDocument();
    });
  });
});
