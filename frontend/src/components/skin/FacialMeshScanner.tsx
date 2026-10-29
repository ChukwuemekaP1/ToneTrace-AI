import React, { useState } from "react";
import { Sparkles, Scan, Eye, Camera, RefreshCw } from "lucide-react";

export type FacialZone =
  | "forehead"
  | "cheeks"
  | "left_cheek"
  | "right_cheek"
  | "t_zone"
  | "chin"
  | "periorbital"
  | "full_face";

export interface ZoneObservationSummary {
  zone: FacialZone;
  metricLabel: string;
  displayValue: number;
  status: "clear" | "mild" | "concern";
  summary?: string;
}

export interface FacialMeshScannerProps {
  imageSrc: string | null;
  isScanning?: boolean;
  selectedZone?: FacialZone | null;
  onSelectZone?: (zone: FacialZone) => void;
  zoneObservations?: ZoneObservationSummary[];
  onRetake?: () => void;
  className?: string;
}

export const FacialMeshScanner: React.FC<FacialMeshScannerProps> = ({
  imageSrc,
  isScanning = false,
  selectedZone = null,
  onSelectZone,
  zoneObservations = [],
  onRetake,
  className = "",
}) => {
  const [showMesh, setShowMesh] = useState(true);

  // Map zone to observations
  const getObservationForZone = (zone: FacialZone) => {
    return zoneObservations.find(
      (z) => z.zone === zone || (zone === "cheeks" && (z.zone === "left_cheek" || z.zone === "right_cheek"))
    );
  };

  const activeObs = selectedZone ? getObservationForZone(selectedZone) : null;

  return (
    <div className={`relative rounded-3xl overflow-hidden bg-slate-900 border border-slate-200 shadow-card ${className}`}>
      {/* Visual Canvas Viewport */}
      <div className="relative w-full aspect-[4/5] max-h-[460px] flex items-center justify-center overflow-hidden bg-gradient-to-b from-slate-900 via-slate-800 to-slate-900 select-none">
        {/* Base Image */}
        {imageSrc ? (
          <img
            src={imageSrc}
            alt="Facial skin scan capture"
            className={`w-full h-full object-cover transition-all duration-300 ${
              isScanning ? "scale-105 filter brightness-95" : ""
            }`}
          />
        ) : (
          <div className="flex flex-col items-center justify-center p-6 text-center text-slate-400 space-y-2">
            <Camera className="w-10 h-10 text-slate-500 animate-pulse" />
            <span className="text-xs">No facial photo loaded</span>
          </div>
        )}

        {/* Luminous Facial 3D Mesh Wireframe (SVG Overlay) */}
        {showMesh && (
          <svg
            viewBox="0 0 400 500"
            className="absolute inset-0 w-full h-full pointer-events-none transition-opacity duration-300"
          >
            <defs>
              {/* Glowing cyan gradient for scanner beam */}
              <linearGradient id="scanBeamGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#38BDF8" stopOpacity="0" />
                <stop offset="50%" stopColor="#06B6D4" stopOpacity="0.8" />
                <stop offset="100%" stopColor="#2DD4BF" stopOpacity="0" />
              </linearGradient>

              {/* Glowing zone filters */}
              <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
                <feGaussianBlur stdDeviation="3" result="blur" />
                <feComposite in="SourceGraphic" in2="blur" operator="over" />
              </filter>
            </defs>

            {/* Canonical Golden Ratio & Facial Geometry Mesh Lines (Image 1 & Image 2) */}
            <g stroke="#38BDF8" strokeWidth="1" strokeOpacity="0.45" fill="none">
              {/* Outer Facial Contour Oval */}
              <ellipse cx="200" cy="245" rx="115" ry="155" strokeDasharray="3 3" strokeOpacity="0.3" />

              {/* Vertical Symmetry Axis */}
              <line x1="200" y1="90" x2="200" y2="400" strokeDasharray="4 4" strokeWidth="1.2" strokeOpacity="0.6" />

              {/* Horizontal Facial Thirds Lines */}
              <line x1="100" y1="165" x2="300" y2="165" strokeOpacity="0.35" /> {/* Brow line */}
              <line x1="110" y1="240" x2="290" y2="240" strokeOpacity="0.35" /> {/* Nose base */}
              <line x1="130" y1="315" x2="270" y2="315" strokeOpacity="0.35" /> {/* Lip line */}

              {/* Facial Fifths Vertical Alignment */}
              <line x1="145" y1="140" x2="145" y2="320" strokeOpacity="0.2" strokeDasharray="2 2" />
              <line x1="255" y1="140" x2="255" y2="320" strokeOpacity="0.2" strokeDasharray="2 2" />

              {/* Geometric Cheeks & Jawline Triangular Mesh (Image 2 style) */}
              {/* Forehead polygon */}
              <polygon points="200,100 150,140 250,140" />
              <polygon points="150,140 120,165 200,165" />
              <polygon points="250,140 280,165 200,165" />

              {/* Eye Orbitals / Periorbital */}
              <polygon points="140,185 175,180 185,200 150,205" />
              <polygon points="260,185 225,180 215,200 250,205" />

              {/* Nose & Nasal Bridge (T-Zone) */}
              <polygon points="200,165 185,240 200,245" />
              <polygon points="200,165 215,240 200,245" />

              {/* Left Cheek Triangular Mesh */}
              <polygon points="120,195 150,210 135,270" />
              <polygon points="135,270 175,255 160,320" />
              <polygon points="120,195 135,270 105,250" />

              {/* Right Cheek Triangular Mesh */}
              <polygon points="280,195 250,210 265,270" />
              <polygon points="265,270 225,255 240,320" />
              <polygon points="280,195 265,270 295,250" />

              {/* Mouth & Chin Contour */}
              <polygon points="170,305 200,295 230,305 200,325" />
              <polygon points="160,320 200,325 240,320 200,370" />
              <polygon points="200,370 170,390 230,390" />

              {/* Sparkling Intersecting Nodes */}
              <circle cx="200" cy="165" r="2.5" fill="#38BDF8" />
              <circle cx="150" cy="180" r="2" fill="#38BDF8" />
              <circle cx="250" cy="180" r="2" fill="#38BDF8" />
              <circle cx="185" cy="240" r="2" fill="#38BDF8" />
              <circle cx="215" cy="240" r="2" fill="#38BDF8" />
              <circle cx="200" cy="245" r="3" fill="#2DD4BF" filter="url(#glow)" />
              <circle cx="135" cy="270" r="2.5" fill="#38BDF8" />
              <circle cx="265" cy="270" r="2.5" fill="#38BDF8" />
              <circle cx="200" cy="370" r="2.5" fill="#38BDF8" />
            </g>

            {/* Interactive Clickable Problem Zones with Highlights */}
            {/* Forehead Zone */}
            <g
              onClick={() => onSelectZone?.("forehead")}
              className="cursor-pointer transition-all duration-300 pointer-events-auto"
            >
              <polygon
                points="130,110 270,110 280,165 120,165"
                fill={
                  selectedZone === "forehead"
                    ? "rgba(56, 189, 248, 0.28)"
                    : "transparent"
                }
                stroke={selectedZone === "forehead" ? "#38BDF8" : "transparent"}
                strokeWidth="2"
                filter={selectedZone === "forehead" ? "url(#glow)" : undefined}
              />
            </g>

            {/* Cheeks Zone (Left & Right) */}
            <g
              onClick={() => onSelectZone?.("cheeks")}
              className="cursor-pointer transition-all duration-300 pointer-events-auto"
            >
              {/* Left Cheek */}
              <polygon
                points="105,185 175,200 175,260 140,310 95,250"
                fill={
                  selectedZone === "cheeks" || selectedZone === "left_cheek"
                    ? "rgba(56, 189, 248, 0.28)"
                    : "transparent"
                }
                stroke={
                  selectedZone === "cheeks" || selectedZone === "left_cheek"
                    ? "#38BDF8"
                    : "transparent"
                }
                strokeWidth="2"
                filter={selectedZone === "cheeks" ? "url(#glow)" : undefined}
              />
              {/* Right Cheek */}
              <polygon
                points="295,185 225,200 225,260 260,310 305,250"
                fill={
                  selectedZone === "cheeks" || selectedZone === "right_cheek"
                    ? "rgba(56, 189, 248, 0.28)"
                    : "transparent"
                }
                stroke={
                  selectedZone === "cheeks" || selectedZone === "right_cheek"
                    ? "#38BDF8"
                    : "transparent"
                }
                strokeWidth="2"
                filter={selectedZone === "cheeks" ? "url(#glow)" : undefined}
              />
            </g>

            {/* T-Zone / Nose Area */}
            <g
              onClick={() => onSelectZone?.("t_zone")}
              className="cursor-pointer transition-all duration-300 pointer-events-auto"
            >
              <polygon
                points="175,160 225,160 220,255 180,255"
                fill={
                  selectedZone === "t_zone"
                    ? "rgba(56, 189, 248, 0.28)"
                    : "transparent"
                }
                stroke={selectedZone === "t_zone" ? "#38BDF8" : "transparent"}
                strokeWidth="2"
                filter={selectedZone === "t_zone" ? "url(#glow)" : undefined}
              />
            </g>

            {/* Periorbital / Under-Eye Zone */}
            <g
              onClick={() => onSelectZone?.("periorbital")}
              className="cursor-pointer transition-all duration-300 pointer-events-auto"
            >
              <ellipse
                cx="160"
                cy="195"
                rx="28"
                ry="18"
                fill={
                  selectedZone === "periorbital"
                    ? "rgba(56, 189, 248, 0.28)"
                    : "transparent"
                }
                stroke={selectedZone === "periorbital" ? "#38BDF8" : "transparent"}
                strokeWidth="2"
                filter={selectedZone === "periorbital" ? "url(#glow)" : undefined}
              />
              <ellipse
                cx="240"
                cy="195"
                rx="28"
                ry="18"
                fill={
                  selectedZone === "periorbital"
                    ? "rgba(56, 189, 248, 0.28)"
                    : "transparent"
                }
                stroke={selectedZone === "periorbital" ? "#38BDF8" : "transparent"}
                strokeWidth="2"
                filter={selectedZone === "periorbital" ? "url(#glow)" : undefined}
              />
            </g>

            {/* Chin Zone */}
            <g
              onClick={() => onSelectZone?.("chin")}
              className="cursor-pointer transition-all duration-300 pointer-events-auto"
            >
              <polygon
                points="155,335 245,335 230,395 170,395"
                fill={
                  selectedZone === "chin"
                    ? "rgba(56, 189, 248, 0.28)"
                    : "transparent"
                }
                stroke={selectedZone === "chin" ? "#38BDF8" : "transparent"}
                strokeWidth="2"
                filter={selectedZone === "chin" ? "url(#glow)" : undefined}
              />
            </g>
          </svg>
        )}

        {/* Luminous Scanning Laser Sweep (when isScanning is True) */}
        {isScanning && (
          <div className="absolute inset-0 pointer-events-none overflow-hidden">
            <div className="w-full h-24 bg-gradient-to-b from-cyan-400/0 via-cyan-400/40 to-teal-400/0 animate-[scanSweep_2.4s_ease-in-out_infinite] border-b-2 border-cyan-300 shadow-[0_0_20px_#06b6d4]" />
            <div className="absolute top-4 left-4 flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-900/80 backdrop-blur-md border border-cyan-400/40 text-cyan-300 text-xxs font-mono">
              <Scan className="w-3.5 h-3.5 animate-spin" />
              <span>SCANNING FACIAL BIOMETRIC ZONES...</span>
            </div>
          </div>
        )}

        {/* Floating Top Status Chips */}
        <div className="absolute top-3 left-3 right-3 flex items-center justify-between pointer-events-none">
          {/* Golden Ratio Alignment Tag (Image 1 style) */}
          <div className="px-2.5 py-1 rounded-full bg-black/60 backdrop-blur-md border border-white/20 text-white text-[10px] font-mono flex items-center gap-1.5 pointer-events-auto">
            <Sparkles className="w-3 h-3 text-cyan-400" />
            <span>GOLDEN RATIO OVERLAY 91%: EXCELLENT</span>
          </div>

          {/* Toggle Mesh visibility button */}
          <button
            type="button"
            onClick={() => setShowMesh(!showMesh)}
            className="p-1.5 rounded-full bg-black/60 backdrop-blur-md border border-white/20 text-white hover:text-cyan-300 transition-colors pointer-events-auto"
            title="Toggle Wireframe Mesh"
          >
            <Eye className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Floating Zone Diagnostic Callout Pin (when a zone is highlighted) */}
        {selectedZone && activeObs && (
          <div className="absolute bottom-4 left-4 right-4 p-3 rounded-2xl bg-white/95 backdrop-blur-xl border border-cyan-400/40 shadow-xl flex items-center justify-between animate-in fade-in slide-in-from-bottom-2 duration-200">
            <div>
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-cyan-500 animate-ping" />
                <span className="text-xxs font-bold uppercase tracking-wider text-slate-700">
                  Target Zone: <strong className="text-slate-950 font-black">{selectedZone.replace("_", " ")}</strong>
                </span>
              </div>
              <p className="text-xs font-semibold text-slate-900 mt-0.5">
                {activeObs.metricLabel}: <span className="font-mono text-brand font-bold">{activeObs.displayValue}%</span>
              </p>
              {activeObs.summary && (
                <p className="text-[10px] text-slate-500 leading-tight">{activeObs.summary}</p>
              )}
            </div>

            <button
              type="button"
              onClick={() => onSelectZone?.("full_face")}
              className="text-xxs text-slate-400 hover:text-slate-600 underline ml-2"
            >
              Reset
            </button>
          </div>
        )}
      </div>

      {/* Viewport Control Bar */}
      <div className="p-3 bg-white border-t border-slate-100 flex items-center justify-between text-xxs text-slate-600">
        <div className="flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-full bg-brand" />
          <span>Interactive 3D Face Viewport (Tap zones to inspect)</span>
        </div>

        {onRetake && (
          <button
            type="button"
            onClick={onRetake}
            className="flex items-center gap-1 text-slate-500 hover:text-slate-800 font-medium transition-colors"
          >
            <RefreshCw className="w-3 h-3" />
            <span>Retake Photo</span>
          </button>
        )}
      </div>
    </div>
  );
};
