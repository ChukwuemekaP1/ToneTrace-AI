import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  Search,
  X,
  SlidersHorizontal,
  Sparkles,
  AlertTriangle,
  ArrowRight,
  RefreshCw,
  FlaskConical,
  Filter,
} from "lucide-react";
import { catalogService } from "@/api/catalog";
import {
  DiscoveryFilterParams,
  DiscoveryProductSummaryItem,
  ApiError,
} from "@/api/types";
import { GlassCard } from "@/components/ui/GlassCard";
import { Chip } from "@/components/ui/Chip";
import { Button } from "@/components/ui/Button";

export interface DiscoveryPageProps {
  onNavigate: (route: string) => void;
  initialQuery?: string;
}

const SUPPORTED_CATEGORIES = [
  "all",
  "Cleanser",
  "Moisturizer",
  "Serum",
  "Sunscreen",
  "Toner",
  "Treatment",
  "Exfoliant",
];

const SUPPORTED_GOALS = [
  "all",
  "hydration",
  "barrier_repair",
  "acne_control",
  "brightening",
  "calming",
];

const SORT_OPTIONS: Array<{ label: string; value: DiscoveryFilterParams["sort_by"] }> = [
  { label: "Suitability (Best Match)", value: "suitability_desc" },
  { label: "Relevance", value: "relevance" },
  { label: "Name A–Z", value: "name_asc" },
  { label: "Name Z–A", value: "name_desc" },
  { label: "Recently Updated", value: "updated_at_desc" },
];

