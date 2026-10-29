import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  Camera,
  AlertCircle,
  CheckCircle2,
  Trash2,
  Loader2,
  Sparkles,
  Sun,
  ShieldCheck,
  ShieldAlert,
  ArrowRight,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { GlassCard } from "@/components/ui/GlassCard";
import { FacialMeshScanner, FacialZone, ZoneObservationSummary } from "@/components/skin/FacialMeshScanner";
import { FacialRadarChart, RadarDataPoint } from "@/components/skin/FacialRadarChart";
import { skinService, isValidUuid } from "@/api/skin";
import { profileService } from "@/api/profile";
import {
  SkinScanResponse,
  SkinObservationResponse,
  ApiError,
  UserConsentResponse,
} from "@/api/types";

export interface SkinScanPageProps {
  onNavigate?: (route: string) => void;
  initialScanId?: string | null;
}

export const ACCEPTED_CONSENT_PURPOSES = ["skin_data_processing", "facial_scan_processing"];
export const MAX_SCAN_FILE_SIZE_BYTES = 10 * 1024 * 1024; // 10MB
export const ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];

export const NON_CLINICAL_DISCLAIMER =
  "Visual surface observations are derived from 2D photographs for cosmetic tracking only. They do not infer the underlying cause of pigmentation, do not diagnose any dermatological or medical condition, and do not substitute for an in-person clinical evaluation.";

export const VARIABILITY_NOTICE =
  "Lighting, angle, device camera, image quality, and skin preparation affect comparability. Surface observations do not constitute a medical diagnosis.";

