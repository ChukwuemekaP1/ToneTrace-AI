import React, { useState } from "react";
import { MobileShell, NavTab } from "@/components/layout/MobileShell";
import { AppHome } from "@/pages/AppHome";
import { DesignSystemShowcase } from "@/pages/DesignSystemShowcase";
import { ShelfPlaceholder, RoutinesPlaceholder, ProfilePlaceholder } from "@/pages/Placeholders";

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<NavTab>("home");
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);

  const getHeaderInfo = () => {
    switch (activeTab) {
      case "shelf":
        return { title: "My Shelf", subtitle: "Formulation Inventory & Scans" };
      case "routines":
        return { title: "Routines & Reminders", subtitle: "Scheduled Check-ins & Reactions" };
      case "profile":
        return { title: "Skin Profile", subtitle: "Sensitivities, Timezone & Consents" };
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
      onTabChange={setActiveTab}
      headerTitle={headerInfo.title}
      headerSubtitle={headerInfo.subtitle}
      backendHealthy={backendHealthy}
    >
      {activeTab === "home" && (
        <AppHome
          onNavigateTab={setActiveTab}
          onHealthChange={setBackendHealthy}
        />
      )}
      {activeTab === "shelf" && <ShelfPlaceholder />}
      {activeTab === "routines" && <RoutinesPlaceholder />}
      {activeTab === "profile" && <ProfilePlaceholder />}
      {activeTab === "showcase" && <DesignSystemShowcase />}
    </MobileShell>
  );
};

export default App;
