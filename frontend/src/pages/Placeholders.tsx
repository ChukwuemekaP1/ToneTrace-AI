import React from "react";
import { BookmarkCheck, Calendar, User } from "lucide-react";
import { EmptyState } from "@/components/ui/EmptyState";
import { Chip } from "@/components/ui/Chip";

export const ShelfPlaceholder: React.FC = () => (
  <div className="space-y-4 text-left">
    <div className="flex items-center justify-between">
      <h2 className="text-base font-bold text-white tracking-tight">My Shelf</h2>
      <Chip variant="neutral" size="sm">Phase 1 Integration</Chip>
    </div>
    <EmptyState
      icon={<BookmarkCheck className="w-6 h-6 text-emerald-400" />}
      title="Personal Shelf & Catalog Discovery"
      description="Endpoints verified: GET/POST /api/v1/me/shelf and GET /api/v1/discovery/products. Business implementation begins in Phase 1 without mock data."
    />
  </div>
);

export const RoutinesPlaceholder: React.FC = () => (
  <div className="space-y-4 text-left">
    <div className="flex items-center justify-between">
      <h2 className="text-base font-bold text-white tracking-tight">Routines & Reminders</h2>
      <Chip variant="neutral" size="sm">Phase 1 Integration</Chip>
    </div>
    <EmptyState
      icon={<Calendar className="w-6 h-6 text-amber-400" />}
      title="Routines & Safety-Aware Reactions"
      description="Endpoints verified: /api/v1/me/routines, /api/v1/me/reminders, and /api/v1/me/product-reactions. No invented backend data is shown."
    />
  </div>
);

export const ProfilePlaceholder: React.FC = () => (
  <div className="space-y-4 text-left">
    <div className="flex items-center justify-between">
      <h2 className="text-base font-bold text-white tracking-tight">User Profile & Sensitivities</h2>
      <Chip variant="neutral" size="sm">Phase 1 Integration</Chip>
    </div>
    <EmptyState
      icon={<User className="w-6 h-6 text-champagne" />}
      title="Skin Profile, Timezone & Consents"
      description="Endpoints verified: /api/v1/me, /api/v1/me/skin-profile, /api/v1/me/sensitivities, and /api/v1/me/consents. Ready for Phase 1 form binding."
    />
  </div>
);
