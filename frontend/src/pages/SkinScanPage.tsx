import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  Camera,
  AlertCircle,
  CheckCircle2,
  Trash2,
  Info,
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
import { Chip } from "@/components/ui/Chip";
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

  // Deep link scan by initialScanId if provided
  useEffect(() => {
    if (initialScanId && isValidUuid(initialScanId)) {
      skinService
        .getScan(initialScanId, false)
        .then((scan) => setCurrentScan(scan))
        .catch(() => {});
    }
  }, [initialScanId]);

  // Handle granting consent directly on the scan page
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
        setConsentError("Could not update privacy consent.");
      }
    } finally {
      setConsentUpdating(false);
    }
  };

  // ---------------------------------------------------------------------------
  // 2. File Selection & Client-Side Validation
  // ---------------------------------------------------------------------------
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setValidationError(null);
    const file = e.target.files?.[0];
    if (!file) return;

    if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
      setValidationError("Unsupported file format. Please upload a JPEG, PNG, or WebP photograph.");
      return;
    }

    if (file.size > MAX_SCAN_FILE_SIZE_BYTES) {
      setValidationError(
        `File size (${(file.size / (1024 * 1024)).toFixed(1)} MB) exceeds the maximum allowed limit of 10 MB.`
      );
      return;
    }

    setSelectedFile(file);
    const previewUrl = URL.createObjectURL(file);
    setFilePreview(previewUrl);
  };

  const handleClearSelectedFile = () => {
    setSelectedFile(null);
    if (filePreview) {
      URL.revokeObjectURL(filePreview);
      setFilePreview(null);
    }
    setValidationError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  // ---------------------------------------------------------------------------
  // 3. Scan Upload & Polling
  // ---------------------------------------------------------------------------
  const handleSubmitScan = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile || isSubmitting) return;

    setIsSubmitting(true);
    setScanError(null);
    setProcessingStatus("Uploading encrypted facial photo...");

    const formData = new FormData();
    formData.append("file", selectedFile);
    formData.append(
      "idempotency_key",
      `scan_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`
    );
    formData.append("lighting_condition", lightingCondition);
    formData.append("camera_angle", cameraAngle);
    formData.append("cosmetics_worn", cosmeticsWorn ? "true" : "false");
    if (captureNotes.trim()) {
      formData.append("capture_notes", captureNotes.trim());
    }

    try {
      let scan = await skinService.createScan(formData);
      setCurrentScan(scan);

      // Handle asynchronous processing if returned
      if (scan.status === "processing") {
        setProcessingStatus("Evaluating visual surface metrics with optical model...");
        let attempts = 0;
        const maxAttempts = 8;
        const scanId = scan.id;

        while (attempts < maxAttempts && scan.status === "processing") {
          attempts += 1;
          await new Promise((r) => setTimeout(r, 1200 + attempts * 400));
          scan = await skinService.pollScan(scanId);
          setCurrentScan(scan);
        }
      }

      if (scan.status === "failed") {
        setScanError(
          scan.error_message ||
            "Skin analysis could not be completed. Please ensure your face is well-lit and clearly visible."
        );
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setScanError(err.message || "Failed to process skin scan.");
      } else {
        setScanError("Network communication error while analyzing facial photo.");
      }
    } finally {
      setIsSubmitting(false);
      setProcessingStatus(null);
    }
  };

  // ---------------------------------------------------------------------------
  // 4. Scan Deletion Workflow
  // ---------------------------------------------------------------------------
  const handleConfirmDeleteScan = async () => {
    if (!currentScan || isDeleting) return;

    setIsDeleting(true);
    try {
      const res = await skinService.deleteScan(currentScan.id);
      setCurrentScan(null);
      handleClearSelectedFile();
      setShowDeleteModal(false);
      setDeleteSuccessMessage(
        res.message || "Scan and associated private photos permanently deleted."
      );
      setTimeout(() => setDeleteSuccessMessage(null), 4000);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setScanError(err.message || "Failed to delete scan.");
      } else {
        setScanError("Network error while deleting scan.");
      }
      setShowDeleteModal(false);
    } finally {
      setIsDeleting(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Render: Loading Consent Verification
  // ---------------------------------------------------------------------------
  if (checkingConsent) {
    return (
      <div className="py-16 text-center space-y-3">
        <Loader2 className="w-6 h-6 animate-spin text-emerald-400 mx-auto" />
        <p className="text-xs text-slate-400">Verifying biometric privacy permissions...</p>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Consent Gate (Absent or Revoked)
  // ---------------------------------------------------------------------------
  if (!hasConsent) {
    return (
      <div className="space-y-4 text-left pb-16">
        <div className="space-y-1 pt-1">
          <h1 className="text-xl font-bold tracking-tight text-white leading-tight">
            Facial <span className="font-serif italic font-normal text-champagne">Scan</span>
          </h1>
          <p className="text-xs text-slate-400">
            Privacy-first surface analysis and non-clinical visual tracking.
          </p>
        </div>

        <GlassCard variant="accent" className="p-5 space-y-4 text-left">
          <div className="w-10 h-10 rounded-2xl bg-amber-500/10 border border-amber-500/20 text-amber-400 flex items-center justify-center">
            <ShieldAlert className="w-5 h-5" />
          </div>

          <div className="space-y-1.5">
            <h2 className="text-sm font-bold text-white tracking-tight">
              Explicit Privacy Consent Required
            </h2>
            <p className="text-xxs text-slate-300 leading-relaxed">
              Facial skin analysis processes photographs of your face to measure surface appearance
              attributes (such as visible redness, texture smoothness, pores, and tone evenness).
            </p>
          </div>

          <div className="p-3 rounded-xl bg-[#090D11] border border-white/8 space-y-2 text-xxs text-slate-300">
            <div className="flex items-center gap-1.5 text-white font-semibold">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              <span>Our Privacy Guarantees</span>
            </div>
            <ul className="space-y-1 list-disc list-inside text-[11px] text-slate-400 leading-normal">
              <li>Photos are stored in private, encrypted cloud storage.</li>
              <li>Used solely for computing cosmetic surface tracking metrics.</li>
              <li>Never used for third-party biometric identification or ad targeting.</li>
              <li>You can permanently purge all stored photos and observations anytime.</li>
            </ul>
          </div>

          <div className="p-2.5 rounded-xl bg-indigo-950/30 border border-indigo-500/30 text-indigo-200 text-xxs flex items-start gap-2">
            <Info className="w-3.5 h-3.5 shrink-0 mt-0.5 text-indigo-400" />
            <p className="leading-normal">{NON_CLINICAL_DISCLAIMER}</p>
          </div>

          {consentError && (
            <div className="p-2.5 rounded-xl bg-rose-950/40 border border-rose-500/40 text-rose-300 text-xxs flex items-center gap-1.5">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              <span>{consentError}</span>
            </div>
          )}

          <div className="pt-2 flex flex-col sm:flex-row gap-2">
            <Button
              variant="primary"
              size="sm"
              onClick={handleGrantConsent}
              disabled={consentUpdating}
              className="w-full font-bold flex items-center justify-center gap-1.5"
            >
              {consentUpdating ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Recording Consent...</span>
                </>
              ) : (
                <>
                  <ShieldCheck className="w-3.5 h-3.5" />
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
  // Render: Active Consent - Scan Interface
  // ---------------------------------------------------------------------------
  return (
    <div className="space-y-4 text-left pb-16">
      {/* Header */}
      <div className="space-y-1 pt-1">
        <div className="flex items-center justify-between">
          <div>
            <h1 aria-label="Facial Scan" className="text-xl font-bold tracking-tight text-white leading-tight">
              Facial <span className="font-serif italic font-normal text-champagne">Scan</span>
            </h1>
            <p className="text-xs text-slate-400">
              Calibrated visual surface tracking and observation metrics.
            </p>
          </div>

          {onNavigate && (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => onNavigate("/skin/story")}
              className="flex items-center gap-1 text-xxs px-2.5"
            >
              <span>Skin Story</span>
              <ArrowRight className="w-3 h-3" />
            </Button>
          )}
        </div>
      </div>

      {deleteSuccessMessage && (
        <div className="p-3 rounded-2xl bg-emerald-950/40 border border-emerald-500/40 text-emerald-300 text-xxs flex items-center gap-1.5">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{deleteSuccessMessage}</span>
        </div>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* Active Scan Results Display                                         */}
      {/* ------------------------------------------------------------------- */}
      {currentScan && currentScan.status === "succeeded" ? (
        <div className="space-y-4 animate-in fade-in duration-200">
          {/* Provider Mock vs Live Notice */}
          {currentScan.provider === "mock" && (
            <div className="p-3 rounded-2xl bg-amber-950/40 border border-amber-500/40 text-amber-200 text-xxs space-y-1">
              <div className="flex items-center gap-1.5 font-bold text-amber-300">
                <Info className="w-3.5 h-3.5" />
                <span>Demo / Simulated Analysis Environment</span>
              </div>
              <p className="text-amber-200/90 leading-normal">
                This instance is operating with a local deterministic mock engine. Surface metrics
                are simulated for system testing and do not represent optical sensor telemetry.
              </p>
            </div>
          )}

          {/* Non-Diagnostic Disclaimer Card */}
          <div className="p-3 rounded-2xl bg-[#0C1217] border border-white/8 text-slate-300 text-xxs space-y-1.5">
            <span className="font-semibold text-white block">Non-Clinical Policy Notice</span>
            <p className="leading-relaxed text-slate-400">
              {currentScan.non_diagnostic_disclaimer || NON_CLINICAL_DISCLAIMER}
            </p>
          </div>

          {/* Scan Overview Summary */}
          <GlassCard variant="accent" className="p-4 space-y-3">
            <div className="flex items-start justify-between gap-2">
              <div>
                <span className="text-xxs font-bold uppercase tracking-wider text-slate-400 block">
                  Scan Observations
                </span>
                <span className="text-xs text-slate-300 block">
                  Captured {new Date(currentScan.created_at).toLocaleDateString()} at{" "}
                  {new Date(currentScan.created_at).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </div>

              <div className="flex items-center gap-1.5 shrink-0">
                <Chip variant="verified" size="sm" className="capitalize">
                  {currentScan.status}
                </Chip>
                <Chip variant="neutral" size="sm" className="font-mono text-slate-400">
                  {currentScan.provider}
                </Chip>
              </div>
            </div>

            {/* Average Visual Metric Index (if computed by backend) */}
            {currentScan.overall_score !== null && currentScan.overall_score !== undefined && (
              <div className="p-3 rounded-xl bg-[#090D11] border border-white/8 flex items-center justify-between">
                <div>
                  <span className="text-xxs font-bold text-white block">
                    Observed Metric Average
                  </span>
                  <span className="text-[10px] text-slate-400 block">
                    Mathematical mean of surface observations (not a health diagnosis)
                  </span>
                </div>
                <span className="text-lg font-mono font-bold text-emerald-400">
                  {currentScan.overall_score}
                  <span className="text-xs text-slate-500">/100</span>
                </span>
              </div>
            )}

            {/* Observations Grid */}
            <div className="space-y-2 pt-1">
              <span className="text-xxs font-bold uppercase tracking-wider text-slate-500 block">
                Normalized Observations ({currentScan.observations.length})
              </span>

              {currentScan.observations.length === 0 ? (
                <div className="p-4 text-center text-slate-400 text-xxs">
                  No visual observations were detected for this image.
                </div>
              ) : (
                <div className="space-y-2">
                  {currentScan.observations.map((obs: SkinObservationResponse) => (
                    <div
                      key={obs.id}
                      className="p-3 rounded-xl bg-[#090D11] border border-white/6 space-y-1.5 text-xxs"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold text-white block truncate">
                          {obs.metric_label}
                        </span>
                        <span className="font-mono font-bold text-emerald-400 shrink-0 text-xs">
                          {obs.display_value}{" "}
                          <span className="text-[10px] text-slate-500">
                            {obs.unit === "score_0_100" ? "/ 100" : obs.unit}
                          </span>
                        </span>
                      </div>

                      <div className="flex items-center gap-2 text-[10px] text-slate-400">
                        <span className="capitalize">Zone: {obs.facial_zone || "Full Face"}</span>
                        <span>•</span>
                        <span className="capitalize">
                          {obs.directionality === "higher_is_better"
                            ? "Higher is clearer"
                            : "Direct score"}
                        </span>
                        <span>•</span>
                        <span className="font-mono text-slate-500">
                          {obs.provider_name}
                          {obs.provider_model_version ? ` (${obs.provider_model_version})` : ""}
                        </span>
                      </div>

                      {obs.caveat_note && (
                        <p className="text-[10px] text-slate-500 leading-normal pt-0.5">
                          {obs.caveat_note}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Scan Footer Actions */}
            <div className="pt-3 border-t border-white/8 flex items-center justify-between gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowDeleteModal(true)}
                className="text-slate-400 hover:text-rose-400 text-xxs flex items-center gap-1"
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
                  className="text-xxs"
                >
                  New Scan
                </Button>

                {onNavigate && (
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => onNavigate("/skin/story")}
                    className="text-xxs font-bold"
                  >
                    View in Skin Story
                  </Button>
                )}
              </div>
            </div>
          </GlassCard>
        </div>
      ) : (
        /* ------------------------------------------------------------------- */
        /* Upload & Capture Form                                               */
        /* ------------------------------------------------------------------- */
        <form onSubmit={handleSubmitScan} className="space-y-4">
          {/* Lighting & Framing Guidance Dropdown */}
          <div className="rounded-2xl bg-[#0C1217] border border-white/8 overflow-hidden text-xxs">
            <button
              type="button"
              onClick={() => setShowGuidance((prev) => !prev)}
              className="w-full p-3 flex items-center justify-between text-slate-300 hover:text-white"
            >
              <div className="flex items-center gap-1.5 font-semibold">
                <Sun className="w-3.5 h-3.5 text-amber-400" />
                <span>Lighting & Framing Guidance</span>
              </div>
              {showGuidance ? (
                <ChevronUp className="w-3.5 h-3.5 text-slate-400" />
              ) : (
                <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
              )}
            </button>

            {showGuidance && (
              <div className="p-3 pt-0 border-t border-white/5 space-y-2 text-slate-400 leading-normal">
                <ul className="space-y-1 list-disc list-inside text-[11px]">
                  <li>
                    <strong className="text-white">Neutral Lighting:</strong> Diffused daylight or
                    soft white room lighting. Avoid yellow bulbs, harsh direct flash, or strong backlighting.
                  </li>
                  <li>
                    <strong className="text-white">Framing:</strong> Hold phone directly at eye level.
                    Keep facial expression relaxed and neutral.
                  </li>
                  <li>
                    <strong className="text-white">Preparation:</strong> Clean, bare skin yields the
                    most consistent observations. If wearing cosmetics, mark the checkbox below.
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
                className="border-2 border-dashed border-white/15 hover:border-emerald-500/50 rounded-2xl p-6 flex flex-col items-center justify-center gap-2 cursor-pointer transition-all bg-[#090D11]/60"
              >
                <div className="w-12 h-12 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center">
                  <Camera className="w-6 h-6" />
                </div>
                <div className="text-center space-y-0.5">
                  <span className="text-xs font-bold text-white block">
                    Take Photo or Select File
                  </span>
                  <span className="text-[11px] text-slate-400 block">
                    Supported: JPEG, PNG, WebP (up to 10 MB)
                  </span>
                </div>
              </label>
            ) : (
              <div className="space-y-2">
                <div className="relative rounded-2xl overflow-hidden max-h-64 border border-white/10 bg-black flex items-center justify-center">
                  <img
                    src={filePreview}
                    alt="Facial scan preview"
                    className="w-full h-auto object-cover max-h-64"
                  />
                  <button
                    type="button"
                    onClick={handleClearSelectedFile}
                    className="absolute top-2 right-2 p-1.5 rounded-full bg-slate-950/80 text-slate-300 hover:text-rose-400 border border-white/10"
                    aria-label="Remove selected image"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
                <div className="flex items-center justify-between text-xxs text-slate-400 px-1">
                  <span className="truncate">{selectedFile?.name}</span>
                  <span>{((selectedFile?.size || 0) / (1024 * 1024)).toFixed(2)} MB</span>
                </div>
              </div>
            )}

            {validationError && (
              <div className="p-2.5 rounded-xl bg-rose-950/40 border border-rose-500/40 text-rose-300 text-xxs flex items-center gap-1.5">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                <span>{validationError}</span>
              </div>
            )}
          </GlassCard>

          {/* Capture Conditions Form */}
          {selectedFile && (
            <GlassCard variant="default" className="p-4 space-y-3 text-xxs">
              <span className="text-xxs font-bold uppercase tracking-wider text-slate-400 block">
                Capture Context Calibration
              </span>

              <div className="grid grid-cols-2 gap-2.5">
                <div className="space-y-1">
                  <label htmlFor="lighting-condition-select" className="text-slate-300 font-semibold block">
                    Ambient Lighting
                  </label>
                  <select
                    id="lighting-condition-select"
                    value={lightingCondition}
                    onChange={(e) => setLightingCondition(e.target.value)}
                    className="w-full text-xs p-2 rounded-xl bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
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
                  <label htmlFor="camera-angle-select" className="text-slate-300 font-semibold block">
                    Camera Angle
                  </label>
                  <select
                    id="camera-angle-select"
                    value={cameraAngle}
                    onChange={(e) => setCameraAngle(e.target.value)}
                    className="w-full text-xs p-2 rounded-xl bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                  >
                    <option value="frontal">Frontal</option>
                    <option value="slight_angle">Slight Angle</option>
                    <option value="unknown">Unknown</option>
                  </select>
                </div>
              </div>

              {/* Cosmetics Worn Checkbox */}
              <label className="flex items-center gap-2 p-2.5 rounded-xl bg-[#090D11] border border-white/8 cursor-pointer">
                <input
                  type="checkbox"
                  id="cosmetics-worn-checkbox"
                  checked={cosmeticsWorn}
                  onChange={(e) => setCosmeticsWorn(e.target.checked)}
                  className="rounded border-white/20 text-emerald-500 w-4 h-4 focus:ring-0"
                />
                <span className="text-slate-300">
                  Cosmetics, makeup, or tinted sunscreen was present during capture
                </span>
              </label>

              {/* Capture Notes */}
              <div className="space-y-1">
                <label htmlFor="capture-notes-input" className="text-slate-300 font-semibold block">
                  Optional Capture Note (max 300 chars)
                </label>
                <input
                  id="capture-notes-input"
                  type="text"
                  maxLength={300}
                  value={captureNotes}
                  onChange={(e) => setCaptureNotes(e.target.value)}
                  placeholder="e.g. Post-cleansing, morning routine check-in"
                  className="w-full text-xs p-2 rounded-xl bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                />
              </div>
            </GlassCard>
          )}

          {scanError && (
            <div className="p-3 rounded-2xl bg-rose-950/40 border border-rose-500/40 text-rose-300 text-xxs flex items-center justify-between">
              <span>{scanError}</span>
              <button
                type="button"
                onClick={() => setScanError(null)}
                className="underline font-semibold ml-2 text-rose-200"
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
            className="w-full font-bold flex items-center justify-center gap-2"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>{processingStatus || "Processing Photo..."}</span>
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
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
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/85 backdrop-blur-md animate-in fade-in duration-150"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-scan-title"
        >
          <div className="w-full max-w-sm bg-[#0E141B] border border-rose-500/30 rounded-2xl p-5 shadow-2xl text-center space-y-3">
            <div className="w-10 h-10 rounded-full bg-rose-950/50 border border-rose-500/40 text-rose-400 mx-auto flex items-center justify-center">
              <Trash2 className="w-5 h-5" />
            </div>

            <div className="space-y-1">
              <h3 id="delete-scan-title" className="text-sm font-bold text-white">
                Delete Skin Scan?
              </h3>
              <p className="text-xxs text-slate-400 leading-normal">
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