export const DiscoveryPage: React.FC<DiscoveryPageProps> = ({
  onNavigate,
  initialQuery = "",
}) => {
  const [searchTerm, setSearchTerm] = useState(initialQuery);
  const [debouncedQuery, setDebouncedQuery] = useState(initialQuery);
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [selectedGoal, setSelectedGoal] = useState<string>("all");
  const [sortBy, setSortBy] = useState<DiscoveryFilterParams["sort_by"]>("suitability_desc");
  const [excludeSensitivities, setExcludeSensitivities] = useState<boolean>(true);
  const [requireComplete, setRequireComplete] = useState<boolean>(false);
  const [showFilterSheet, setShowFilterSheet] = useState<boolean>(false);

  // Pagination & Results State
  const [page, setPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [products, setProducts] = useState<DiscoveryProductSummaryItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Debounce search input (around 300ms)
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    debounceTimerRef.current = setTimeout(() => {
      setDebouncedQuery(searchTerm);
      setPage(1); // reset to page 1 on new query
    }, 300);

    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [searchTerm]);

  // Execute search against verified discovery API
  const fetchProducts = useCallback(
    async (currentPage = page) => {
      setLoading(true);
      setError(null);
      try {
        const res = await catalogService.discoverProducts({
          q: debouncedQuery,
          category: selectedCategory,
          goal: selectedGoal,
          sort_by: sortBy,
          exclude_user_sensitivities: excludeSensitivities,
          require_complete_ingredients: requireComplete,
          page: currentPage,
          page_size: 15,
        });

        setProducts(res.items || []);
        setTotalPages(res.total_pages || Math.max(1, Math.ceil((res.total || 0) / 15)));
        setTotalCount(res.total || 0);
      } catch (err) {
        if (err instanceof ApiError) {
          if (err.status === 429) {
            setError("Search request limit reached. Please wait a few moments before searching again.");
          } else {
            setError(err.message || "Failed to search product catalogue.");
          }
        } else {
          setError("Network connection issue while searching catalogue.");
        }
      } finally {
        setLoading(false);
      }
    },
    [
      debouncedQuery,
      selectedCategory,
      selectedGoal,
      sortBy,
      excludeSensitivities,
      requireComplete,
      page,
    ]
  );

  useEffect(() => {
    fetchProducts();
  }, [fetchProducts]);

  const handleClearSearch = () => {
    setSearchTerm("");
    setDebouncedQuery("");
    setPage(1);
  };

  const handleResetFilters = () => {
    setSelectedCategory("all");
    setSelectedGoal("all");
    setSortBy("suitability_desc");
    setExcludeSensitivities(true);
    setRequireComplete(false);
    setPage(1);
  };

  const activeFilterCount =
    (selectedCategory !== "all" ? 1 : 0) +
    (selectedGoal !== "all" ? 1 : 0) +
    (!excludeSensitivities ? 1 : 0) +
    (requireComplete ? 1 : 0) +
    (sortBy !== "suitability_desc" ? 1 : 0);

  return (
    <div className="space-y-4 text-left pb-16">
      {/* ------------------------------------------------------------------- */}
      {/* 1. Header & Search Input Bar                                        */}
      {/* ------------------------------------------------------------------- */}
      <div className="space-y-2 pt-1">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold tracking-tight text-white leading-tight">
              Product{" "}
              <span className="font-serif italic font-normal text-champagne">
                Discovery
              </span>
            </h2>
            <p className="text-xs text-slate-400">
              Transparent, evidence-based cosmetic formulation catalogue.
            </p>
          </div>

          <Button
            size="sm"
            variant="secondary"
            onClick={() => setShowFilterSheet((prev) => !prev)}
            aria-label="Toggle search filters"
            className={`text-xxs px-2.5 py-1.5 flex items-center gap-1.5 ${
              activeFilterCount > 0 ? "border-emerald-500/50 text-emerald-300" : ""
            }`}
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
            <span>Filters</span>
            {activeFilterCount > 0 && (
              <span className="w-4 h-4 rounded-full bg-emerald-500/20 text-emerald-400 text-xxs font-bold flex items-center justify-center">
                {activeFilterCount}
              </span>
            )}
          </Button>
        </div>

        {/* Search Input with Debounce & Clear */}
        <div className="relative">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
            <Search className="w-4 h-4" />
          </div>

          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search by product name, brand, or formula..."
            aria-label="Search cosmetic products"
            className="w-full pl-9 pr-16 py-2.5 rounded-xl text-xs bg-[#10161C]/90 border border-white/10 text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500/60 shadow-glass transition-colors"
          />

          <div className="absolute inset-y-0 right-0 pr-2.5 flex items-center gap-1">
            {loading && (
              <RefreshCw className="w-3.5 h-3.5 text-emerald-400 animate-spin mr-1" />
            )}
            {searchTerm && (
              <button
                type="button"
                onClick={handleClearSearch}
                aria-label="Clear search input"
                className="p-1 rounded-lg hover:bg-white/10 text-slate-400 hover:text-white transition-colors"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Horizontal Category Filter Chips */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 no-scrollbar pt-1">
          {SUPPORTED_CATEGORIES.map((cat) => (
            <button
              key={cat}
              type="button"
              onClick={() => {
                setSelectedCategory(cat);
                setPage(1);
              }}
              className={`px-2.5 py-1 text-xxs font-medium rounded-lg capitalize tracking-tight transition-all shrink-0 ${
                selectedCategory === cat
                  ? "bg-emerald-500 text-slate-950 font-bold shadow-glow"
                  : "bg-white/[0.04] border border-white/8 text-slate-300 hover:border-white/20"
              }`}
            >
              {cat === "all" ? "All Categories" : cat}
            </button>
          ))}
        </div>
      </div>

      {/* ------------------------------------------------------------------- */}
      {/* 2. Expanded Filter Sheet                                            */}
      {/* ------------------------------------------------------------------- */}
      {showFilterSheet && (
        <GlassCard variant="default" className="p-3.5 space-y-3 animate-in fade-in duration-200">
          <div className="flex items-center justify-between border-b border-white/5 pb-2">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-white">
              <Filter className="w-3.5 h-3.5 text-emerald-400" />
              <span>Refine Search Results</span>
            </div>
            <button
              type="button"
              onClick={handleResetFilters}
              className="text-xxs text-slate-400 hover:text-slate-200 underline"
            >
              Reset all
            </button>
          </div>

          <div className="grid grid-cols-2 gap-3 text-left">
            {/* Target Goal */}
            <div className="space-y-1">
              <label htmlFor="filter-goal" className="text-xxs font-semibold text-slate-300 block">
                Target Skincare Goal
              </label>
              <select
                id="filter-goal"
                value={selectedGoal}
                onChange={(e) => {
                  setSelectedGoal(e.target.value);
                  setPage(1);
                }}
                className="w-full text-xxs p-2 rounded-lg bg-[#0C1217] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
              >
                {SUPPORTED_GOALS.map((g) => (
                  <option key={g} value={g}>
                    {g === "all" ? "Any Goal" : g.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </div>

            {/* Sort Order */}
            <div className="space-y-1">
              <label htmlFor="filter-sort" className="text-xxs font-semibold text-slate-300 block">Sort By</label>
              <select
                id="filter-sort"
                value={sortBy}
                onChange={(e) => {
                  setSortBy(e.target.value as any);
                  setPage(1);
                }}
                className="w-full text-xxs p-2 rounded-lg bg-[#0C1217] border border-white/10 text-white focus:outline-none focus:border-emerald-500"
              >
                {SORT_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Toggle Switches */}
          <div className="pt-2 border-t border-white/5 space-y-2 text-xxs">
            <label htmlFor="filter-exclude-sensitivities" className="flex items-center justify-between cursor-pointer">
              <span className="text-slate-300">Exclude My Reported Sensitivities</span>
              <input
                id="filter-exclude-sensitivities"
                type="checkbox"
                checked={excludeSensitivities}
                onChange={(e) => {
                  setExcludeSensitivities(e.target.checked);
                  setPage(1);
                }}
                className="rounded border-white/20 text-emerald-500 focus:ring-0 focus:outline-none"
              />
            </label>

            <label htmlFor="filter-require-complete" className="flex items-center justify-between cursor-pointer">
              <span className="text-slate-300">Require Complete Ingredient Lists</span>
              <input
                id="filter-require-complete"
                type="checkbox"
                checked={requireComplete}
                onChange={(e) => {
                  setRequireComplete(e.target.checked);
                  setPage(1);
                }}
                className="rounded border-white/20 text-emerald-500 focus:ring-0 focus:outline-none"
              />
            </label>
          </div>
        </GlassCard>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* 3. Product Results List                                             */}
      {/* ------------------------------------------------------------------- */}

      {/* Error Recovery State */}
      {error ? (
        <div className="p-4 rounded-2xl bg-rose-950/40 border border-rose-500/40 text-rose-200 space-y-2 text-center">
          <div className="flex items-center justify-center gap-1.5 font-semibold text-xs text-rose-300">
            <AlertTriangle className="w-4 h-4" />
            <span>Search Error</span>
          </div>
          <p className="text-xxs text-rose-300/80 leading-normal">{error}</p>
          <div className="pt-1">
            <Button size="sm" variant="secondary" onClick={() => fetchProducts(page)}>
              Retry Search
            </Button>
          </div>
        </div>
      ) : loading ? (
        /* Loading Skeletons */
        <div className="space-y-2.5">
          {[1, 2, 3, 4].map((n) => (
            <GlassCard key={n} variant="default" className="p-3.5 space-y-2 animate-pulse">
              <div className="flex gap-3">
                <div className="w-12 h-12 rounded-xl bg-white/10 shrink-0"></div>
                <div className="space-y-1.5 flex-1">
                  <div className="h-3.5 bg-white/10 rounded w-3/4"></div>
                  <div className="h-3 bg-white/5 rounded w-1/2"></div>
                </div>
              </div>
            </GlassCard>
          ))}
        </div>
      ) : products.length === 0 ? (
        /* No Results State */
        <div className="p-8 rounded-2xl border border-dashed border-white/10 bg-[#0C1115]/50 text-center space-y-3">
          <div className="w-12 h-12 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center text-slate-400 mx-auto">
            <FlaskConical className="w-6 h-6 text-slate-400" />
          </div>
          <div className="space-y-1 max-w-xs mx-auto">
            <h3 className="text-sm font-semibold text-slate-200">No matching products found</h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              {debouncedQuery
                ? `No products matched "${debouncedQuery}". Try checking for typos or relaxing sensitivity filters.`
                : "No products match the selected category and filter combination."}
            </p>
          </div>
          {activeFilterCount > 0 && (
            <div className="pt-2">
              <Button size="sm" variant="secondary" onClick={handleResetFilters}>
                Clear Active Filters
              </Button>
            </div>
          )}
        </div>
      ) : (
        /* Populated Products Feed */
        <div className="space-y-2.5">
          <div className="flex items-center justify-between px-0.5 text-xxs text-slate-400">
            <span>
              Showing {products.length} of {totalCount} verified products
            </span>
            <span>Page {page} of {totalPages}</span>
          </div>

          {products.map((item) => (
            <div
              key={item.product_id}
              onClick={() => onNavigate(`/products/${item.product_id}`)}
              className="p-3.5 rounded-2xl bg-[#11171E]/90 border border-white/8 hover:border-white/20 transition-all shadow-glass flex items-start gap-3 cursor-pointer group text-left"
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  onNavigate(`/products/${item.product_id}`);
                }
              }}
              aria-label={`View details for ${item.name} by ${item.brand}`}
            >
              {/* Product Image with Designed Soft-Glass Fallback */}
              <div className="w-14 h-14 rounded-xl bg-[#090D11] border border-white/10 shrink-0 overflow-hidden flex items-center justify-center relative">
                {item.image_url ? (
                  <img
                    src={item.image_url}
                    alt={item.name}
                    className="w-full h-full object-cover"
                    onError={(e) => {
                      // Fallback gracefully on broken images
                      (e.target as HTMLElement).style.display = "none";
                    }}
                  />
                ) : (
                  <div className="flex flex-col items-center justify-center text-slate-500">
                    <FlaskConical className="w-5 h-5 text-slate-400 group-hover:text-emerald-400 transition-colors" />
                    <span className="text-[9px] font-mono mt-0.5 uppercase tracking-tighter">
                      {item.brand.slice(0, 3).toUpperCase()}
                    </span>
                  </div>
                )}
              </div>

              {/* Product Meta */}
              <div className="flex-1 min-w-0 space-y-1">
                <div className="flex items-start justify-between gap-1">
                  <div className="min-w-0">
                    <span className="text-xxs text-emerald-400 font-medium block truncate">
                      {item.brand}
                    </span>
                    <h3 className="text-xs font-bold text-white truncate leading-tight group-hover:text-champagne transition-colors">
                      {item.name}
                    </h3>
                  </div>

                  {item.lowest_offer_minor_units !== null &&
                    item.lowest_offer_minor_units !== undefined && (
                      <span className="text-xxs font-mono text-slate-300 font-semibold shrink-0">
                        ${(item.lowest_offer_minor_units / 100).toFixed(2)}
                      </span>
                    )}
                </div>

                <div className="flex items-center gap-1.5 flex-wrap">
                  <Chip variant="neutral" size="sm">
                    {item.category}
                  </Chip>

                  {item.ingredient_data_status === "complete" ? (
                    <Chip variant="verified" size="sm">
                      {item.ingredient_count} INCI
                    </Chip>
                  ) : item.ingredient_data_status === "partial_text_only" ? (
                    <Chip variant="caution" size="sm">
                      Packaging text
                    </Chip>
                  ) : (
                    <Chip variant="caution" size="sm">
                      Missing formula
                    </Chip>
                  )}

                  {/* Recommendation Assessment Badge */}
                  {item.recommendation && (
                    <span
                      className={`text-xxs font-medium flex items-center gap-1 ${
                        item.recommendation.decision === "suitable_for_skin_profile"
                          ? "text-emerald-400"
                          : item.recommendation.decision.includes("sensitivities")
                          ? "text-amber-400"
                          : "text-slate-400"
                      }`}
                    >
                      <Sparkles className="w-2.5 h-2.5" />
                      <span className="truncate max-w-[140px]">
                        {item.recommendation.decision.replace(/_/g, " ")}
                      </span>
                    </span>
                  )}
                </div>
              </div>

              <div className="text-slate-500 group-hover:text-slate-200 self-center transition-colors">
                <ArrowRight className="w-4 h-4" />
              </div>
            </div>
          ))}

          {/* ----------------------------------------------------------------- */}
          {/* 4. Pagination Navigation                                          */}
          {/* ----------------------------------------------------------------- */}
          {totalPages > 1 && (
            <div className="pt-3 flex items-center justify-between border-t border-white/5">
              <Button
                size="sm"
                variant="secondary"
                disabled={page <= 1}
                onClick={() => {
                  const newPage = page - 1;
                  setPage(newPage);
                  fetchProducts(newPage);
                }}
              >
                Previous
              </Button>

              <span className="text-xxs text-slate-400 font-mono">
                Page {page} / {totalPages}
              </span>

              <Button
                size="sm"
                variant="secondary"
                disabled={page >= totalPages}
                onClick={() => {
                  const newPage = page + 1;
                  setPage(newPage);
                  fetchProducts(newPage);
                }}
              >
                Next
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
