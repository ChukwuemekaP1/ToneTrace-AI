import React, { useState, useEffect, useCallback } from "react";
import { MobileShell, NavTab } from "@/components/layout/MobileShell";
import { AuthProvider } from "@/context/AuthContext";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { LoginPage } from "@/pages/auth/LoginPage";
import { RegisterPage } from "@/pages/auth/RegisterPage";
import { OnboardingPage } from "@/pages/auth/OnboardingPage";
import { SkinProfileEditorPage } from "@/pages/SkinProfileEditorPage";
import { ProfilePage } from "@/pages/ProfilePage";
import { DashboardPage } from "@/pages/DashboardPage";
import { DiscoveryPage } from "@/pages/DiscoveryPage";
import { ProductDetailPage } from "@/pages/ProductDetailPage";
import { ShelfPage } from "@/pages/ShelfPage";
import { RoutinesPage } from "@/pages/RoutinesPage";
import { ScanLabelModal } from "@/components/ocr/ScanLabelModal";
import { DesignSystemShowcase } from "@/pages/DesignSystemShowcase";
import {
  SkinTrackPlaceholder,
  AiAskPlaceholder,
} from "@/pages/Placeholders";

export const AppContent: React.FC = () => {
  const [currentRoute, setCurrentRoute] = useState<string>(() => {
    if (typeof window !== "undefined" && window.location.pathname) {
      return window.location.pathname;
    }
    return "/";
  });
  const [backendHealthy] = useState<boolean | null>(true);

  const navigate = useCallback((route: string) => {
    setCurrentRoute(route);
    if (typeof window !== "undefined" && window.location.pathname !== route) {
      window.history.pushState(null, "", route);
    }
  }, []);

  useEffect(() => {
    const handlePopState = () => {
      setCurrentRoute(window.location.pathname || "/");
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const isProductDetailRoute =
    currentRoute.startsWith("/products/") || currentRoute.startsWith("/discovery/products/");
  const productId = isProductDetailRoute
    ? currentRoute.replace(/^\/(?:discovery\/)?products\//, "").split("?")[0]
    : "";

  const isShelfDetailRoute = currentRoute.startsWith("/shelf/") && currentRoute !== "/shelf";
  const shelfItemId = isShelfDetailRoute
    ? currentRoute.replace(/^\/shelf\//, "").split("?")[0]
    : null;

  const isDiscoveryRoute = currentRoute === "/discovery" || currentRoute === "/explore";

  // Determine active tab from route
  const activeTab: NavTab = (() => {
    if (currentRoute === "/shelf" || currentRoute.startsWith("/shelf/")) return "shelf";
    if (currentRoute === "/routines") return "routines";
    if (currentRoute === "/profile" || currentRoute === "/settings/skin-profile") return "profile";
    if (currentRoute === "/showcase") return "showcase";
    if (currentRoute === "/scan") return "scan";
    return "home";
  })();

  const handleTabChange = (tab: NavTab) => {
    switch (tab) {
      case "shelf":
        navigate("/shelf");
        break;
      case "routines":
        navigate("/routines");
        break;
      case "profile":
        navigate("/profile");
        break;
      case "showcase":
        navigate("/showcase");
        break;
      case "scan":
        navigate("/scan");
        break;
      case "home":
      default:
        navigate("/");
        break;
    }
  };

  const isAuthRoute = currentRoute === "/auth/login" || currentRoute === "/auth/register";
  const isOnboardingRoute = currentRoute === "/onboarding";
  const isSettingsRoute = currentRoute === "/settings/skin-profile";

  const getHeaderInfo = () => {
    if (currentRoute === "/auth/login") {
      return { title: "Sign In", subtitle: "ToneTrace Authentication" };
    }
    if (currentRoute === "/auth/register") {
      return { title: "Register", subtitle: "Create Formulation Profile" };
    }
    if (isOnboardingRoute) {
      return { title: "Onboarding", subtitle: "Skin Profile Verification" };
    }
    if (isSettingsRoute) {
      return { title: "Skin Profile", subtitle: "Formulation Preferences" };
    }
    if (isProductDetailRoute) {
      return { title: "Product Detail", subtitle: "Formulation & Scientific Evidence" };
    }
    if (isDiscoveryRoute) {
      return { title: "Product Discovery", subtitle: "Cosmetic Formulation Catalogue" };
    }
    if (currentRoute === "/scan") {
      return { title: "OCR Scanner", subtitle: "Formulation Verification" };
    }
    if (currentRoute === "/skin/track") {
      return { title: "Skin Story", subtitle: "Visual Check-in & History" };
    }
    if (currentRoute === "/ai/ask") {
      return { title: "Grounded AI", subtitle: "Scientific Formulation Q&A" };
    }

    switch (activeTab) {
      case "shelf":
        return { title: "My Shelf", subtitle: "Formulation Inventory & Scans" };
      case "routines":
        return { title: "Routines & Reminders", subtitle: "Scheduled Check-ins & Reactions" };
      case "profile":
        return { title: "User Account", subtitle: "Session & Skin Profile" };
      case "showcase":
        return { title: "Design System", subtitle: "ToneTrace UI Primitives & Tokens" };
      case "home":
      default:
        return { title: "ToneTrace AI", subtitle: "Cosmetic Formulation Science" };
    }
  };

  const headerInfo = getHeaderInfo();

  return (
    <MobileShell
      activeTab={activeTab}
      onTabChange={handleTabChange}
      headerTitle={headerInfo.title}
      headerSubtitle={headerInfo.subtitle}
      backendHealthy={backendHealthy}
      hideNav={isAuthRoute || isOnboardingRoute}
    >
      {/* Auth Public Routes */}
      {currentRoute === "/auth/login" && <LoginPage onNavigate={navigate} />}
      {currentRoute === "/auth/register" && <RegisterPage onNavigate={navigate} />}

      {/* Onboarding Route (Protected, but allows incomplete onboarding state) */}
      {isOnboardingRoute && (
        <ProtectedRoute onNavigate={navigate} allowIncompleteOnboarding={true}>
          <OnboardingPage onNavigate={navigate} />
        </ProtectedRoute>
      )}

      {/* Skin Profile Editor Route */}
      {isSettingsRoute && (
        <ProtectedRoute onNavigate={navigate} allowIncompleteOnboarding={true}>
          <SkinProfileEditorPage onNavigate={navigate} />
        </ProtectedRoute>
      )}

      {/* Core Dashboard Protected Route */}
      {currentRoute === "/" && (
        <ProtectedRoute onNavigate={navigate}>
          <DashboardPage onNavigate={navigate} onNavigateTab={handleTabChange} />
        </ProtectedRoute>
      )}

      {/* Product Discovery Route */}
      {isDiscoveryRoute && (
        <ProtectedRoute onNavigate={navigate}>
          <DiscoveryPage onNavigate={navigate} />
        </ProtectedRoute>
      )}

      {/* Product Detail Route */}
      {isProductDetailRoute && (
        <ProtectedRoute onNavigate={navigate}>
          <ProductDetailPage productId={productId} onNavigate={navigate} />
        </ProtectedRoute>
      )}

      {/* Quick Action Routes */}
      {currentRoute === "/scan" && (
        <ProtectedRoute onNavigate={navigate}>
          <div className="space-y-4 text-left">
            <ScanLabelModal
              isOpen={true}
              onClose={() => navigate("/")}
            />
          </div>
        </ProtectedRoute>
      )}

      {currentRoute === "/skin/track" && (
        <ProtectedRoute onNavigate={navigate}>
          <SkinTrackPlaceholder onNavigate={navigate} />
        </ProtectedRoute>
      )}

      {currentRoute === "/ai/ask" && (
        <ProtectedRoute onNavigate={navigate}>
          <AiAskPlaceholder onNavigate={navigate} />
        </ProtectedRoute>
      )}

      {(currentRoute === "/shelf" || isShelfDetailRoute) && (
        <ProtectedRoute onNavigate={navigate}>
          <ShelfPage onNavigate={navigate} initialItemId={shelfItemId} />
        </ProtectedRoute>
      )}

      {currentRoute === "/routines" && (
        <ProtectedRoute onNavigate={navigate}>
          <RoutinesPage onNavigate={navigate} />
        </ProtectedRoute>
      )}

      {currentRoute === "/profile" && (
        <ProtectedRoute onNavigate={navigate}>
          <ProfilePage onNavigate={navigate} />
        </ProtectedRoute>
      )}

      {currentRoute === "/showcase" && <DesignSystemShowcase />}
    </MobileShell>
  );
};

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
};

export default App;
