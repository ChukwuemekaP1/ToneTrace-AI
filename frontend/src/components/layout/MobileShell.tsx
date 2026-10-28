import React, { useState } from "react";
import {
  Sparkles,
  Compass,
  BookmarkCheck,
  Calendar,
  User,
  Code2,
  Camera,
  MoreHorizontal,
  X,
} from "lucide-react";

export type NavTab = "home" | "shelf" | "routines" | "profile" | "showcase" | "scan";

export interface MobileShellProps {
  children: React.ReactNode;
  activeTab?: NavTab;
  onTabChange?: (tab: NavTab) => void;
  headerTitle?: string;
  headerSubtitle?: string;
  headerAction?: React.ReactNode;
  backendHealthy?: boolean | null;
  hideNav?: boolean;
}

export const MobileShell: React.FC<MobileShellProps> = ({
  children,
  activeTab = "home",
  onTabChange,
  headerTitle = "ToneTrace AI",
  headerSubtitle = "Cosmetic Formulation Science",
  headerAction,
  backendHealthy = null,
  hideNav = false,
}) => {
  const [showMoreMenu, setShowMoreMenu] = useState(false);

  const handleSelectTab = (tab: NavTab) => {
    setShowMoreMenu(false);
    onTabChange?.(tab);
  };

  return (
    <div className="min-h-screen w-full bg-[#040608] flex justify-center items-start antialiased text-slate-100 overflow-x-hidden">
      {/* 
        Mobile Device Container:
        - Baseline: 390px
        - Tested responsive: 360px to 430px
        - On wider screens: Centered maximum-430px container
      */}
      <div
        data-testid="mobile-shell-container"
        className="w-full max-w-[430px] min-h-screen flex flex-col relative bg-[#090D11] border-x border-white/[0.07] shadow-2xl overflow-x-hidden"
      >
        {/* Top Status Bar / Header */}
        <header className="sticky top-0 z-30 bg-[#090D11]/90 backdrop-blur-md border-b border-white/[0.08] px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-emerald-600 to-emerald-400 p-0.5 flex items-center justify-center shadow-glow shrink-0">
              <div className="w-full h-full bg-[#090D11] rounded-[10px] flex items-center justify-center">
                <Sparkles className="w-4 h-4 text-emerald-400" />
              </div>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-sm font-bold tracking-tight text-white leading-none">
                  {headerTitle}
                </h1>
                {backendHealthy !== null && (
                  <span
                    data-testid="backend-health-pill"
                    className={`inline-block w-2 h-2 rounded-full ${
                      backendHealthy
                        ? "bg-emerald-400 shadow-[0_0_8px_#34D399]"
                        : "bg-amber-400 shadow-[0_0_8px_#FBBF24]"
                    }`}
                    title={backendHealthy ? "Backend connected" : "Backend offline or connecting..."}
                  />
                )}
              </div>
              <p className="text-xxs text-slate-400 mt-0.5 leading-none">{headerSubtitle}</p>
            </div>
          </div>

          <div className="flex items-center gap-1.5">{headerAction}</div>
        </header>

        {/* Main Content Body */}
        <main className="flex-1 w-full px-3.5 sm:px-4 py-4 pb-28 overflow-y-auto">
          {children}
        </main>

        {/* Three-Button Floating Navigation Dock */}
        {!hideNav && (
          <div className="fixed bottom-3 left-1/2 -translate-x-1/2 w-[calc(100%-1.5rem)] max-w-[400px] z-40">
            {/* Expandable Discoverability Menu */}
            <div
              className={
                showMoreMenu
                  ? "mb-2 p-2.5 rounded-2xl bg-[#0C1217]/95 backdrop-blur-xl border border-white/12 shadow-2xl grid grid-cols-3 gap-2 animate-in fade-in slide-in-from-bottom-2 duration-150"
                  : "sr-only"
              }
              aria-label="Additional navigation options"
            >
              <button
                type="button"
                onClick={() => handleSelectTab("routines")}
                aria-label="Routines"
                className={`flex flex-col items-center gap-1 p-2 rounded-xl border transition-all text-xxs ${
                  activeTab === "routines"
                    ? "bg-emerald-950/40 border-emerald-500/40 text-emerald-400 font-semibold"
                    : "bg-white/[0.03] border-white/5 text-slate-300 hover:border-white/15"
                }`}
              >
                <Calendar className="w-4 h-4" />
                <span>Routines</span>
              </button>

              <button
                type="button"
                onClick={() => handleSelectTab("profile")}
                aria-label="Profile"
                className={`flex flex-col items-center gap-1 p-2 rounded-xl border transition-all text-xxs ${
                  activeTab === "profile"
                    ? "bg-emerald-950/40 border-emerald-500/40 text-emerald-400 font-semibold"
                    : "bg-white/[0.03] border-white/5 text-slate-300 hover:border-white/15"
                }`}
              >
                <User className="w-4 h-4" />
                <span>Profile</span>
              </button>

              <button
                type="button"
                onClick={() => handleSelectTab("showcase")}
                aria-label="Showcase"
                title="Design System Showcase"
                className={`flex flex-col items-center gap-1 p-2 rounded-xl border transition-all text-xxs ${
                  activeTab === "showcase"
                    ? "bg-champagne/20 border-champagne/40 text-champagne font-semibold"
                    : "bg-white/[0.03] border-white/5 text-slate-300 hover:border-white/15"
                }`}
              >
                <Code2 className="w-4 h-4" />
                <span>Showcase</span>
              </button>
            </div>

            {/* Three Primary Floating Buttons Bar */}
            <nav
              data-testid="mobile-bottom-nav"
              aria-label="Primary navigation"
              className="w-full bg-[#0C1217]/90 backdrop-blur-2xl border border-white/12 rounded-2xl px-3 py-1.5 flex items-center justify-between shadow-glass"
            >
              {/* Button 1: Home */}
              <button
                type="button"
                aria-label="Home"
                onClick={() => handleSelectTab("home")}
                className={`flex flex-col items-center gap-0.5 py-1 px-3 rounded-xl transition-all ${
                  activeTab === "home"
                    ? "text-emerald-400 font-semibold"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Compass className="w-5 h-5" />
                <span className="text-xxs tracking-tight">Home</span>
              </button>

              {/* Button 2: Scan (Hero Action) */}
              <button
                type="button"
                aria-label="Scan a Label"
                onClick={() => handleSelectTab("scan")}
                className="flex flex-col items-center -translate-y-2 group focus:outline-none"
              >
                <div className="w-11 h-11 rounded-full bg-gradient-to-tr from-emerald-600 to-emerald-400 p-0.5 shadow-glow flex items-center justify-center transition-transform group-hover:scale-105 active:scale-95">
                  <div className="w-full h-full bg-[#090D11] rounded-full flex items-center justify-center">
                    <Camera className="w-5 h-5 text-emerald-400" />
                  </div>
                </div>
                <span className="text-xxs tracking-tight text-emerald-400 font-medium mt-0.5">
                  Scan
                </span>
              </button>

              {/* Button 3: Shelf */}
              <button
                type="button"
                aria-label="Shelf"
                onClick={() => handleSelectTab("shelf")}
                className={`flex flex-col items-center gap-0.5 py-1 px-3 rounded-xl transition-all ${
                  activeTab === "shelf"
                    ? "text-emerald-400 font-semibold"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <BookmarkCheck className="w-5 h-5" />
                <span className="text-xxs tracking-tight">Shelf</span>
              </button>

              {/* More / Discoverability Toggle */}
              <button
                type="button"
                aria-label="More navigation options"
                aria-expanded={showMoreMenu}
                onClick={() => setShowMoreMenu((prev) => !prev)}
                className={`p-1.5 rounded-xl transition-colors ${
                  showMoreMenu
                    ? "text-white bg-white/10"
                    : "text-slate-400 hover:text-slate-200"
                }`}
                title="More navigation"
              >
                {showMoreMenu ? (
                  <X className="w-4 h-4" />
                ) : (
                  <MoreHorizontal className="w-4 h-4" />
                )}
              </button>
            </nav>
          </div>
        )}
      </div>
    </div>
  );
};
