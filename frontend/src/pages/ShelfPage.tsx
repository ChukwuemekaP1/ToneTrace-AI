import React, { useState, useEffect, useCallback } from "react";
import {
  BookmarkCheck,
  Plus,
  Camera,
  Search,
  AlertTriangle,
  Calendar,
  Clock,
  Trash2,
  Edit3,
  X,
  ExternalLink,
  ShieldAlert,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { GlassCard } from "@/components/ui/GlassCard";
import { Chip } from "@/components/ui/Chip";
import { ScanLabelModal } from "@/components/ocr/ScanLabelModal";
import { ProductReactionModal } from "@/components/reactions/ProductReactionModal";
import {
  shelfService,
  SUPPORTED_SHELF_STATUSES,
  isValidUuid,
} from "@/api/shelf";
import { catalogService } from "@/api/catalog";
import {
  ShelfItemResponse,
  ShelfStatus,
  ShelfItemCreateRequest,
  ShelfItemUpdateRequest,
  DiscoveryProductSummaryItem,
  ApiError,
} from "@/api/types";

export interface ShelfPageProps {
  onNavigate: (route: string) => void;
  initialItemId?: string | null;
}

export function formatExpirationCountdown(expiresAt: string | null | undefined): {
  label: string;
  isExpired: boolean;
  isNearExpiry: boolean;
} | null {
  if (!expiresAt) return null;
  const expDate = new Date(expiresAt);
  if (isNaN(expDate.getTime())) return null;

  const now = new Date();
  const diffMs = expDate.getTime() - now.getTime();
  const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));

  const formattedDate = expDate.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  if (diffDays < 0) {
    return {
      label: `Expired on ${formattedDate} (${Math.abs(diffDays)}d ago)`,
      isExpired: true,
      isNearExpiry: false,
    };
  }

  if (diffDays <= 30) {
    return {
      label: `Expires in ${diffDays} day${diffDays === 1 ? "" : "s"} (${formattedDate})`,
      isExpired: false,
      isNearExpiry: true,
    };
  }

  return {
    label: `Expires ${formattedDate} (in ${diffDays}d)`,
    isExpired: false,
    isNearExpiry: false,
  };
}