export const SkinScanPage: React.FC<SkinScanPageProps> = ({
  onNavigate,
  initialScanId,
}) => {
  // Consent state
  const [checkingConsent, setCheckingConsent] = useState<boolean>(true);
  const [hasConsent, setHasConsent] = useState<boolean>(false);
  const [consentUpdating, setConsentUpdating] = useState<boolean>(false);
  const [consentError, setConsentError] = useState<string | null>(null);

  // File & Upload state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [filePreview, setFilePreview] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Capture Conditions state
  const [lightingCondition, setLightingCondition] = useState<string>("natural_daylight");
  const [cameraAngle, setCameraAngle] = useState<string>("frontal");
  const [cosmeticsWorn, setCosmeticsWorn] = useState<boolean>(false);
  const [captureNotes, setCaptureNotes] = useState<string>("");
  const [showGuidance, setShowGuidance] = useState<boolean>(false);

  // Processing & Scan Result state
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [processingStatus, setProcessingStatus] = useState<string | null>(null);
  const [currentScan, setCurrentScan] = useState<SkinScanResponse | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);

  // Interactive UI state (Zone selection & category filtering)
  const [selectedZone, setSelectedZone] = useState<FacialZone | null>(null);
  const [activeCategory, setActiveCategory] = useState<string>("all");

  // Delete modal state
  const [showDeleteModal, setShowDeleteModal] = useState<boolean>(false);
  const [isDeleting, setIsDeleting] = useState<boolean>(false);
  const [deleteSuccessMessage, setDeleteSuccessMessage] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // 1. Consent Verification
  // ---------------------------------------------------------------------------
  const verifyConsent = useCallback(async () => {
    setCheckingConsent(true);
    setConsentError(null);
    try {
      const consents: UserConsentResponse[] = await profileService.listConsents();
      const active = consents.some(
        (c) =>
          ACCEPTED_CONSENT_PURPOSES.includes(c.purpose) &&
          c.is_granted === true &&
          !c.revoked_at
      );
      setHasConsent(active);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setConsentError(err.message || "Failed to verify privacy consent.");
      } else {
        setConsentError("Unable to connect to account privacy settings.");
      }
      setHasConsent(false);
    } finally {
      setCheckingConsent(false);
    }
  }, []);

  useEffect(() => {
    verifyConsent();
  }, [verifyConsent]);

  // Load initial scan if requested
  useEffect(() => {
    if (initialScanId && isValidUuid(initialScanId)) {
      skinService
        .getScan(initialScanId)
        .then((scan) => setCurrentScan(scan))
        .catch(() => {
          // Silently ignore if not found
        });
    }
  }, [initialScanId]);

  // ---------------------------------------------------------------------------
  // 2. Consent Grant Action
  // ---------------------------------------------------------------------------
  const handleGrantConsent = async () => {
    setConsentUpdating(true);
    setConsentError(null);
    try {
      await profileService.updateConsent("skin_data_processing", {
        is_granted: true,
        policy_version: "1.0.0",
      });
      setHasConsent(true);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setConsentError(err.message || "Failed to record privacy consent.");
      } else {
        setConsentError("Network connection error granting consent.");
      }
    } finally {
      setConsentUpdating(false);
    }
  };

  // ---------------------------------------------------------------------------
  // 3. File Input & Validation
  // ---------------------------------------------------------------------------
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setValidationError(null);
    setScanError(null);
    const file = e.target.files?.[0];
    if (!file) return;

    if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
      setValidationError("Unsupported file format. Please upload a JPEG, PNG, or WebP photograph.");
      return;
    }
    if (file.size > MAX_SCAN_FILE_SIZE_BYTES) {
      setValidationError("Image file size exceeds the maximum allowed limit of 10 MB.");
      return;
    }

    setSelectedFile(file);
    const objectUrl = URL.createObjectURL(file);
    setFilePreview(objectUrl);
  };

  const handleClearSelectedFile = () => {
    if (filePreview) {
      URL.revokeObjectURL(filePreview);
    }
    setSelectedFile(null);
    setFilePreview(null);
    setValidationError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  // ---------------------------------------------------------------------------
  // 4. Scan Submission & Polling
  // ---------------------------------------------------------------------------
  const handleSubmitScan = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setValidationError("Please select or capture a facial photograph first.");
      return;
    }

    setIsSubmitting(true);
    setScanError(null);
    setProcessingStatus("Initializing facial scan telemetry...");

    const formData = new FormData();
    formData.append("file", selectedFile);
    formData.append("lighting_condition", lightingCondition);
    formData.append("camera_angle", cameraAngle);
    formData.append("cosmetics_worn", cosmeticsWorn ? "true" : "false");
    if (captureNotes.trim()) {
      formData.append("user_notes", captureNotes.trim());
    }

    try {
      setProcessingStatus("Running multimodal optical skin analysis...");
      const scan = await skinService.createScan(formData);

      if (scan.status === "succeeded") {
        setCurrentScan(scan);
      } else if (scan.status === "processing") {
        setProcessingStatus("Calibrating optical observations...");
        const finalScan = await pollScanStatus(scan.id);
        setCurrentScan(finalScan);
      } else {
        setScanError(scan.error_message || "Skin analysis could not be completed.");
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setScanError(err.message || "Failed to process skin scan.");
      } else {
        setScanError("Network communication failure during facial scan.");
      }
    } finally {
      setIsSubmitting(false);
      setProcessingStatus(null);
    }
  };

  const pollScanStatus = async (
    scanId: string,
    maxAttempts = 10,
    delayMs = 1500
  ): Promise<SkinScanResponse> => {
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise((resolve) => setTimeout(resolve, delayMs));
      const res = await skinService.getScan(scanId);
      if (res.status === "succeeded" || res.status === "failed") {
        return res;
      }
    }
    throw new Error("Scan processing timed out. Please check again in a few moments.");
  };

  // ---------------------------------------------------------------------------
  // 5. Delete Scan
  // ---------------------------------------------------------------------------
  const handleConfirmDeleteScan = async () => {
    if (!currentScan) return;
    setIsDeleting(true);
    try {
      await skinService.deleteScan(currentScan.id);
      setCurrentScan(null);
      handleClearSelectedFile();
      setDeleteSuccessMessage("Scan record and private photos permanently deleted.");
      setShowDeleteModal(false);
    } catch {
      setScanError("Failed to delete scan record.");
    } finally {
      setIsDeleting(false);
    }
  };

  // Filter observations based on active category pill
  const filteredObservations = (currentScan?.observations || []).filter((obs) => {
    if (activeCategory === "all") return true;
    if (activeCategory === "cheeks") {
      return obs.facial_zone?.includes("cheek");
    }
    if (activeCategory === "t_zone") {
      return obs.facial_zone === "t_zone" || obs.facial_zone === "forehead";
    }
    if (activeCategory === "eyes") {
      return obs.facial_zone === "periorbital" || obs.metric_code.includes("eye") || obs.metric_code.includes("circle");
    }
    return true;
  });

  // Map observations to ZoneObservationSummary for the 3D mesh
  const zoneSummaries: ZoneObservationSummary[] = (currentScan?.observations || []).map((obs) => ({
    zone: (obs.facial_zone as FacialZone) || "full_face",
    metricLabel: obs.metric_label,
    displayValue: obs.display_value,
    status: obs.display_value >= 75 ? "clear" : obs.display_value >= 50 ? "mild" : "concern",
    summary: `${obs.metric_label} score: ${obs.display_value}%`,
  }));

  // Build Radar data from observations
  const radarData: RadarDataPoint[] = (() => {
    if (!currentScan?.observations || currentScan.observations.length === 0) return [];
    const getVal = (code: string, fallback: number) => {
      const match = currentScan.observations.find((o) => o.metric_code.includes(code));
      return match ? match.display_value : fallback;
    };

    return [
      { label: "Skin Health", value: currentScan.overall_score || 80 },
      { label: "Eye Harmony", value: getVal("dark_circles", 78) },
      { label: "Smoothness", value: getVal("texture", 75) },
      { label: "Pore Refinement", value: getVal("pores", 72) },
      { label: "Clarity", value: getVal("acne", 85) },
    ];
  })();

  // ---------------------------------------------------------------------------
  // Render: Loading Consent Gate
  // ---------------------------------------------------------------------------
  if (checkingConsent) {
    return (
      <div className="flex flex-col items-center justify-center p-12 space-y-3">
        <Loader2 className="w-8 h-8 animate-spin text-brand" />
        <p className="text-xs text-slate-500 font-medium">Verifying privacy consent protocols...</p>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Consent Missing Gate
  // ---------------------------------------------------------------------------
  if (!hasConsent) {
    return (
      <div className="space-y-4 text-left max-w-md mx-auto pt-4">
        <GlassCard variant="elevated" className="p-6 space-y-4 border-slate-200">
          <div className="w-12 h-12 rounded-2xl bg-brand/10 border border-brand/20 text-brand flex items-center justify-center">
            <ShieldAlert className="w-6 h-6" />
          </div>

          <div className="space-y-1.5">
            <h2 className="text-base font-bold text-slate-900">
              Explicit Privacy Consent Required
            </h2>
            <p className="text-xs text-slate-600 leading-relaxed">
              Facial skin analysis processes photographs of your face using private, on-device and secure cloud vision analysis to track cosmetic skin concerns. Under biometric privacy regulations, we require your explicit, informed consent before uploading or analyzing any facial photographs.
            </p>
          </div>

          <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-xxs text-slate-600 space-y-1">
            <span className="font-semibold text-slate-800 block">Our Privacy Commitments:</span>
            <ul className="list-disc list-inside space-y-0.5">
              <li>Images are stored in private, isolated storage buckets with signed URLs.</li>
              <li>Never used for biometric surveillance, cross-site identity, or ad targeting.</li>
              <li>You can permanently delete your scans and purge photos anytime.</li>
            </ul>
          </div>

          {consentError && (
            <div className="p-2.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xxs flex items-center gap-1.5">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              <span>{consentError}</span>
            </div>
          )}

          <div className="pt-2 flex flex-col gap-2">
            <Button
              variant="primary"
              size="md"
              onClick={handleGrantConsent}
              disabled={consentUpdating}
              className="w-full font-bold bg-charcoal text-white hover:bg-slate-800"
            >
              {consentUpdating ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin mr-1.5" />
                  <span>Recording Consent...</span>
                </>
              ) : (
                <>
                  <ShieldCheck className="w-4 h-4 mr-1.5 text-brand" />
                  <span>Grant Facial Analysis Consent</span>
                </>
              )}
            </Button>

            {onNavigate && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => onNavigate("/settings/skin-profile")}
                className="w-full text-xxs"
              >
                Review in Settings
              </Button>
            )}
          </div>
        </GlassCard>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Active Scan Results Display
  // ---------------------------------------------------------------------------
  return (
    <div className="space-y-4 text-left pb-16">
      {/* Header */}
      <div className="space-y-1 pt-1">
        <div className="flex items-center justify-between">
          <div>
            <h1 aria-label="Facial Scan" className="text-xl font-bold tracking-tight text-slate-900 leading-tight">
              Facial <span className="font-serif italic font-normal text-brand">Analysis</span>
            </h1>
            <p className="text-xs text-slate-500">
              Calibrated visual surface tracking and AI observation telemetry.
            </p>
          </div>

          {onNavigate && (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => onNavigate("/skin/story")}
              className="flex items-center gap-1 text-xxs px-2.5 bg-white text-slate-700 border-slate-200"
            >
              <span>Skin Story</span>
              <ArrowRight className="w-3 h-3" />
            </Button>
          )}
        </div>
      </div>

      {deleteSuccessMessage && (
        <div className="p-3 rounded-2xl bg-brand/10 border border-brand/20 text-brand text-xxs flex items-center gap-1.5">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{deleteSuccessMessage}</span>
        </div>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* Active Scan Results Display                                         */}
      {/* ------------------------------------------------------------------- */}
      {currentScan && currentScan.status === "succeeded" ? (
        <div className="space-y-4 animate-in fade-in duration-200">
          {/* Demo / Simulated badge when running in mock or non-production environment */}
          {(currentScan.provider === "mock" ||
            Boolean(currentScan.is_mock) ||
            (currentScan.provider_environment && currentScan.provider_environment !== "production")) && (
            <div className="flex items-center gap-2">
              <span className="px-2.5 py-1 rounded-full bg-amber-50 border border-amber-200 text-amber-800 text-xxs font-semibold">
                Demo / Simulated Analysis Environment
              </span>
            </div>
          )}

          {/* Interactive Facial Mesh & Zone Viewport */}
          <FacialMeshScanner
            imageSrc={filePreview}
            selectedZone={selectedZone}
            onSelectZone={(zone) => setSelectedZone(zone)}
            zoneObservations={zoneSummaries}
            onRetake={() => {
              setCurrentScan(null);
              handleClearSelectedFile();
            }}
          />

          {/* Health Report Hero Card (Image 2 style) */}
          <div className="p-4 rounded-3xl bg-white border border-slate-200 shadow-soft space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-xxs font-bold uppercase tracking-wider text-slate-500 block">
                  Health Report
                </span>
                <h2 className="text-sm font-bold text-slate-900">
                  Comprehensive Visual Surface Evaluation
                </h2>
              </div>
              <span className="text-xxs font-mono text-slate-400">
                {new Date(currentScan.created_at).toLocaleDateString()}
              </span>
            </div>

            {/* Floating metrics row */}
            <div className="grid grid-cols-2 gap-2.5">
              {/* Primary Skin Health Score (Dark Charcoal Pill - Image 2) */}
              <div className="p-3 rounded-2xl bg-charcoal text-white flex flex-col justify-between">
                <span className="text-[11px] text-slate-300">Skin Health Index</span>
                <div className="flex items-baseline gap-1 mt-1">
                  <span className="text-2xl font-mono font-black text-white">
                    {currentScan.overall_score || 80}%
                  </span>
                  <span className="text-xxs text-emerald-400 font-semibold">Optimal</span>
                </div>
              </div>

              {/* Skin Type & Age Pill */}
              <div className="p-3 rounded-2xl bg-slate-50 border border-slate-200/80 flex flex-col justify-between">
                <span className="text-[11px] text-slate-500">Skin Profile Type</span>
                <div className="mt-1">
                  <span className="text-sm font-bold capitalize text-slate-900 block truncate">
                    {currentScan.skin_type_observation || "Combination"}
                  </span>
                  <span className="text-[10px] text-slate-400 font-mono">Telemetry: Live Vision</span>
                </div>
              </div>
            </div>
          </div>

          {/* Horizontal Category Navigation Tabs (Image 2 style: All, Face, Cheeks, T-Zone, Eye) */}
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 no-scrollbar select-none">
            {[
              { id: "all", label: "All Concerns" },
              { id: "face", label: "Full Face" },
              { id: "cheeks", label: "Cheeks" },
              { id: "t_zone", label: "T-Zone" },
              { id: "eyes", label: "Periorbital" },
            ].map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => {
                  setActiveCategory(tab.id);
                  if (tab.id === "cheeks") setSelectedZone("cheeks");
                  else if (tab.id === "t_zone") setSelectedZone("t_zone");
                  else if (tab.id === "eyes") setSelectedZone("periorbital");
                  else setSelectedZone(null);
                }}
                className={`px-3.5 py-1.5 rounded-full text-xxs font-medium whitespace-nowrap transition-all border ${
                  activeCategory === tab.id
                    ? "bg-brand text-white border-brand shadow-sm font-semibold"
                    : "bg-white text-slate-600 border-slate-200 hover:border-slate-300"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Clinical Observation Sliders List (Image 1 & Image 2) */}
          <GlassCard variant="default" className="p-4 space-y-3">
            <div className="flex items-center justify-between pb-1">
              <span className="text-xxs font-bold uppercase tracking-wider text-slate-500 block">
                Normalized Telemetry ({filteredObservations.length})
              </span>
              <span className="text-[10px] text-slate-400 font-mono">0-100 Clarity Scale</span>
            </div>

            <div className="space-y-3">
              {filteredObservations.map((obs: SkinObservationResponse) => {
                const isSelected =
                  selectedZone === obs.facial_zone ||
                  (selectedZone === "cheeks" && (obs.facial_zone === "left_cheek" || obs.facial_zone === "right_cheek"));

                return (
                  <div
                    key={obs.id}
                    onClick={() => setSelectedZone((obs.facial_zone as FacialZone) || "full_face")}
                    className={`p-3 rounded-2xl border transition-all cursor-pointer ${
                      isSelected
                        ? "bg-cyan-50/60 border-cyan-300 shadow-sm"
                        : "bg-slate-50/60 border-slate-200 hover:border-slate-300"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <div>
                        <span className="font-bold text-slate-900 text-xs block">
                          {obs.metric_label}
                        </span>
                        <span className="text-[10px] text-slate-500 capitalize">
                          Zone: <strong className="text-slate-700">{(obs.facial_zone || "full_face").replace("_", " ")}</strong>
                        </span>
                      </div>

                      <div className="text-right">
                        <span className="font-mono font-bold text-brand text-sm block">
                          <span>{Math.round(obs.display_value)}</span>
                          <span className="text-[10px] text-slate-400 font-normal">%</span>
                        </span>
                        <span className="text-[9px] text-slate-400">
                          {obs.display_value >= 75 ? "Clear" : obs.display_value >= 50 ? "Moderate" : "Attention"}
                        </span>
                      </div>
                    </div>

                    {/* Scientific Slider Metric Bar with Min/Avg/Ideal Markers (Image 1 style) */}
                    <div className="space-y-1">
                      <div className="relative w-full h-2 rounded-full bg-slate-200 overflow-hidden">
                        <div
                          className="h-full rounded-full bg-brand transition-all duration-500"
                          style={{ width: `${Math.max(5, Math.min(100, obs.display_value))}%` }}
                        />
                      </div>
                      <div className="flex items-center justify-between text-[9px] text-slate-400 font-mono">
                        <span>Min (0%)</span>
                        <span className="text-slate-500">Average</span>
                        <span className="text-brand font-semibold">Optimal (100%)</span>
                      </div>
                    </div>

                    {obs.caveat_note && (
                      <p className="text-[10px] text-slate-500 pt-1 leading-normal border-t border-slate-200/50 mt-2">
                        {obs.caveat_note}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          </GlassCard>

          {/* 5-Axis Facial Optimization Radar Spider Chart (Image 1) */}
          <FacialRadarChart
            data={radarData}
            overallScore={currentScan.overall_score || 80}
          />

          {/* AI Recommendation CTA Button (Image 2 style) */}
          {onNavigate && (
            <div className="p-4 rounded-3xl bg-white border border-brand/20 shadow-soft flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-10 h-10 rounded-2xl bg-brand/10 text-brand flex items-center justify-center">
                  <Sparkles className="w-5 h-5" />
                </div>
                <div>
                  <span className="text-xs font-bold text-slate-900 block">
                    AI Routine Recommendations
                  </span>
                  <p className="text-xxs text-slate-500">
                    Formulation regimens tailored to this scan
                  </p>
                </div>
              </div>

              <Button
                variant="primary"
                size="sm"
                onClick={() => onNavigate("/ask-ai")}
                className="bg-charcoal text-white text-xxs font-bold px-3 py-2"
              >
                <span>View</span>
                <ArrowRight className="w-3 h-3 ml-1" />
              </Button>
            </div>
          )}

          {/* Non-Diagnostic Disclaimer Card */}
          <div className="p-3 rounded-2xl bg-slate-100 border border-slate-200 text-slate-600 text-xxs space-y-1">
            <span className="font-semibold text-slate-800 block">Non-Clinical Notice</span>
            <p className="leading-relaxed text-slate-500 text-[10px]">
              {currentScan.non_diagnostic_disclaimer || NON_CLINICAL_DISCLAIMER}
            </p>
          </div>

          {/* Scan Footer Actions */}
          <div className="pt-2 flex items-center justify-between gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowDeleteModal(true)}
              className="text-slate-500 hover:text-rose-600 text-xxs flex items-center gap-1"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>Delete Scan</span>
            </Button>

            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  setCurrentScan(null);
                  handleClearSelectedFile();
                }}
                className="text-xxs bg-white border-slate-200"
              >
                New Scan
              </Button>

              {onNavigate && (
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => onNavigate("/skin/story")}
                  className="text-xxs font-bold bg-charcoal text-white"
                >
                  View in Skin Story
                </Button>
              )}
            </div>
          </div>
        </div>
      ) : (
        /* ------------------------------------------------------------------- */
        /* Upload & Capture Form                                               */
        /* ------------------------------------------------------------------- */
        <form onSubmit={handleSubmitScan} className="space-y-4">
          {/* Lighting & Framing Guidance Dropdown */}
          <div className="rounded-2xl bg-white border border-slate-200 overflow-hidden text-xxs shadow-soft">
            <button
              type="button"
              onClick={() => setShowGuidance((prev) => !prev)}
              className="w-full p-3 flex items-center justify-between text-slate-700 hover:text-slate-900"
            >
              <div className="flex items-center gap-1.5 font-semibold">
                <Sun className="w-3.5 h-3.5 text-amber-500" />
                <span>Lighting & Framing Guidance</span>
              </div>
              {showGuidance ? (
                <ChevronUp className="w-3.5 h-3.5 text-slate-400" />
              ) : (
                <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
              )}
            </button>

            {showGuidance && (
              <div className="p-3 pt-0 border-t border-slate-100 space-y-2 text-slate-600 leading-normal">
                <ul className="space-y-1 list-disc list-inside text-[11px]">
                  <li>
                    <strong className="text-slate-800">Neutral Lighting:</strong> Diffused daylight or
                    soft white room lighting. Avoid yellow bulbs or harsh direct flash.
                  </li>
                  <li>
                    <strong className="text-slate-800">Framing:</strong> Hold phone directly at eye level.
                    Keep facial expression relaxed and neutral.
                  </li>
                  <li>
                    <strong className="text-slate-800">Preparation:</strong> Clean, bare skin yields the
                    most consistent observations.
                  </li>
                </ul>
                <p className="text-[10px] text-slate-500 italic pt-1">{VARIABILITY_NOTICE}</p>
              </div>
            )}
          </div>

          {/* File Picker / Camera Input Card */}
          <GlassCard variant="default" className="p-4 space-y-3">
            <input
              ref={fileInputRef}
              type="file"
              id="skin-photo-input"
              aria-label="Upload facial photograph"
              accept="image/jpeg,image/png,image/webp"
              capture="user"
              onChange={handleFileChange}
              className="hidden"
            />

            {!filePreview ? (
              <label
                htmlFor="skin-photo-input"
                className="border-2 border-dashed border-slate-200 hover:border-brand rounded-3xl p-8 flex flex-col items-center justify-center gap-3 cursor-pointer transition-all bg-white hover:bg-slate-50/50 shadow-soft"
              >
                <div className="w-14 h-14 rounded-full bg-brand/10 border border-brand/20 text-brand flex items-center justify-center">
                  <Camera className="w-7 h-7" />
                </div>
                <div className="text-center space-y-1">
                  <span className="text-sm font-bold text-slate-900 block">
                    Take Face Photo or Upload
                  </span>
                  <span className="text-xs text-slate-500 block">
                    Supported: JPEG, PNG, WebP (up to 10 MB)
                  </span>
                  <span className="text-xxs font-mono text-brand font-semibold block pt-1">
                    Powered by Live Vision AI & YouCam S2S
                  </span>
                </div>
              </label>
            ) : (
              <div className="space-y-2">
                <FacialMeshScanner
                  imageSrc={filePreview}
                  isScanning={isSubmitting}
                  onRetake={handleClearSelectedFile}
                />
                <div className="flex items-center justify-between text-xxs text-slate-500 px-1 pt-1">
                  <span className="truncate">{selectedFile?.name}</span>
                  <span>{((selectedFile?.size || 0) / (1024 * 1024)).toFixed(2)} MB</span>
                </div>
              </div>
            )}

            {validationError && (
              <div className="p-2.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xxs flex items-center gap-1.5">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                <span>{validationError}</span>
              </div>
            )}
          </GlassCard>

          {/* Capture Conditions Form */}
          {selectedFile && (
            <GlassCard variant="default" className="p-4 space-y-3 text-xxs">
              <span className="text-xxs font-bold uppercase tracking-wider text-slate-500 block">
                Capture Context Calibration
              </span>

              <div className="grid grid-cols-2 gap-2.5">
                <div className="space-y-1">
                  <label htmlFor="lighting-condition-select" className="text-slate-700 font-semibold block">
                    Ambient Lighting
                  </label>
                  <select
                    id="lighting-condition-select"
                    value={lightingCondition}
                    onChange={(e) => setLightingCondition(e.target.value)}
                    className="w-full text-xs p-2 rounded-xl bg-white border border-slate-200 text-slate-800 focus:outline-none focus:border-brand"
                  >
                    <option value="natural_daylight">Natural Daylight</option>
                    <option value="indoor_warm">Indoor Warm</option>
                    <option value="indoor_cool">Indoor Cool</option>
                    <option value="ring_light">Ring Light</option>
                    <option value="dim_or_uneven">Dim / Uneven</option>
                    <option value="unknown">Unknown</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <label htmlFor="camera-angle-select" className="text-slate-700 font-semibold block">
                    Camera Angle
                  </label>
                  <select
                    id="camera-angle-select"
                    value={cameraAngle}
                    onChange={(e) => setCameraAngle(e.target.value)}
                    className="w-full text-xs p-2 rounded-xl bg-white border border-slate-200 text-slate-800 focus:outline-none focus:border-brand"
                  >
                    <option value="frontal">Frontal</option>
                    <option value="slight_angle">Slight Angle</option>
                    <option value="unknown">Unknown</option>
                  </select>
                </div>
              </div>

              {/* Cosmetics Worn Checkbox */}
              <label className="flex items-center gap-2 p-2.5 rounded-xl bg-slate-50 border border-slate-200 cursor-pointer">
                <input
                  type="checkbox"
                  id="cosmetics-worn-checkbox"
                  checked={cosmeticsWorn}
                  onChange={(e) => setCosmeticsWorn(e.target.checked)}
                  className="rounded border-slate-300 text-brand w-4 h-4 focus:ring-0"
                />
                <span className="text-slate-700">
                  Cosmetics, makeup, or tinted sunscreen was present during capture
                </span>
              </label>

              {/* Capture Notes */}
              <div className="space-y-1">
                <label htmlFor="capture-notes-input" className="text-slate-700 font-semibold block">
                  Optional Capture Note (max 300 chars)
                </label>
                <input
                  id="capture-notes-input"
                  type="text"
                  maxLength={300}
                  value={captureNotes}
                  onChange={(e) => setCaptureNotes(e.target.value)}
                  placeholder="e.g. Post-cleansing, morning routine check-in"
                  className="w-full text-xs p-2 rounded-xl bg-white border border-slate-200 text-slate-800 focus:outline-none focus:border-brand"
                />
              </div>
            </GlassCard>
          )}

          {scanError && (
            <div className="p-3 rounded-2xl bg-rose-50 border border-rose-200 text-rose-700 text-xxs flex items-center justify-between">
              <span>{scanError}</span>
              <button
                type="button"
                onClick={() => setScanError(null)}
                className="underline font-semibold ml-2 text-rose-700"
              >
                Dismiss
              </button>
            </div>
          )}

          {/* Submit Action */}
          <Button
            type="submit"
            variant="primary"
            size="md"
            disabled={!selectedFile || isSubmitting}
            className="w-full font-bold flex items-center justify-center gap-2 bg-charcoal text-white hover:bg-slate-800 py-3 rounded-2xl shadow-md"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>{processingStatus || "Analyzing Facial Telemetry..."}</span>
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4 text-brand" />
                <span>Analyze Facial Surface</span>
              </>
            )}
          </Button>

          <p className="text-[10px] text-slate-500 text-center leading-normal">
            {NON_CLINICAL_DISCLAIMER}
          </p>
        </form>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* 5. Delete Scan Confirmation Modal                                   */}
      {/* ------------------------------------------------------------------- */}
      {showDeleteModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-150"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-scan-title"
        >
          <div className="w-full max-w-sm bg-white border border-rose-200 rounded-3xl p-5 shadow-2xl text-center space-y-3">
            <div className="w-10 h-10 rounded-full bg-rose-50 border border-rose-200 text-rose-600 mx-auto flex items-center justify-center">
              <Trash2 className="w-5 h-5" />
            </div>

            <div className="space-y-1">
              <h3 id="delete-scan-title" className="text-sm font-bold text-slate-900">
                Delete Skin Scan?
              </h3>
              <p className="text-xxs text-slate-500 leading-normal">
                This will permanently delete this scan record, its visual surface observations, and
                purge all private stored photos from cloud storage. This action cannot be undone.
              </p>
            </div>

            <div className="pt-2 flex items-center justify-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setShowDeleteModal(false)}
                disabled={isDeleting}
                className="bg-slate-100 border-slate-200"
              >
                Keep Scan
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleConfirmDeleteScan}
                disabled={isDeleting}
                className="bg-rose-600 hover:bg-rose-500 text-white font-bold"
              >
                {isDeleting ? "Deleting..." : "Yes, Permanently Delete"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
