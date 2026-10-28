import React from "react";
import {
  BookmarkCheck,
  Calendar,
  User,
  Camera,
  Sparkles,
  MessageSquareQuote,
  Compass,
} from "lucide-react";
import { EmptyState } from "@/components/ui/EmptyState";
import { Chip } from "@/components/ui/Chip";

interface PlaceholderProps {
  onNavigate?: (route: string) => void;
}

export const ShelfPlaceholder: React.FC<PlaceholderProps> = ({ onNavigate }) => (
  <div className="space-y-4 text-left">
    <div className="flex items-center justify-between">
      <h2 className="text-base font-bold text-white tracking-tight">My Shelf</h2>
      <Chip variant="verified" size="sm">Phase 4 Scope</Chip>
    </div>
    <EmptyState
      icon={<BookmarkCheck className="w-6 h-6 text-emerald-400" />}
      title="Personal Shelf & Catalog Discovery"
      description="Endpoints verified: GET/POST /api/v1/me/shelf and GET /api/v1/discovery/products. Shelf inventory management begins in Phase 4."
      actionLabel="Back to Home"
      onAction={onNavigate ? () => onNavigate("/") : undefined}
    />
  </div>
);

export const RoutinesPlaceholder: React.FC<PlaceholderProps> = ({ onNavigate }) => (
  <div className="space-y-4 text-left">
    <div className="flex items-center justify-between">
      <h2 className="text-base font-bold text-white tracking-tight">Routines & Reminders</h2>
      <Chip variant="verified" size="sm">Phase 5 Scope</Chip>
    </div>
    <EmptyState
      icon={<Calendar className="w-6 h-6 text-amber-400" />}
      title="Routines & Safety-Aware Reactions"
      description="Endpoints verified: /api/v1/me/routines, /api/v1/me/reminders, and /api/v1/me/product-reactions. Full routine editing begins in Phase 5."
      actionLabel="Back to Home"
      onAction={onNavigate ? () => onNavigate("/") : undefined}
    />
  </div>
);

export const ProfilePlaceholder: React.FC<PlaceholderProps> = ({ onNavigate }) => (
  <div className="space-y-4 text-left">
    <div className="flex items-center justify-between">
      <h2 className="text-base font-bold text-white tracking-tight">User Profile & Sensitivities</h2>
      <Chip variant="verified" size="sm">Phase 1 Integration</Chip>
    </div>
    <EmptyState
      icon={<User className="w-6 h-6 text-champagne" />}
      title="Skin Profile, Timezone & Consents"
      description="Endpoints verified: /api/v1/me, /api/v1/me/skin-profile, /api/v1/me/sensitivities, and /api/v1/me/consents."
      actionLabel="Back to Home"
      onAction={onNavigate ? () => onNavigate("/") : undefined}
    />
  </div>
);

export const ScanPlaceholder: React.FC<PlaceholderProps> = ({ onNavigate }) => (
  <div className="space-y-4 text-left">
    <div className="flex items-center justify-between">
      <h2 className="text-base font-bold text-white tracking-tight">Label OCR Scanner</h2>
      <Chip variant="verified" size="sm">Verified Endpoint</Chip>
    </div>
    <EmptyState
      icon={<Camera className="w-6 h-6 text-emerald-400" />}
      title="Formulation Label OCR"
      description="Endpoints verified: POST /api/v1/ocr/scans and POST /api/v1/ocr/scans/{id}/confirm. Multipart OCR upload begins in dedicated scanner phase."
      actionLabel="Back to Dashboard"
      onAction={onNavigate ? () => onNavigate("/") : undefined}
    />
  </div>
);

export const SkinTrackPlaceholder: React.FC<PlaceholderProps> = ({ onNavigate }) => (
  <div className="space-y-4 text-left">
    <div className="flex items-center justify-between">
      <h2 className="text-base font-bold text-white tracking-tight">Skin Story & Tracking</h2>
      <Chip variant="verified" size="sm">Verified Endpoint</Chip>
    </div>
    <EmptyState
      icon={<Sparkles className="w-6 h-6 text-champagne" />}
      title="Calibrated Visual Skin Check-in"
      description="Endpoints verified: POST /api/v1/skin/scans and GET /api/v1/skin/story. Non-clinical visual observation workflow begins in skin tracker phase."
      actionLabel="Back to Dashboard"
      onAction={onNavigate ? () => onNavigate("/") : undefined}
    />
  </div>
);

export const AiAskPlaceholder: React.FC<PlaceholderProps> = ({ onNavigate }) => (
  <div className="space-y-4 text-left">
    <div className="flex items-center justify-between">
      <h2 className="text-base font-bold text-white tracking-tight">Grounded Scientific AI</h2>
      <Chip variant="verified" size="sm">Verified Endpoint</Chip>
    </div>
    <EmptyState
      icon={<MessageSquareQuote className="w-6 h-6 text-emerald-400" />}
      title="Formulation Inquiry"
      description="Endpoints verified: POST /api/v1/ai/explanations. Grounded single-turn question-answering with citation source IDs."
      actionLabel="Back to Dashboard"
      onAction={onNavigate ? () => onNavigate("/") : undefined}
    />
  </div>
);

export const ExplorePlaceholder: React.FC<PlaceholderProps> = ({ onNavigate }) => (
  <div className="space-y-4 text-left">
    <div className="flex items-center justify-between">
      <h2 className="text-base font-bold text-white tracking-tight">Product Discovery</h2>
      <Chip variant="verified" size="sm">Verified Endpoint</Chip>
    </div>
    <EmptyState
      icon={<Compass className="w-6 h-6 text-emerald-400" />}
      title="Catalogue Discovery"
      description="Endpoints verified: GET /api/v1/discovery/products and GET /api/v1/search/products with sensitivity exclusion."
      actionLabel="Back to Dashboard"
      onAction={onNavigate ? () => onNavigate("/") : undefined}
    />
  </div>
);
