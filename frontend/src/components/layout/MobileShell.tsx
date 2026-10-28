import React from "react";
import { Sparkles, Compass, BookmarkCheck, Calendar, User, Code2 } from "lucide-react";

export type NavTab = "home" | "shelf" | "routines" | "profile" | "showcase";

export interface MobileShellProps {
  children: React.ReactNode;
  activeTab?: NavTab;
  onTabChange?: (tab: NavTab) => void;
  headerTitle?: string;
  headerSubtitle?: string;
  headerAction?: React.ReactNode;
  backendHealthy?: boolean | null;
}

export const MobileShell: React.FC<MobileShellProps> = ({
  children,
  activeTab = "home",
  onTabChange,
  headerTitle = "ToneTrace AI",
  headerSubtitle = "Cosmetic Formulation Science",
  headerAction,
  backendHealthy = null,
}) => {
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
                      backendHealthy ? "bg-emerald-400 shadow-[0_0_8px_#34D399]" : "bg-amber-400 shadow-[0_0_8px_#FBBF24]"
                    }`}
                    title={backendHealthy ? "Backend connected" : "Backend offline or connecting..."}
                  />
                )}
              </div>
              <p className="text-xxs text-slate-400 mt-0.5 leading-none">{headerSubtitle}</p>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            {headerAction}
          </div>
        </header>

        {/* Main Content Body */}
        <main className="flex-1 w-full px-3.5 sm:px-4 py-4 pb-24 overflow-y-auto">
          {children}
        </main>

        {/* Bottom Tab Navigation Bar */}
        <nav
          data-testid="mobile-bottom-nav"
          className="fixed bottom-0 left-1/2 -translate-x-1/2 w-full max-w-[430px] z-40 bg-[#0C1217]/95 backdrop-blur-xl border-t border-white/[0.08] px-3 py-2 flex items-center justify-around shadow-glass"
        >
          <button
            type="button"
            onClick={() => onTabChange?.("home")}
            className={`flex flex-col items-center gap-1 py-1 px-2.5 rounded-xl transition-all ${
              activeTab === "home" ? "text-emerald-400 font-semibold" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Compass className="w-5 h-5" />
            <span className="text-xxs tracking-tight">Explore</span>
          </button>

          <button
            type="button"
            onClick={() => onTabChange?.("shelf")}
            className={`flex flex-col items-center gap-1 py-1 px-2.5 rounded-xl transition-all ${
              activeTab === "shelf" ? "text-emerald-400 font-semibold" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <BookmarkCheck className="w-5 h-5" />
            <span className="text-xxs tracking-tight">Shelf</span>
          </button>

          <button
            type="button"
            onClick={() => onTabChange?.("routines")}
            className={`flex flex-col items-center gap-1 py-1 px-2.5 rounded-xl transition-all ${
              activeTab === "routines" ? "text-emerald-400 font-semibold" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Calendar className="w-5 h-5" />
            <span className="text-xxs tracking-tight">Routines</span>
          </button>

          <button
            type="button"
            onClick={() => onTabChange?.("profile")}
            className={`flex flex-col items-center gap-1 py-1 px-2.5 rounded-xl transition-all ${
              activeTab === "profile" ? "text-emerald-400 font-semibold" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <User className="w-5 h-5" />
            <span className="text-xxs tracking-tight">Profile</span>
          </button>

          <button
            type="button"
            onClick={() => onTabChange?.("showcase")}
            className={`flex flex-col items-center gap-1 py-1 px-2.5 rounded-xl transition-all ${
              activeTab === "showcase" ? "text-champagne font-semibold" : "text-slate-400 hover:text-slate-200"
            }`}
            title="Design System Showcase"
          >
            <Code2 className="w-5 h-5" />
            <span className="text-xxs tracking-tight">Showcase</span>
          </button>
        </nav>
      </div>
    </div>
  );
};
