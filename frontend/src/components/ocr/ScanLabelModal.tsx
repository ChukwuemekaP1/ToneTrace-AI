import React, { useState, useRef, useEffect } from "react";
import {
  Camera,
  UploadCloud,
  CheckCircle2,
  AlertTriangle,
  X,
  Trash2,
  Plus,
  ArrowUp,
  ArrowDown,
  RefreshCw,
  FileText,
  BookmarkPlus,
  ShieldAlert,
  Loader2,
  Eye,
  EyeOff,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import {
  ocrService,
  validateImageFile,
} from "@/api/ocr";
import {
  OCRScanResponse,
  ConfirmScanResponse,
  ConfirmIngredientItem,
  ApiError,
  ShelfItemResponse,
} from "@/api/types";

export interface ScanLabelModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccessConfirm?: (result: ConfirmScanResponse) => void;
  onAddedToShelf?: (item: ShelfItemResponse) => void;
}

type ScanStep = "select" | "scanning" | "review" | "confirmed" | "error";

interface EditableCandidate {
  id?: string;
  name: string;
  position: number;
  isConfirmed: boolean;
  isUserCorrected: boolean;
  confidence?: number | null;
}

export const ScanLabelModal: React.FC<ScanLabelModalProps> = ({
  isOpen,
  onClose,
  onSuccessConfirm,
  onAddedToShelf,
}) => {
  // Step & Data state
  const [step, setStep] = useState<ScanStep>("select");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [errorCategory, setErrorCategory] = useState<string | null>(null);

  // Scan & review state
  const [scanResult, setScanResult] = useState<OCRScanResponse | null>(null);
  const [candidates, setCandidates] = useState<EditableCandidate[]>([]);
  const [confirmedResult, setConfirmedResult] = useState<ConfirmScanResponse | null>(null);
  const [showRawText, setShowRawText] = useState<boolean>(false);
  const [newIngredientName, setNewIngredientName] = useState<string>("");

  // In-flight & UI guards
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [isConfirming, setIsConfirming] = useState<boolean>(false);
  const [isSavingToShelf, setIsSavingToShelf] = useState<boolean>(false);
  const [shelfSuccessMessage, setShelfSuccessMessage] = useState<string | null>(null);
  const [assetDeleted, setAssetDeleted] = useState<boolean>(false);
  const [isDeletingAsset, setIsDeletingAsset] = useState<boolean>(false);

  // Shelf form fields
  const [shelfName, setShelfName] = useState<string>("");
  const [shelfBrand, setShelfBrand] = useState<string>("");
  const [shelfCategory, setShelfCategory] = useState<string>("Moisturizer");
  const [shelfStatus, setShelfStatus] = useState<"in_use" | "wishlist">("in_use");

  // Abort controller ref for cancellation
  const abortControllerRef = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const cameraInputRef = useRef<HTMLInputElement | null>(null);
  const modalRef = useRef<HTMLDivElement | null>(null);

  // Sync preview URL with selectedFile
  useEffect(() => {
    if (!selectedFile) {
      if (previewUrl && typeof URL !== "undefined" && typeof URL.revokeObjectURL === "function") {
        URL.revokeObjectURL(previewUrl);
      }
      setPreviewUrl(null);
      return;
    }
    if (typeof URL !== "undefined" && typeof URL.createObjectURL === "function") {
      try {
        const url = URL.createObjectURL(selectedFile);
        setPreviewUrl(url);
        return () => {
          if (typeof URL.revokeObjectURL === "function") {
            URL.revokeObjectURL(url);
          }
        };
      } catch {
        setPreviewUrl(null);
      }
    } else {
      setPreviewUrl(null);
    }
  }, [selectedFile]);

  // Reset state on open/close
  useEffect(() => {
    if (isOpen) {
      setStep("select");
      setSelectedFile(null);
      setValidationError(null);
      setErrorMessage(null);
      setErrorCategory(null);
      setScanResult(null);
      setCandidates([]);
      setConfirmedResult(null);
      setShowRawText(false);
      setNewIngredientName("");
      setIsSubmitting(false);
      setIsConfirming(false);
      setIsSavingToShelf(false);
      setShelfSuccessMessage(null);
      setAssetDeleted(false);
      setShelfName("");
      setShelfBrand("");
      setShelfCategory("Moisturizer");
    } else {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
    }
  }, [isOpen]);

  // Handle ESC key to dismiss modal when not submitting
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen && !isSubmitting && !isConfirming) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isSubmitting, isConfirming, onClose]);

  if (!isOpen) return null;

  // ---------------------------------------------------------------------------
  // 1. File Selection & Client Validation
  // ---------------------------------------------------------------------------
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setValidationError(null);
    setErrorMessage(null);
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const file = files[0];
    const validation = validateImageFile(file);
    if (!validation.valid) {
      setValidationError(validation.error || "Invalid file.");
      setSelectedFile(null);
      return;
    }

    setSelectedFile(file);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setValidationError(null);
    setErrorMessage(null);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      const validation = validateImageFile(file);
      if (!validation.valid) {
        setValidationError(validation.error || "Invalid file.");
        setSelectedFile(null);
        return;
      }
      setSelectedFile(file);
    }
  };

  // ---------------------------------------------------------------------------
  // 2. Upload & OCR Processing
  // ---------------------------------------------------------------------------
  const handleStartScan = async () => {
    if (!selectedFile || isSubmitting) return;

    setIsSubmitting(true);
    setStep("scanning");
    setErrorMessage(null);
    setErrorCategory(null);

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    // Generate unique idempotency key to prevent double submissions on retry
    const idempotencyKey = `scan_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;

    try {
      let scanData = await ocrService.uploadScan(
        selectedFile,
        idempotencyKey,
        abortController.signal
      );

      // If asynchronous job status is returned, poll until final state
      if (scanData.status === "processing") {
        scanData = await ocrService.pollScanStatus(scanData.id, {
          signal: abortController.signal,
          maxWaitMs: 25000,
        });
      }

      if (scanData.status === "failed") {
        setStep("error");
        setErrorCategory(scanData.error_category || "ocr_error");
        setErrorMessage(
          scanData.error_message ||
            "OCR extraction could not detect readable cosmetic ingredients on this label."
        );
        return;
      }

      if (scanData.candidates.length === 0 && (!scanData.raw_text || !scanData.raw_text.trim())) {
        setStep("error");
        setErrorCategory("unreadable_image");
        setErrorMessage(
          "No ingredient text could be recognized. Please check lighting and ensure ingredient list is clear and in focus."
        );
        return;
      }

      // Populate candidate items for human review
      setScanResult(scanData);
      setCandidates(
        scanData.candidates.map((c) => ({
          id: c.id,
          name: c.normalized_name,
          position: c.position,
          isConfirmed: true, // Defaults to confirmed state on review
          isUserCorrected: c.is_user_corrected,
          confidence: c.confidence,
        }))
      );
      setStep("review");
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") {
        // User voluntarily cancelled
        setStep("select");
        return;
      }

      setStep("error");
      if (err instanceof ApiError) {
        if (err.status === 429) {
          setErrorCategory("rate_limited");
          setErrorMessage("Scan quota exceeded. Please wait a few moments before trying again.");
        } else if (err.status >= 500) {
          setErrorCategory("upstream_unavailable");
          setErrorMessage("OCR server service is temporarily unavailable. Please try again later.");
        } else {
          setErrorCategory("client_error");
          setErrorMessage(err.message || "Failed to process product label.");
        }
      } else {
        setErrorCategory("network_error");
        setErrorMessage(
          err instanceof Error ? err.message : "A network failure occurred during image upload."
        );
      }
    } finally {
      setIsSubmitting(false);
      abortControllerRef.current = null;
    }
  };

  const handleCancelScan = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsSubmitting(false);
    setStep("select");
  };

  // ---------------------------------------------------------------------------
  // 3. Candidate Review & Editing Actions
  // ---------------------------------------------------------------------------
  const handleEditCandidateName = (index: number, newName: string) => {
    setCandidates((prev) => {
      const next = [...prev];
      next[index] = {
        ...next[index],
        name: newName,
        isUserCorrected: true,
      };
      return next;
    });
  };

  const handleMoveCandidate = (index: number, direction: "up" | "down") => {
    setCandidates((prev) => {
      const targetIndex = direction === "up" ? index - 1 : index + 1;
      if (targetIndex < 0 || targetIndex >= prev.length) return prev;

      const next = [...prev];
      const itemToMove = next[index];
      next.splice(index, 1);
      next.splice(targetIndex, 0, itemToMove);

      // Re-normalize positions
      return next.map((item, idx) => ({
        ...item,
        position: idx + 1,
        isUserCorrected: true,
      }));
    });
  };

  const handleRemoveCandidate = (index: number) => {
    setCandidates((prev) => {
      const next = prev.filter((_, idx) => idx !== index);
      return next.map((item, idx) => ({
        ...item,
        position: idx + 1,
        isUserCorrected: true,
      }));
    });
  };

  const handleAddCustomCandidate = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = newIngredientName.trim();
    if (!trimmed) return;

    setCandidates((prev) => [
      ...prev,
      {
        name: trimmed,
        position: prev.length + 1,
        isConfirmed: true,
        isUserCorrected: true,
      },
    ]);
    setNewIngredientName("");
  };

  // ---------------------------------------------------------------------------
  // 4. Confirm Scan
  // ---------------------------------------------------------------------------
  const handleConfirmScan = async () => {
    if (!scanResult || isConfirming) return;

    const validCandidates = candidates.filter((c) => c.name.trim().length > 0);
    if (validCandidates.length === 0) {
      setErrorMessage("At least one candidate ingredient must be present to confirm.");
      return;
    }

    setIsConfirming(true);
    setErrorMessage(null);

    const payloadItems: ConfirmIngredientItem[] = validCandidates.map((c, idx) => ({
      candidate_id: c.id,
      position: idx + 1,
      name: c.name.trim(),
      is_confirmed: true,
    }));

    try {
      const confirmed = await ocrService.confirmScan(scanResult.id, payloadItems);
      setConfirmedResult(confirmed);
      setStep("confirmed");
      if (onSuccessConfirm) {
        onSuccessConfirm(confirmed);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.message || "Failed to confirm formulation review.");
      } else {
        setErrorMessage("Network issue while confirming formulation.");
      }
    } finally {
      setIsConfirming(false);
    }
  };

  // ---------------------------------------------------------------------------
  // 5. Add to My Shelf (Verified backend contract)
  // ---------------------------------------------------------------------------
  const handleSaveToShelf = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!scanResult || !confirmedResult || isSavingToShelf) return;

    setIsSavingToShelf(true);
    setErrorMessage(null);

    const fullIngredientText = confirmedResult.candidates
      .map((c) => c.normalized_name)
      .join(", ");

    try {
      const item = await ocrService.addScannedProductToShelf({
        ocr_job_id: scanResult.id,
        custom_name: shelfName.trim() || "Scanned Formulation",
        custom_brand: shelfBrand.trim() || "Custom Scan",
        custom_category: shelfCategory,
        custom_ingredient_text: fullIngredientText,
        status: shelfStatus,
      });

      setShelfSuccessMessage(
        `"${item.display_name || shelfName}" successfully saved to My Shelf!`
      );
      if (onAddedToShelf) {
        onAddedToShelf(item);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.message || "Failed to save scanned product to My Shelf.");
      } else {
        setErrorMessage("Could not connect to shelf service.");
      }
    } finally {
      setIsSavingToShelf(false);
    }
  };

  // ---------------------------------------------------------------------------
  // 6. Delete Asset Voluntary Action (Privacy & Retention)
  // ---------------------------------------------------------------------------
  const handleDeleteImage = async () => {
    if (!scanResult?.media_asset?.id || isDeletingAsset) return;

    setIsDeletingAsset(true);
    try {
      await ocrService.deleteOwnedAsset(scanResult.media_asset.id);
      setAssetDeleted(true);
    } catch (err: unknown) {
      // Non-blocking error for voluntary asset deletion
      setErrorMessage(
        err instanceof ApiError
          ? err.message
          : "Failed to purge image asset from private storage."
      );
    } finally {
      setIsDeletingAsset(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200"
      role="dialog"
      aria-modal="true"
      aria-labelledby="scan-modal-title"
    >
      <div
        ref={modalRef}
        className="w-full sm:max-w-lg bg-[#0E141B] border border-white/12 rounded-t-3xl sm:rounded-3xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh] text-left"
      >
        {/* Header Bar */}
        <div className="p-4 sm:p-5 border-b border-white/8 flex items-center justify-between shrink-0 bg-[#0C1217]/90">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
              <Camera className="w-4 h-4" />
            </div>
            <div>
              <h2
                id="scan-modal-title"
                className="text-sm font-bold text-white tracking-tight leading-tight"
              >
                Label Scanner{" "}
                <span className="font-serif italic font-normal text-champagne">
                  Verification
                </span>
              </h2>
              <p className="text-xxs text-slate-400">
                Segment & review formulation ingredients with OCR
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting || isConfirming}
            aria-label="Close scanner modal"
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/5 transition-colors disabled:opacity-30"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Scrollable Body */}
        <div className="p-4 sm:p-5 overflow-y-auto space-y-4 text-xs">
          {/* Global Error Banner (shown during non-error steps) */}
          {errorMessage && step !== "error" && (
            <div className="p-3 rounded-xl bg-rose-950/40 border border-rose-500/40 text-rose-200 flex items-start gap-2.5">
              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              <div className="text-xxs space-y-0.5 flex-1">
                <span className="font-semibold block text-rose-300">
                  {errorCategory === "rate_limited"
                    ? "Quota Exceeded"
                    : errorCategory === "unreadable_image"
                    ? "Unreadable Packaging"
                    : errorCategory === "upstream_unavailable"
                    ? "OCR Service Busy"
                    : "Scan Issue"}
                </span>
                <p className="text-rose-200/90 leading-normal">{errorMessage}</p>
              </div>
            </div>
          )}

          {/* ================================================================= */}
          {/* STEP 1: Select / Capture Label Image                              */}
          {/* ================================================================= */}
          {step === "select" && (
            <div className="space-y-4">
              {/* Privacy & OCR Explanation Banner */}
              <div className="p-3 rounded-xl bg-emerald-950/20 border border-emerald-500/20 text-emerald-300/90 space-y-1">
                <div className="flex items-center gap-1.5 font-semibold text-xxs text-emerald-400">
                  <ShieldAlert className="w-3.5 h-3.5 shrink-0" />
                  <span>Private Formulation Extraction</span>
                </div>
                <p className="text-xxs text-slate-300 leading-normal">
                  Your uploaded label photo is processed securely by the application's OCR
                  provider to segment packaging ingredients into candidate items. Raw image bytes
                  are never made public or indexed externally.
                </p>
              </div>

              {/* Hidden File & Camera Inputs */}
              <input
                ref={cameraInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                capture="environment"
                className="hidden"
                onChange={handleFileChange}
                aria-label="Snap packaging label with camera"
              />
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="hidden"
                onChange={handleFileChange}
                aria-label="Upload packaging label photo"
              />

              {/* Snap / Select Action Tiles (Visible when no file chosen) */}
              {!selectedFile && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {/* 1. Snap Label with Camera */}
                  <button
                    type="button"
                    onClick={() => cameraInputRef.current?.click()}
                    className="group relative p-4 rounded-2xl border border-emerald-500/30 bg-gradient-to-b from-emerald-950/30 to-emerald-900/10 hover:from-emerald-950/50 hover:to-emerald-900/20 hover:border-emerald-500/60 transition-all text-left flex flex-col justify-between space-y-3 cursor-pointer shadow-lg shadow-emerald-950/20 active:scale-[0.98]"
                  >
                    <div className="flex items-center justify-between w-full">
                      <div className="w-10 h-10 rounded-xl bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-400 group-hover:scale-105 transition-transform">
                        <Camera className="w-5 h-5" />
                      </div>
                      <Chip variant="verified" size="sm">Camera</Chip>
                    </div>
                    <div>
                      <span className="text-xs font-bold text-white block">
                        Snap Label Photo
                      </span>
                      <span className="text-xxs text-slate-400 block mt-0.5 leading-snug">
                        Use device camera to snap packaging ingredients
                      </span>
                    </div>
                  </button>

                  {/* 2. Upload / Drag & Drop Card */}
                  <div
                    onDragOver={handleDragOver}
                    onDrop={handleDrop}
                    onClick={() => fileInputRef.current?.click()}
                    className="group relative p-4 rounded-2xl border-2 border-dashed border-white/15 bg-white/[0.02] hover:border-white/30 hover:bg-white/[0.04] transition-all text-left flex flex-col justify-between space-y-3 cursor-pointer active:scale-[0.98]"
                  >
                    <div className="flex items-center justify-between w-full">
                      <div className="w-10 h-10 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center text-slate-300 group-hover:scale-105 transition-transform">
                        <UploadCloud className="w-5 h-5 text-slate-300" />
                      </div>
                      <span className="text-xxs font-mono text-slate-400">Max 5MB</span>
                    </div>
                    <div>
                      <span className="text-xs font-bold text-white block">
                        Upload Image
                      </span>
                      <span className="text-xxs text-slate-400 block mt-0.5 leading-snug">
                        Select screenshot, photo, or drag & drop
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {/* Validation Error Message */}
              {validationError && (
                <div className="p-2.5 rounded-lg bg-rose-950/30 border border-rose-500/30 text-rose-300 text-xxs flex items-center gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                  <span>{validationError}</span>
                </div>
              )}

              {/* Snapped/Selected Photo Preview Card */}
              {selectedFile && (
                <div className="p-3.5 rounded-2xl bg-[#090D11]/90 border border-white/10 space-y-3">
                  {/* Photo Preview Frame */}
                  <div className="relative rounded-xl overflow-hidden bg-black/80 border border-white/10 flex items-center justify-center min-h-[160px] max-h-56">
                    {previewUrl ? (
                      <img
                        src={previewUrl}
                        alt="Snapped packaging label preview"
                        className="w-full max-h-56 object-contain"
                      />
                    ) : (
                      <div className="py-10 text-center text-slate-500 text-xs">
                        Loading photo preview...
                      </div>
                    )}
                    <button
                      type="button"
                      onClick={() => setSelectedFile(null)}
                      aria-label="Remove snapped photo"
                      className="absolute top-2 right-2 p-1.5 rounded-full bg-slate-950/80 text-slate-300 hover:text-rose-400 border border-white/15 shadow-md transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                    <div className="absolute bottom-2 left-2">
                      <Chip variant="champagne" size="sm">
                        Ready to Process
                      </Chip>
                    </div>
                  </div>

                  <div className="flex items-center justify-between px-0.5">
                    <div className="space-y-0.5 truncate max-w-[190px]">
                      <span className="text-xxs text-slate-400 block">Snapped Photo</span>
                      <span className="text-xs font-semibold text-white block truncate">
                        {selectedFile.name}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Chip variant="neutral" size="sm">
                        {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB
                      </Chip>
                      <button
                        type="button"
                        onClick={() => cameraInputRef.current?.click()}
                        className="text-xxs text-emerald-400 hover:text-emerald-300 font-medium underline flex items-center gap-1"
                      >
                        <RefreshCw className="w-3 h-3" />
                        Retake
                      </button>
                    </div>
                  </div>

                  <p className="text-xxs text-slate-400 px-0.5">
                    Image remains locally on your device until you press "Process Label".
                  </p>

                  <Button
                    variant="primary"
                    size="md"
                    onClick={handleStartScan}
                    disabled={isSubmitting}
                    className="w-full flex items-center justify-center gap-2 font-semibold shadow-lg shadow-emerald-500/20"
                  >
                    <Camera className="w-4 h-4" />
                    <span>Process Label</span>
                  </Button>
                </div>
              )}

              {/* Retention Policy Notice */}
              <div className="text-[11px] text-slate-500 text-center leading-relaxed px-2">
                Storage Policy: Label images are retained privately for up to 30 days under policy{" "}
                <code className="text-slate-400 font-mono">ocr_retain_30d</code> to support formula
                verification, after which they are automatically expunged. You may also delete the
                file immediately upon confirmation.
              </div>
            </div>
          )}

          {/* ================================================================= */}
          {/* STEP 2: In-Flight Upload & OCR Extraction                         */}
          {/* ================================================================= */}
          {step === "scanning" && (
            <div className="py-8 space-y-5 text-center">
              <div className="relative inline-flex items-center justify-center">
                <div className="w-16 h-16 rounded-full bg-emerald-500/10 border border-emerald-500/30 animate-pulse flex items-center justify-center">
                  <RefreshCw className="w-8 h-8 text-emerald-400 animate-spin" />
                </div>
              </div>

              <div className="space-y-1">
                <h3 className="text-sm font-bold text-white">Extracting Formulation Data</h3>
                <p className="text-xxs text-slate-400 max-w-xs mx-auto">
                  Uploading image to secure storage and segmenting cosmetic ingredient candidates...
                </p>
              </div>

              <div className="space-y-2 max-w-xs mx-auto animate-pulse pt-2">
                <div className="h-3 bg-white/10 rounded w-full"></div>
                <div className="h-3 bg-white/5 rounded w-4/5 mx-auto"></div>
                <div className="h-3 bg-white/5 rounded w-3/5 mx-auto"></div>
              </div>

              <div className="pt-4">
                <Button variant="secondary" size="sm" onClick={handleCancelScan}>
                  Cancel Extraction
                </Button>
              </div>
            </div>
          )}

          {/* ================================================================= */}
          {/* STEP 3: Review & Edit Candidate Ingredients                       */}
          {/* ================================================================= */}
          {step === "review" && (
            <div className="space-y-4">
              {/* Epistemic Guardrail Notice */}
              <div className="p-3 rounded-xl bg-amber-950/20 border border-amber-500/20 text-amber-200/90 space-y-1">
                <div className="flex items-center gap-1.5 font-semibold text-xxs text-amber-400">
                  <ShieldAlert className="w-3.5 h-3.5 shrink-0" />
                  <span>Unconfirmed OCR Candidate Candidates</span>
                </div>
                <p className="text-xxs text-slate-300 leading-normal">
                  Extracted text is untrusted. Curved bottles, reflective plastic, and small print can
                  lead to misread characters. Please review, edit, or remove candidate items below
                  before confirming.
                </p>
              </div>

              {/* Confidence & Timing Meta */}
              {scanResult && (
                <div className="flex items-center justify-between text-xxs text-slate-400 px-1">
                  <span>
                    Provider: <span className="font-mono text-slate-300">{scanResult.provider}</span>
                  </span>
                  {scanResult.confidence_score !== null &&
                    scanResult.confidence_score !== undefined && (
                      <span>
                        Confidence:{" "}
                        <span className="font-semibold text-emerald-400">
                          {(scanResult.confidence_score * 100).toFixed(0)}%
                        </span>
                      </span>
                    )}
                  {scanResult.processing_time_ms && (
                    <span>{scanResult.processing_time_ms} ms</span>
                  )}
                </div>
              )}

              {/* Raw Text Accordion (Untrusted Plain Text Display) */}
              {scanResult?.raw_text && (
                <div className="border border-white/8 rounded-xl bg-[#0B0F13] overflow-hidden">
                  <button
                    type="button"
                    onClick={() => setShowRawText(!showRawText)}
                    className="w-full p-2.5 flex items-center justify-between text-xxs text-slate-400 hover:text-white transition-colors"
                  >
                    <span className="flex items-center gap-1.5 font-medium">
                      <FileText className="w-3.5 h-3.5" />
                      <span>View Untrusted Raw OCR Text</span>
                    </span>
                    {showRawText ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                  </button>

                  {showRawText && (
                    <div className="p-3 border-t border-white/8 bg-[#070A0D] text-slate-400 font-mono text-[11px] leading-relaxed whitespace-pre-wrap select-text max-h-36 overflow-y-auto">
                      {/* Rendered strictly as text, never HTML */}
                      {scanResult.raw_text}
                    </div>
                  )}
                </div>
              )}

              {/* Editable Candidates List */}
              <div className="space-y-2">
                <div className="flex items-center justify-between px-1">
                  <span className="text-xxs font-bold uppercase tracking-wider text-slate-400">
                    Candidate Ingredients ({candidates.length})
                  </span>
                  <span className="text-xxs text-slate-500">
                    Order reflects descending packaging position
                  </span>
                </div>

                <div className="space-y-1.5 max-h-60 overflow-y-auto pr-1">
                  {candidates.map((cand, idx) => (
                    <div
                      key={cand.id || `custom-${idx}`}
                      className="p-2 rounded-xl bg-[#11171E] border border-white/8 flex items-center gap-2 text-xxs group"
                    >
                      <span className="w-5 text-center font-mono text-slate-500 shrink-0 font-semibold">
                        {cand.position}
                      </span>

                      {/* Name Input */}
                      <input
                        type="text"
                        value={cand.name}
                        onChange={(e) => handleEditCandidateName(idx, e.target.value)}
                        aria-label={`Ingredient candidate ${cand.position}`}
                        className="flex-1 bg-transparent border-b border-white/10 focus:border-emerald-500 text-white font-medium text-xs py-0.5 focus:outline-none"
                      />

                      {/* Controls: Move Up, Move Down, Remove */}
                      <div className="flex items-center gap-1 shrink-0">
                        <button
                          type="button"
                          onClick={() => handleMoveCandidate(idx, "up")}
                          disabled={idx === 0}
                          aria-label={`Move ${cand.name} up`}
                          className="p-1 text-slate-500 hover:text-white disabled:opacity-20 transition-colors"
                        >
                          <ArrowUp className="w-3 h-3" />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleMoveCandidate(idx, "down")}
                          disabled={idx === candidates.length - 1}
                          aria-label={`Move ${cand.name} down`}
                          className="p-1 text-slate-500 hover:text-white disabled:opacity-20 transition-colors"
                        >
                          <ArrowDown className="w-3 h-3" />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleRemoveCandidate(idx)}
                          aria-label={`Remove ${cand.name}`}
                          className="p-1 text-slate-500 hover:text-rose-400 transition-colors"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Add Custom / Missing Ingredient Field */}
                <form onSubmit={handleAddCustomCandidate} className="flex gap-2 pt-1">
                  <input
                    type="text"
                    value={newIngredientName}
                    onChange={(e) => setNewIngredientName(e.target.value)}
                    placeholder="Add missing ingredient..."
                    className="flex-1 px-3 py-1.5 rounded-xl bg-[#090D11] border border-white/10 text-white text-xs placeholder-slate-500 focus:outline-none focus:border-emerald-500"
                  />
                  <Button type="submit" size="sm" variant="secondary" disabled={!newIngredientName.trim()}>
                    <Plus className="w-3.5 h-3.5 mr-1" />
                    <span>Add</span>
                  </Button>
                </form>
              </div>

              {/* Confirmation Action */}
              <div className="pt-2 border-t border-white/8 flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="md"
                  onClick={() => setStep("select")}
                  disabled={isConfirming}
                  className="w-1/3"
                >
                  Rescan
                </Button>
                <Button
                  variant="primary"
                  size="md"
                  onClick={handleConfirmScan}
                  disabled={isConfirming || candidates.length === 0}
                  className="flex-1 flex items-center justify-center gap-2 font-bold"
                >
                  {isConfirming ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Confirming...</span>
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="w-4 h-4" />
                      <span>Confirm Formulation</span>
                    </>
                  )}
                </Button>
              </div>
            </div>
          )}

          {/* ================================================================= */}
          {/* STEP 4: Confirmed Result & Shelf Integration                      */}
          {/* ================================================================= */}
          {step === "confirmed" && confirmedResult && (
            <div className="space-y-4">
              {/* Confirmed Banner */}
              <div className="p-4 rounded-2xl bg-emerald-950/30 border border-emerald-500/40 text-emerald-200 text-center space-y-1.5">
                <div className="w-10 h-10 rounded-full bg-emerald-500/20 text-emerald-400 mx-auto flex items-center justify-center border border-emerald-500/30">
                  <CheckCircle2 className="w-5 h-5" />
                </div>
                <h3 className="text-sm font-bold text-white">Formulation Verified & Saved</h3>
                <p className="text-xxs text-emerald-300/80">
                  {confirmedResult.confirmed_count} candidate ingredients verified and registered
                  under scan #{confirmedResult.scan_id.slice(0, 8)}.
                </p>
              </div>

              {/* Exact Confirmed Ingredients Display */}
              <div className="p-3 rounded-xl bg-[#0B0F13] border border-white/8 space-y-2">
                <span className="text-xxs font-bold uppercase tracking-wider text-slate-400 block">
                  Confirmed Ingredients
                </span>
                <div className="flex flex-wrap gap-1.5 max-h-36 overflow-y-auto">
                  {confirmedResult.candidates.map((cand) => (
                    <span
                      key={cand.id}
                      className="px-2 py-0.5 rounded-lg bg-white/5 border border-white/10 text-slate-200 text-xxs font-medium"
                    >
                      {cand.position}. {cand.normalized_name}
                    </span>
                  ))}
                </div>
              </div>

              {/* Add to My Shelf Form */}
              <div className="p-3.5 rounded-xl bg-[#11171E] border border-white/8 space-y-3">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-white">
                  <BookmarkPlus className="w-4 h-4 text-emerald-400" />
                  <span>Save Scanned Product to My Shelf</span>
                </div>

                {shelfSuccessMessage ? (
                  <div className="p-2.5 rounded-lg bg-emerald-950/30 border border-emerald-500/40 text-emerald-300 text-xxs">
                    {shelfSuccessMessage}
                  </div>
                ) : (
                  <form onSubmit={handleSaveToShelf} className="space-y-2.5">
                    <div className="grid grid-cols-2 gap-2">
                      <div className="space-y-1">
                        <label className="text-xxs text-slate-400 block font-medium">
                          Product Name
                        </label>
                        <input
                          type="text"
                          value={shelfName}
                          onChange={(e) => setShelfName(e.target.value)}
                          placeholder="e.g. Centella Soothing Gel"
                          required
                          className="w-full text-xs p-2 rounded-lg bg-[#0C1217] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-xxs text-slate-400 block font-medium">Brand</label>
                        <input
                          type="text"
                          value={shelfBrand}
                          onChange={(e) => setShelfBrand(e.target.value)}
                          placeholder="e.g. SkinScience"
                          required
                          className="w-full text-xs p-2 rounded-lg bg-[#0C1217] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-2">
                      <div className="space-y-1">
                        <label className="text-xxs text-slate-400 block font-medium">Category</label>
                        <select
                          value={shelfCategory}
                          onChange={(e) => setShelfCategory(e.target.value)}
                          className="w-full text-xs p-2 rounded-lg bg-[#0C1217] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                        >
                          <option value="Cleanser">Cleanser</option>
                          <option value="Moisturizer">Moisturizer</option>
                          <option value="Serum">Serum</option>
                          <option value="Sunscreen">Sunscreen</option>
                          <option value="Toner">Toner</option>
                          <option value="Treatment">Treatment</option>
                        </select>
                      </div>
                      <div className="space-y-1">
                        <label className="text-xxs text-slate-400 block font-medium">
                          Shelf Status
                        </label>
                        <select
                          value={shelfStatus}
                          onChange={(e) => setShelfStatus(e.target.value as "in_use" | "wishlist")}
                          className="w-full text-xs p-2 rounded-lg bg-[#0C1217] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                        >
                          <option value="in_use">In Use</option>
                          <option value="wishlist">Wishlist</option>
                        </select>
                      </div>
                    </div>

                    <Button
                      type="submit"
                      variant="primary"
                      size="sm"
                      disabled={isSavingToShelf}
                      className="w-full font-semibold"
                    >
                      {isSavingToShelf ? "Adding to Shelf..." : "Add to My Shelf"}
                    </Button>
                  </form>
                )}
              </div>

              {/* Private Image Asset Retention & Voluntary Deletion */}
              {scanResult?.media_asset && (
                <div className="p-3 rounded-xl bg-[#090D11] border border-white/5 space-y-2 text-xxs">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">Image Retention Policy:</span>
                    <span className="font-mono text-slate-300">
                      {scanResult.media_asset.retention_policy}
                    </span>
                  </div>

                  {assetDeleted ? (
                    <div className="p-2 rounded-lg bg-white/5 text-slate-400 text-center">
                      Image bytes successfully deleted from backend storage.
                    </div>
                  ) : (
                    <div className="flex items-center justify-between pt-1">
                      <span className="text-slate-500 text-[10px]">
                        Expires in 30 days or delete immediately.
                      </span>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={handleDeleteImage}
                        disabled={isDeletingAsset}
                        className="text-xxs text-rose-400 hover:text-rose-300 hover:bg-rose-950/20 px-2 py-1 h-auto"
                      >
                        {isDeletingAsset ? "Deleting..." : "Delete Image Asset Now"}
                      </Button>
                    </div>
                  )}
                </div>
              )}

              {/* Done Button */}
              <div className="pt-2">
                <Button variant="secondary" size="md" onClick={onClose} className="w-full">
                  Done
                </Button>
              </div>
            </div>
          )}

          {/* ================================================================= */}
          {/* STEP 5: Error / Recovery View                                     */}
          {/* ================================================================= */}
          {step === "error" && (
            <div className="py-4 space-y-4 text-center">
              <div className="w-12 h-12 rounded-full bg-rose-950/40 border border-rose-500/40 text-rose-400 mx-auto flex items-center justify-center">
                <AlertTriangle className="w-6 h-6" />
              </div>

              <div className="space-y-1">
                <h3 className="text-sm font-bold text-white">
                  {errorCategory === "rate_limited"
                    ? "Quota Exceeded"
                    : errorCategory === "unreadable_image"
                    ? "Unreadable Packaging"
                    : errorCategory === "upstream_unavailable"
                    ? "OCR Service Busy"
                    : "Extraction Unsuccessful"}
                </h3>
                <p className="text-xxs text-slate-400 max-w-xs mx-auto leading-normal">
                  {errorMessage ||
                    "We encountered a difficulty segmenting formulation ingredients from this image."}
                </p>
              </div>

              <div className="pt-2 flex items-center justify-center gap-2">
                <Button variant="secondary" size="sm" onClick={() => setStep("select")}>
                  Select Different Image
                </Button>
                {selectedFile && (
                  <Button variant="primary" size="sm" onClick={handleStartScan} disabled={isSubmitting}>
                    Retry Scan
                  </Button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