export const ShelfPage: React.FC<ShelfPageProps> = ({ onNavigate, initialItemId }) => {
  // Shelf list state
  const [items, setItems] = useState<ShelfItemResponse[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filters & Sorting state
  const [activeStatus, setActiveStatus] = useState<ShelfStatus | "all">("all");
  const [sortBy, setSortBy] = useState<"created_at_desc" | "name_asc" | "opened_at_desc">(
    "created_at_desc"
  );
  const [page, setPage] = useState<number>(1);

  // Modals state
  const [isScanModalOpen, setIsScanModalOpen] = useState<boolean>(false);
  const [isAddModalOpen, setIsAddModalOpen] = useState<boolean>(false);
  const [selectedDetailItem, setSelectedDetailItem] = useState<ShelfItemResponse | null>(null);
  const [isEditModalOpen, setIsEditModalOpen] = useState<boolean>(false);
  const [deleteConfirmItem, setDeleteConfirmItem] = useState<ShelfItemResponse | null>(null);
  const [isReactionModalOpen, setIsReactionModalOpen] = useState<boolean>(false);

  // Add Product Modal Tabs ("catalog" vs "custom")
  const [addMode, setAddMode] = useState<"catalog" | "custom">("catalog");
  const [catalogSearchQuery, setCatalogSearchQuery] = useState<string>("");
  const [catalogSearchResults, setCatalogSearchResults] = useState<DiscoveryProductSummaryItem[]>([]);
  const [catalogSearchLoading, setCatalogSearchLoading] = useState<boolean>(false);

  // Custom Product Form state
  const [customName, setCustomName] = useState<string>("");
  const [customBrand, setCustomBrand] = useState<string>("");
  const [customCategory, setCustomCategory] = useState<string>("Moisturizer");
  const [customStatus, setCustomStatus] = useState<ShelfStatus>("in_use");
  const [customOpenedAt, setCustomOpenedAt] = useState<string>("");
  const [customExpiresAt, setCustomExpiresAt] = useState<string>("");
  const [customIngredients, setCustomIngredients] = useState<string>("");
  const [customNotes, setCustomNotes] = useState<string>("");
  const [isAddingProduct, setIsAddingProduct] = useState<boolean>(false);
  const [addFormError, setAddFormError] = useState<string | null>(null);

  // Edit Product Form state
  const [editStatus, setEditStatus] = useState<ShelfStatus>("in_use");
  const [editOpenedAt, setEditOpenedAt] = useState<string>("");
  const [editExpiresAt, setEditExpiresAt] = useState<string>("");
  const [editNotes, setEditNotes] = useState<string>("");
  const [editCustomName, setEditCustomName] = useState<string>("");
  const [editCustomBrand, setEditCustomBrand] = useState<string>("");
  const [isUpdatingItem, setIsUpdatingItem] = useState<boolean>(false);
  const [editFormError, setEditFormError] = useState<string | null>(null);

  // Delete state
  const [isDeleting, setIsDeleting] = useState<boolean>(false);

  // Fetch shelf items
  const fetchShelf = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await shelfService.listShelfItems({
        status: activeStatus === "all" ? undefined : activeStatus,
        sort_by: sortBy,
        page,
        page_size: 20,
      });
      setItems(res.items || []);
      setTotalCount(res.total || 0);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.message || "Failed to load shelf items.");
      } else {
        setError("Network error loading your skincare shelf.");
      }
    } finally {
      setLoading(false);
    }
  }, [activeStatus, sortBy, page]);

  useEffect(() => {
    fetchShelf();
  }, [fetchShelf]);

  // Handle deep-linked item if valid UUID is passed
  useEffect(() => {
    if (initialItemId && isValidUuid(initialItemId)) {
      shelfService
        .getShelfItem(initialItemId)
        .then((item) => {
          setSelectedDetailItem(item);
        })
        .catch(() => {
          // Non-blocking if item not found / owned by someone else
        });
    }
  }, [initialItemId]);

  // Catalog search debouncing for Add Product Modal
  useEffect(() => {
    if (addMode !== "catalog" || !catalogSearchQuery.trim()) {
      setCatalogSearchResults([]);
      return;
    }

    const timer = setTimeout(async () => {
      setCatalogSearchLoading(true);
      try {
        const res = await catalogService.discoverProducts({
          q: catalogSearchQuery.trim(),
          page: 1,
          page_size: 6,
        });
        setCatalogSearchResults(res.items || []);
      } catch {
        setCatalogSearchResults([]);
      } finally {
        setCatalogSearchLoading(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [catalogSearchQuery, addMode]);

  // Add Catalogue-linked item
  const handleAddCatalogProduct = async (product: DiscoveryProductSummaryItem) => {
    setIsAddingProduct(true);
    setAddFormError(null);
    try {
      await shelfService.addShelfItem({
        product_id: product.product_id,
        status: "in_use",
      });
      setIsAddModalOpen(false);
      setCatalogSearchQuery("");
      fetchShelf();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setAddFormError(`"${product.name}" is already on your shelf.`);
        } else {
          setAddFormError(err.message || "Failed to add catalogue product.");
        }
      } else {
        setAddFormError("Network error adding product to shelf.");
      }
    } finally {
      setIsAddingProduct(false);
    }
  };

  // Add Custom Product
  const handleAddCustomProduct = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customName.trim() || !customBrand.trim()) {
      setAddFormError("Product name and brand are required.");
      return;
    }

    setIsAddingProduct(true);
    setAddFormError(null);

    const payload: ShelfItemCreateRequest = {
      custom_name: customName.trim(),
      custom_brand: customBrand.trim(),
      custom_category: customCategory,
      status: customStatus,
      opened_at: customOpenedAt ? new Date(customOpenedAt).toISOString() : null,
      expires_at: customExpiresAt ? new Date(customExpiresAt).toISOString() : null,
      custom_ingredient_text: customIngredients.trim() || null,
      private_notes: customNotes.trim() || null,
    };

    try {
      await shelfService.addShelfItem(payload);
      setIsAddModalOpen(false);
      setCustomName("");
      setCustomBrand("");
      setCustomIngredients("");
      setCustomNotes("");
      setCustomOpenedAt("");
      setCustomExpiresAt("");
      fetchShelf();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setAddFormError(`Custom product "${customBrand} - ${customName}" is already on your shelf.`);
        } else {
          setAddFormError(err.message || "Failed to add custom product.");
        }
      } else {
        setAddFormError("Network issue adding custom product.");
      }
    } finally {
      setIsAddingProduct(false);
    }
  };

  // Open Edit Modal with prepopulated values
  const handleOpenEdit = (item: ShelfItemResponse) => {
    setSelectedDetailItem(item);
    setEditStatus((item.status as ShelfStatus) || "in_use");
    setEditOpenedAt(item.opened_at ? item.opened_at.split("T")[0] : "");
    setEditExpiresAt(item.expires_at ? item.expires_at.split("T")[0] : "");
    setEditNotes(item.private_notes || "");
    setEditCustomName(item.display_name);
    setEditCustomBrand(item.display_brand);
    setEditFormError(null);
    setIsEditModalOpen(true);
  };

  // Save Item Updates
  const handleSaveEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedDetailItem) return;

    setIsUpdatingItem(true);
    setEditFormError(null);

    const payload: ShelfItemUpdateRequest = {
      status: editStatus,
      opened_at: editOpenedAt ? new Date(editOpenedAt).toISOString() : null,
      expires_at: editExpiresAt ? new Date(editExpiresAt).toISOString() : null,
      private_notes: editNotes.trim() || null,
    };

    if (selectedDetailItem.is_custom) {
      if (editCustomName.trim()) payload.custom_name = editCustomName.trim();
      if (editCustomBrand.trim()) payload.custom_brand = editCustomBrand.trim();
    }

    try {
      const updated = await shelfService.updateShelfItem(selectedDetailItem.id, payload);
      // Update cache & list strictly after server confirmation
      setItems((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setSelectedDetailItem(updated);
      setIsEditModalOpen(false);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setEditFormError(err.message || "Failed to update shelf item.");
      } else {
        setEditFormError("Network error while updating product.");
      }
    } finally {
      setIsUpdatingItem(false);
    }
  };

  // Delete Item
  const handleConfirmDelete = async () => {
    if (!deleteConfirmItem) return;

    setIsDeleting(true);
    try {
      await shelfService.deleteShelfItem(deleteConfirmItem.id);
      // Strictly remove from UI after server confirms
      setItems((prev) => prev.filter((item) => item.id !== deleteConfirmItem.id));
      setTotalCount((prev) => Math.max(0, prev - 1));
      if (selectedDetailItem?.id === deleteConfirmItem.id) {
        setSelectedDetailItem(null);
      }
      setDeleteConfirmItem(null);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.message || "Failed to delete item from shelf.");
      } else {
        setError("Network error while deleting shelf item.");
      }
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="space-y-4 text-left pb-16">
      {/* ------------------------------------------------------------------- */}
      {/* 1. Header Bar & Primary Actions                                     */}
      {/* ------------------------------------------------------------------- */}
      <div className="space-y-2 pt-1">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-white leading-tight">
              My{" "}
              <span className="font-serif italic font-normal text-champagne">Shelf</span>
            </h1>
            <p className="text-xs text-slate-400">
              Personal skincare inventory, formula tracking & safety checks.
            </p>
          </div>

          <div className="flex items-center gap-1.5">
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setIsScanModalOpen(true)}
              aria-label="Scan packaging label"
              className="flex items-center gap-1 px-2.5"
            >
              <Camera className="w-3.5 h-3.5 text-emerald-400" />
              <span>Scan</span>
            </Button>

            <Button
              size="sm"
              variant="primary"
              onClick={() => {
                setAddFormError(null);
                setIsAddModalOpen(true);
              }}
              aria-label="Add product to shelf"
              className="flex items-center gap-1 px-2.5 font-bold"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Add</span>
            </Button>
          </div>
        </div>

        {/* Status Enum Tabs (Verified Backend Literal) */}
        <div className="flex items-center gap-1 overflow-x-auto pb-1 no-scrollbar pt-1">
          <button
            type="button"
            onClick={() => {
              setActiveStatus("all");
              setPage(1);
            }}
            className={`px-3 py-1.5 text-xxs font-medium rounded-xl whitespace-nowrap transition-all shrink-0 ${
              activeStatus === "all"
                ? "bg-emerald-500 text-slate-950 font-bold shadow-glow"
                : "bg-white/[0.04] border border-white/8 text-slate-300 hover:border-white/20"
            }`}
          >
            All Products
          </button>

          {SUPPORTED_SHELF_STATUSES.map((st) => (
            <button
              key={st.value}
              type="button"
              onClick={() => {
                setActiveStatus(st.value);
                setPage(1);
              }}
              className={`px-3 py-1.5 text-xxs font-medium rounded-xl whitespace-nowrap transition-all shrink-0 ${
                activeStatus === st.value
                  ? "bg-emerald-500 text-slate-950 font-bold shadow-glow"
                  : "bg-white/[0.04] border border-white/8 text-slate-300 hover:border-white/20"
              }`}
            >
              {st.label}
            </button>
          ))}
        </div>

        {/* Sort Selector & Meta Count */}
        <div className="flex items-center justify-between text-xxs text-slate-400 px-1 pt-0.5">
          <span>
            {loading ? "Updating..." : `${totalCount} item${totalCount === 1 ? "" : "s"}`}
          </span>

          <div className="flex items-center gap-1.5">
            <span className="text-slate-500">Sort:</span>
            <select
              value={sortBy}
              onChange={(e) => {
                setSortBy(e.target.value as any);
                setPage(1);
              }}
              className="text-xxs bg-transparent text-slate-300 border-none focus:outline-none cursor-pointer"
            >
              <option value="created_at_desc" className="bg-[#0C1217]">
                Recently Added
              </option>
              <option value="name_asc" className="bg-[#0C1217]">
                Name A-Z
              </option>
              <option value="opened_at_desc" className="bg-[#0C1217]">
                Opened Date
              </option>
            </select>
          </div>
        </div>
      </div>

      {/* ------------------------------------------------------------------- */}
      {/* 2. Product Cards Feed & Statuses                                    */}
      {/* ------------------------------------------------------------------- */}
      {error ? (
        <div className="p-4 rounded-2xl bg-rose-950/40 border border-rose-500/40 text-rose-200 space-y-2 text-center">
          <div className="flex items-center justify-center gap-1.5 font-semibold text-xs text-rose-300">
            <AlertTriangle className="w-4 h-4" />
            <span>Shelf Error</span>
          </div>
          <p className="text-xxs text-rose-300/80 leading-normal">{error}</p>
          <div className="pt-1">
            <Button size="sm" variant="secondary" onClick={fetchShelf}>
              Retry Loading Shelf
            </Button>
          </div>
        </div>
      ) : loading ? (
        /* Loading Skeletons */
        <div className="space-y-2.5">
          {[1, 2, 3, 4].map((n) => (
            <GlassCard key={n} variant="default" className="p-3.5 space-y-2 animate-pulse">
              <div className="flex justify-between items-start">
                <div className="space-y-1.5 flex-1">
                  <div className="h-3 bg-white/10 rounded w-1/4"></div>
                  <div className="h-4 bg-white/10 rounded w-3/4"></div>
                </div>
                <div className="h-5 w-16 bg-white/5 rounded-full"></div>
              </div>
            </GlassCard>
          ))}
        </div>
      ) : items.length === 0 ? (
        /* Empty State with Action Buttons */
        <div className="p-6 rounded-3xl bg-[#11171E]/80 border border-white/8 text-center space-y-3.5">
          <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 mx-auto flex items-center justify-center">
            <BookmarkCheck className="w-6 h-6" />
          </div>

          <div className="space-y-1">
            <h3 className="text-sm font-bold text-white">
              {activeStatus === "all"
                ? "Your skincare shelf is empty"
                : `No products marked as "${activeStatus.replace(/_/g, " ")}"`}
            </h3>
            <p className="text-xxs text-slate-400 max-w-xs mx-auto leading-normal">
              Track your daily regimen, monitor period-after-opening expiry, and cross-check
              formulations against your personal sensitivities.
            </p>
          </div>

          <div className="pt-2 flex flex-col sm:flex-row items-center justify-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              onClick={() => onNavigate("/explore")}
              className="w-full sm:w-auto"
            >
              Browse Catalog
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setIsScanModalOpen(true)}
              className="w-full sm:w-auto flex items-center justify-center gap-1.5"
            >
              <Camera className="w-3.5 h-3.5 text-emerald-400" />
              <span>Scan a Label</span>
            </Button>
            <Button
              size="sm"
              variant="primary"
              onClick={() => {
                setAddMode("custom");
                setIsAddModalOpen(true);
              }}
              className="w-full sm:w-auto"
            >
              Add Custom Product
            </Button>
          </div>
        </div>
      ) : (
        /* Populated Shelf Feed */
        <div className="space-y-2.5">
          {items.map((item) => {
            const expCountdown = formatExpirationCountdown(item.expires_at);

            return (
              <div
                key={item.id}
                onClick={() => setSelectedDetailItem(item)}
                className="p-3.5 rounded-2xl bg-[#11171E]/90 border border-white/8 hover:border-white/20 transition-all shadow-glass cursor-pointer group text-left space-y-2"
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    setSelectedDetailItem(item);
                  }
                }}
                aria-label={`View ${item.display_name} by ${item.display_brand}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1 space-y-0.5">
                    <span className="text-xxs font-semibold text-emerald-400 block truncate">
                      {item.display_brand}
                    </span>
                    <h3 className="text-xs font-bold text-white truncate leading-tight group-hover:text-champagne transition-colors">
                      {item.display_name}
                    </h3>
                  </div>

                  {/* Status Badge */}
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider bg-white/5 border border-white/10 text-slate-300 shrink-0">
                    {item.status.replace(/_/g, " ")}
                  </span>
                </div>

                {/* Metadata Row: Category, Catalogue/Custom Badge */}
                <div className="flex items-center gap-1.5 flex-wrap text-xxs">
                  <Chip variant="neutral" size="sm">
                    {item.display_category}
                  </Chip>

                  <Chip variant={item.is_custom ? "neutral" : "verified"} size="sm">
                    {item.is_custom ? "Custom Entry" : "Catalogue Linked"}
                  </Chip>

                  {/* Sensitivity Warning Pill */}
                  {item.sensitivity_alerts && item.sensitivity_alerts.length > 0 && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg bg-rose-950/40 border border-rose-500/40 text-rose-300 text-xxs font-semibold">
                      <ShieldAlert className="w-3 h-3 text-rose-400" />
                      <span>{item.sensitivity_alerts.join(", ")} Alert</span>
                    </span>
                  )}
                </div>

                {/* Dates & Countdown (Strictly from stored fields; never guessed) */}
                <div className="flex items-center gap-3 pt-1 border-t border-white/5 text-[11px] text-slate-400">
                  {item.opened_at && (
                    <div className="flex items-center gap-1">
                      <Clock className="w-3 h-3 text-slate-500" />
                      <span>Opened: {new Date(item.opened_at).toLocaleDateString()}</span>
                    </div>
                  )}

                  {expCountdown && (
                    <div
                      className={`flex items-center gap-1 font-medium ${
                        expCountdown.isExpired
                          ? "text-rose-400 font-semibold"
                          : expCountdown.isNearExpiry
                          ? "text-amber-400 font-semibold"
                          : "text-slate-400"
                      }`}
                    >
                      <Calendar className="w-3 h-3" />
                      <span>{expCountdown.label}</span>
                    </div>
                  )}

                  {!item.opened_at && !item.expires_at && (
                    <span className="text-slate-500 text-[10px]">No dates recorded</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* 3. Shelf Item Detail Modal                                          */}
      {/* ------------------------------------------------------------------- */}
      {selectedDetailItem && !isEditModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200"
          role="dialog"
          aria-modal="true"
          aria-labelledby="detail-modal-title"
        >
          <div className="w-full sm:max-w-lg bg-[#0E141B] border border-white/12 rounded-t-3xl sm:rounded-3xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh] text-left">
            {/* Header */}
            <div className="p-4 sm:p-5 border-b border-white/8 flex items-center justify-between shrink-0 bg-[#0C1217]/90">
              <div className="space-y-0.5 min-w-0 pr-2">
                <span className="text-xxs font-semibold text-emerald-400 block truncate">
                  {selectedDetailItem.display_brand}
                </span>
                <h2
                  id="detail-modal-title"
                  className="text-sm font-bold text-white tracking-tight leading-tight truncate"
                >
                  {selectedDetailItem.display_name}
                </h2>
              </div>

              <div className="flex items-center gap-1.5 shrink-0">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => handleOpenEdit(selectedDetailItem)}
                  className="px-2.5 flex items-center gap-1"
                >
                  <Edit3 className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Edit</span>
                </Button>

                <button
                  type="button"
                  onClick={() => setSelectedDetailItem(null)}
                  aria-label="Close product detail"
                  className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/5 transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Body */}
            <div className="p-4 sm:p-5 overflow-y-auto space-y-4 text-xs">
              {/* Sensitivity Alerts */}
              {selectedDetailItem.sensitivity_alerts &&
                selectedDetailItem.sensitivity_alerts.length > 0 && (
                  <div className="p-3 rounded-xl bg-rose-950/40 border border-rose-500/40 text-rose-200 space-y-1">
                    <div className="flex items-center gap-1.5 font-semibold text-xxs text-rose-300">
                      <ShieldAlert className="w-3.5 h-3.5 shrink-0" />
                      <span>Formulation Sensitivity Notice</span>
                    </div>
                    <p className="text-xxs text-rose-200/90 leading-normal">
                      Contains {selectedDetailItem.sensitivity_alerts.join(", ")}, which matches your
                      reported sensitivity profile. This alert is informational and not clinical advice.
                    </p>
                  </div>
                )}

              {/* Status & Timing Grid */}
              <div className="grid grid-cols-2 gap-2 text-xxs">
                <div className="p-2.5 rounded-xl bg-[#11171E] border border-white/8 space-y-0.5">
                  <span className="text-slate-400 block">Status</span>
                  <span className="font-bold text-white capitalize">
                    {selectedDetailItem.status.replace(/_/g, " ")}
                  </span>
                </div>

                <div className="p-2.5 rounded-xl bg-[#11171E] border border-white/8 space-y-0.5">
                  <span className="text-slate-400 block">Category</span>
                  <span className="font-bold text-white capitalize">
                    {selectedDetailItem.display_category}
                  </span>
                </div>

                <div className="p-2.5 rounded-xl bg-[#11171E] border border-white/8 space-y-0.5">
                  <span className="text-slate-400 block">Opened Date</span>
                  <span className="font-bold text-white">
                    {selectedDetailItem.opened_at
                      ? new Date(selectedDetailItem.opened_at).toLocaleDateString()
                      : "Not set"}
                  </span>
                </div>

                <div className="p-2.5 rounded-xl bg-[#11171E] border border-white/8 space-y-0.5">
                  <span className="text-slate-400 block">Expiration / Target</span>
                  <span className="font-bold text-white">
                    {selectedDetailItem.expires_at
                      ? new Date(selectedDetailItem.expires_at).toLocaleDateString()
                      : "Not recorded"}
                  </span>
                </div>
              </div>

              {/* Private Notes */}
              {selectedDetailItem.private_notes && (
                <div className="p-3 rounded-xl bg-[#0B0F13] border border-white/8 space-y-1 text-xxs">
                  <span className="text-slate-400 font-semibold block">Private Notes</span>
                  <p className="text-slate-300 whitespace-pre-wrap select-text leading-relaxed">
                    {selectedDetailItem.private_notes}
                  </p>
                </div>
              )}

              {/* Ingredient Breakdown */}
              {selectedDetailItem.ingredient_names &&
                selectedDetailItem.ingredient_names.length > 0 && (
                  <div className="p-3 rounded-xl bg-[#0B0F13] border border-white/8 space-y-2 text-xxs">
                    <span className="text-slate-400 font-semibold block">
                      Ingredients ({selectedDetailItem.ingredient_names.length})
                    </span>
                    <div className="flex flex-wrap gap-1.5 max-h-36 overflow-y-auto">
                      {selectedDetailItem.ingredient_names.map((name, idx) => {
                        const isAlert = selectedDetailItem.sensitivity_alerts?.includes(name);
                        return (
                          <span
                            key={idx}
                            className={`px-2 py-0.5 rounded-lg border text-xxs font-medium ${
                              isAlert
                                ? "bg-rose-950/60 border-rose-500/50 text-rose-300"
                                : "bg-white/5 border-white/10 text-slate-300"
                            }`}
                          >
                            {name}
                          </span>
                        );
                      })}
                    </div>
                  </div>
                )}

              {/* Action Buttons: Delete, Log Reaction, View Evidence */}
              <div className="pt-2 border-t border-white/8 flex items-center justify-between gap-2 flex-wrap">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setDeleteConfirmItem(selectedDetailItem)}
                  className="text-rose-400 hover:text-rose-300 hover:bg-rose-950/30 flex items-center gap-1.5"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>Remove from Shelf</span>
                </Button>

                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => setIsReactionModalOpen(true)}
                    className="flex items-center gap-1.5 text-amber-300 hover:text-amber-200 border-amber-500/30"
                  >
                    <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                    <span>Log Reaction</span>
                  </Button>

                  {selectedDetailItem.product_id && (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => onNavigate(`/products/${selectedDetailItem.product_id}`)}
                      className="flex items-center gap-1.5"
                    >
                      <span>View Evidence</span>
                      <ExternalLink className="w-3 h-3 text-slate-400" />
                    </Button>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* 4. Edit Item Modal                                                  */}
      {/* ------------------------------------------------------------------- */}
      {isEditModalOpen && selectedDetailItem && (
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200"
          role="dialog"
          aria-modal="true"
          aria-labelledby="edit-modal-title"
        >
          <div className="w-full sm:max-w-lg bg-[#0E141B] border border-white/12 rounded-t-3xl sm:rounded-3xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh] text-left">
            <div className="p-4 sm:p-5 border-b border-white/8 flex items-center justify-between shrink-0 bg-[#0C1217]/90">
              <h2 id="edit-modal-title" className="text-sm font-bold text-white tracking-tight">
                Edit Shelf Item
              </h2>
              <button
                type="button"
                onClick={() => setIsEditModalOpen(false)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/5"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSaveEdit} className="p-4 sm:p-5 overflow-y-auto space-y-3.5 text-xs">
              {editFormError && (
                <div className="p-2.5 rounded-xl bg-rose-950/40 border border-rose-500/40 text-rose-300 text-xxs">
                  {editFormError}
                </div>
              )}

              {/* Status Enum Selector */}
              <div className="space-y-1">
                <label htmlFor="edit-status" className="text-xxs font-semibold text-slate-300 block">
                  Shelf Status
                </label>
                <select
                  id="edit-status"
                  value={editStatus}
                  onChange={(e) => setEditStatus(e.target.value as ShelfStatus)}
                  className="w-full text-xs p-2.5 rounded-xl bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                >
                  {SUPPORTED_SHELF_STATUSES.map((st) => (
                    <option key={st.value} value={st.value}>
                      {st.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Opened and Expiry Dates */}
              <div className="grid grid-cols-2 gap-2.5">
                <div className="space-y-1">
                  <label htmlFor="edit-opened-at" className="text-xxs font-semibold text-slate-300 block">
                    Opened Date
                  </label>
                  <input
                    id="edit-opened-at"
                    type="date"
                    value={editOpenedAt}
                    onChange={(e) => setEditOpenedAt(e.target.value)}
                    className="w-full text-xs p-2 rounded-xl bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                  />
                </div>

                <div className="space-y-1">
                  <label htmlFor="edit-expires-at" className="text-xxs font-semibold text-slate-300 block">
                    Expiration Date
                  </label>
                  <input
                    id="edit-expires-at"
                    type="date"
                    value={editExpiresAt}
                    onChange={(e) => setEditExpiresAt(e.target.value)}
                    className="w-full text-xs p-2 rounded-xl bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                  />
                </div>
              </div>

              {/* Custom Product Fields (if custom entry) */}
              {selectedDetailItem.is_custom && (
                <div className="grid grid-cols-2 gap-2.5 pt-1">
                  <div className="space-y-1">
                    <label className="text-xxs font-semibold text-slate-300 block">Product Name</label>
                    <input
                      type="text"
                      value={editCustomName}
                      onChange={(e) => setEditCustomName(e.target.value)}
                      className="w-full text-xs p-2 rounded-xl bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xxs font-semibold text-slate-300 block">Brand</label>
                    <input
                      type="text"
                      value={editCustomBrand}
                      onChange={(e) => setEditCustomBrand(e.target.value)}
                      className="w-full text-xs p-2 rounded-xl bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                    />
                  </div>
                </div>
              )}

              {/* Private Notes */}
              <div className="space-y-1">
                <label className="text-xxs font-semibold text-slate-300 block">
                  Private Notes (Strictly Confidential)
                </label>
                <textarea
                  value={editNotes}
                  onChange={(e) => setEditNotes(e.target.value)}
                  rows={3}
                  placeholder="Record personal observations, application frequency, or layering notes..."
                  className="w-full text-xs p-2.5 rounded-xl bg-[#090D11] border border-white/10 text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 resize-none"
                />
              </div>

              <div className="pt-2 border-t border-white/8 flex items-center justify-end gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => setIsEditModalOpen(false)}
                  disabled={isUpdatingItem}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  disabled={isUpdatingItem}
                  className="font-bold"
                >
                  {isUpdatingItem ? "Saving..." : "Save Changes"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* 5. Add Product Modal (Catalog Search & Custom Entry Tabs)          */}
      {/* ------------------------------------------------------------------- */}
      {isAddModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200"
          role="dialog"
          aria-modal="true"
          aria-labelledby="add-modal-title"
        >
          <div className="w-full sm:max-w-lg bg-[#0E141B] border border-white/12 rounded-t-3xl sm:rounded-3xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh] text-left">
            <div className="p-4 sm:p-5 border-b border-white/8 flex items-center justify-between shrink-0 bg-[#0C1217]/90">
              <h2 id="add-modal-title" className="text-sm font-bold text-white tracking-tight">
                Add Product to Shelf
              </h2>
              <button
                type="button"
                onClick={() => setIsAddModalOpen(false)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/5"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-4 sm:p-5 overflow-y-auto space-y-4 text-xs">
              {/* Tab Selector */}
              <div className="flex rounded-xl bg-[#090D11] p-1 border border-white/8">
                <button
                  type="button"
                  onClick={() => {
                    setAddMode("catalog");
                    setAddFormError(null);
                  }}
                  className={`flex-1 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                    addMode === "catalog"
                      ? "bg-emerald-500 text-slate-950 shadow-sm"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  Search Catalog
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setAddMode("custom");
                    setAddFormError(null);
                  }}
                  className={`flex-1 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                    addMode === "custom"
                      ? "bg-emerald-500 text-slate-950 shadow-sm"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  Custom Product
                </button>
              </div>

              {addFormError && (
                <div className="p-2.5 rounded-xl bg-rose-950/40 border border-rose-500/40 text-rose-300 text-xxs">
                  {addFormError}
                </div>
              )}

              {/* Mode 1: Search Catalog */}
              {addMode === "catalog" && (
                <div className="space-y-3">
                  <div className="relative">
                    <Search className="w-4 h-4 absolute left-3 top-3 text-slate-400 pointer-events-none" />
                    <input
                      type="text"
                      value={catalogSearchQuery}
                      onChange={(e) => setCatalogSearchQuery(e.target.value)}
                      placeholder="Type brand or product name..."
                      className="w-full pl-9 pr-3 py-2.5 rounded-xl bg-[#090D11] border border-white/10 text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 text-xs"
                    />
                  </div>

                  {catalogSearchLoading ? (
                    <div className="py-6 text-center text-slate-400 text-xxs">
                      Searching verified cosmetic catalogue...
                    </div>
                  ) : catalogSearchResults.length > 0 ? (
                    <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                      {catalogSearchResults.map((prod) => (
                        <div
                          key={prod.product_id}
                          className="p-3 rounded-xl bg-[#11171E] border border-white/8 flex items-center justify-between gap-2 text-left"
                        >
                          <div className="min-w-0 flex-1 space-y-0.5">
                            <span className="text-xxs text-emerald-400 font-semibold block truncate">
                              {prod.brand}
                            </span>
                            <span className="text-xs font-bold text-white block truncate">
                              {prod.name}
                            </span>
                            <span className="text-xxs text-slate-400 block">
                              {prod.category}
                            </span>
                          </div>

                          <Button
                            size="sm"
                            variant="primary"
                            onClick={() => handleAddCatalogProduct(prod)}
                            disabled={isAddingProduct}
                            className="shrink-0 text-xxs font-bold"
                          >
                            Add
                          </Button>
                        </div>
                      ))}
                    </div>
                  ) : catalogSearchQuery.trim() ? (
                    <div className="py-6 text-center space-y-2 text-slate-400 text-xxs">
                      <p>No catalogue matches found for "{catalogSearchQuery}".</p>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => {
                          setCustomName(catalogSearchQuery);
                          setAddMode("custom");
                        }}
                      >
                        Create Custom Entry
                      </Button>
                    </div>
                  ) : (
                    <div className="py-6 text-center text-slate-500 text-xxs">
                      Search over thousands of verified cosmetic products to add them directly to
                      your shelf.
                    </div>
                  )}
                </div>
              )}

              {/* Mode 2: Custom Product Entry */}
              {addMode === "custom" && (
                <form onSubmit={handleAddCustomProduct} className="space-y-3">
                  <div className="grid grid-cols-2 gap-2.5">
                    <div className="space-y-1">
                      <label className="text-xxs font-semibold text-slate-300 block">
                        Product Name *
                      </label>
                      <input
                        type="text"
                        value={customName}
                        onChange={(e) => setCustomName(e.target.value)}
                        placeholder="e.g. Daily Soothing Gel"
                        required
                        className="w-full text-xs p-2 rounded-xl bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                      />
                    </div>

                    <div className="space-y-1">
                      <label className="text-xxs font-semibold text-slate-300 block">Brand *</label>
                      <input
                        type="text"
                        value={customBrand}
                        onChange={(e) => setCustomBrand(e.target.value)}
                        placeholder="e.g. SkinScience"
                        required
                        className="w-full text-xs p-2 rounded-xl bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2.5">
                    <div className="space-y-1">
                      <label className="text-xxs font-semibold text-slate-300 block">Category</label>
                      <select
                        value={customCategory}
                        onChange={(e) => setCustomCategory(e.target.value)}
                        className="w-full text-xs p-2 rounded-xl bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                      >
                        <option value="Cleanser">Cleanser</option>
                        <option value="Moisturizer">Moisturizer</option>
                        <option value="Serum">Serum</option>
                        <option value="Sunscreen">Sunscreen</option>
                        <option value="Toner">Toner</option>
                        <option value="Treatment">Treatment</option>
                        <option value="Other">Other</option>
                      </select>
                    </div>

                    <div className="space-y-1">
                      <label className="text-xxs font-semibold text-slate-300 block">
                        Initial Status
                      </label>
                      <select
                        value={customStatus}
                        onChange={(e) => setCustomStatus(e.target.value as ShelfStatus)}
                        className="w-full text-xs p-2 rounded-xl bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                      >
                        {SUPPORTED_SHELF_STATUSES.map((st) => (
                          <option key={st.value} value={st.value}>
                            {st.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2.5">
                    <div className="space-y-1">
                      <label className="text-xxs font-semibold text-slate-300 block">
                        Opened Date
                      </label>
                      <input
                        type="date"
                        value={customOpenedAt}
                        onChange={(e) => setCustomOpenedAt(e.target.value)}
                        className="w-full text-xs p-2 rounded-xl bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                      />
                    </div>

                    <div className="space-y-1">
                      <label className="text-xxs font-semibold text-slate-300 block">
                        Expiration Date
                      </label>
                      <input
                        type="date"
                        value={customExpiresAt}
                        onChange={(e) => setCustomExpiresAt(e.target.value)}
                        className="w-full text-xs p-2 rounded-xl bg-[#090D11] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
                      />
                    </div>
                  </div>

                  <div className="space-y-1">
                    <label className="text-xxs font-semibold text-slate-300 block">
                      Ingredients Declaration (Optional)
                    </label>
                    <textarea
                      value={customIngredients}
                      onChange={(e) => setCustomIngredients(e.target.value)}
                      rows={2}
                      placeholder="e.g. Water, Glycerin, Niacinamide, Centella..."
                      className="w-full text-xs p-2.5 rounded-xl bg-[#090D11] border border-white/10 text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 resize-none"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xxs font-semibold text-slate-300 block">
                      Private Notes (Optional)
                    </label>
                    <textarea
                      value={customNotes}
                      onChange={(e) => setCustomNotes(e.target.value)}
                      rows={2}
                      placeholder="Personal notes kept strictly confidential..."
                      className="w-full text-xs p-2.5 rounded-xl bg-[#090D11] border border-white/10 text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 resize-none"
                    />
                  </div>

                  <div className="pt-2 border-t border-white/8 flex items-center justify-end gap-2">
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={() => setIsAddModalOpen(false)}
                      disabled={isAddingProduct}
                    >
                      Cancel
                    </Button>
                    <Button
                      type="submit"
                      variant="primary"
                      size="sm"
                      disabled={isAddingProduct}
                      className="font-bold"
                    >
                      {isAddingProduct ? "Adding..." : "Add to Shelf"}
                    </Button>
                  </div>
                </form>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* 6. Delete Confirmation Dialog                                       */}
      {/* ------------------------------------------------------------------- */}
      {deleteConfirmItem && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/85 backdrop-blur-md animate-in fade-in duration-150"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-dialog-title"
        >
          <div className="w-full max-w-sm bg-[#0E141B] border border-rose-500/30 rounded-2xl p-5 shadow-2xl text-center space-y-3">
            <div className="w-10 h-10 rounded-full bg-rose-950/50 border border-rose-500/40 text-rose-400 mx-auto flex items-center justify-center">
              <Trash2 className="w-5 h-5" />
            </div>

            <div className="space-y-1">
              <h3 id="delete-dialog-title" className="text-sm font-bold text-white">
                Remove from Shelf?
              </h3>
              <p className="text-xxs text-slate-400 leading-normal">
                Are you sure you want to remove{" "}
                <span className="font-semibold text-white">
                  "{deleteConfirmItem.display_name}"
                </span>{" "}
                from your shelf? This will also remove any personal notes or logged reactions for
                this item.
              </p>
            </div>

            <div className="pt-2 flex items-center justify-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setDeleteConfirmItem(null)}
                disabled={isDeleting}
              >
                Keep Item
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleConfirmDelete}
                disabled={isDeleting}
                className="bg-rose-600 hover:bg-rose-500 text-white font-bold"
              >
                {isDeleting ? "Removing..." : "Yes, Remove"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* 7. OCR Scanning Modal                                               */}
      {/* ------------------------------------------------------------------- */}
      <ScanLabelModal
        isOpen={isScanModalOpen}
        onClose={() => setIsScanModalOpen(false)}
        onAddedToShelf={() => {
          fetchShelf();
        }}
      />

      {/* ------------------------------------------------------------------- */}
      {/* 8. Product Reaction Modal                                           */}
      {/* ------------------------------------------------------------------- */}
      {isReactionModalOpen && selectedDetailItem && (
        <ProductReactionModal
          isOpen={isReactionModalOpen}
          onClose={() => setIsReactionModalOpen(false)}
          initialUserProductId={selectedDetailItem.id}
          initialProductId={selectedDetailItem.product_id}
          initialProductName={`${selectedDetailItem.display_brand} ${selectedDetailItem.display_name}`}
        />
      )}
    </div>
  );
};
