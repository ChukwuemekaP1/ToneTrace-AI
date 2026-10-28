import React, { useEffect, useState, useCallback } from "react";
import {
  ArrowLeft,
  Sparkles,
  AlertTriangle,
  FlaskConical,
  ExternalLink,
  Tag,
  BookOpen,
  ShoppingBag,
  RefreshCw,
  Info,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { catalogService, isValidUuid } from "@/api/catalog";
import {
  DiscoveryProductDetailResponse,
  DiscoveryIngredientDetail,
  IngredientEvidenceItemResponse,
  ApiError,
} from "@/api/types";
import { GlassCard } from "@/components/ui/GlassCard";
import { Chip } from "@/components/ui/Chip";
import { Button } from "@/components/ui/Button";

export interface ProductDetailPageProps {
  productId: string;
  onNavigate: (route: string) => void;
}

export const ProductDetailPage: React.FC<ProductDetailPageProps> = ({
  productId,
  onNavigate,
}) => {
  const [product, setProduct] = useState<DiscoveryProductDetailResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Ingredient Evidence Modal/Drawer State
  const [activeEvidenceIngredient, setActiveEvidenceIngredient] =
    useState<DiscoveryIngredientDetail | null>(null);
  const [evidenceList, setEvidenceList] = useState<IngredientEvidenceItemResponse[]>([]);
  const [evidenceLoading, setEvidenceLoading] = useState<boolean>(false);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);

  // Accordion for full raw packaging text
  const [showRawFormula, setShowRawFormula] = useState<boolean>(false);

  const fetchProductDetail = useCallback(async () => {
    // 1. Validate Canonical UUID upfront
    if (!isValidUuid(productId)) {
      setError("Invalid product identifier. Expected canonical UUID.");
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const data = await catalogService.getProductDetail(productId);
      setProduct(data);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 404) {
          setError("Product not found in cosmetic catalogue.");
        } else if (err.status === 429) {
          setError("Request limit reached. Please wait a moment before trying again.");
        } else {
          setError(err.message || "Failed to load product detail.");
        }
      } else {
        setError("Network error while loading product.");
      }
    } finally {
      setLoading(false);
    }
  }, [productId]);

  useEffect(() => {
    fetchProductDetail();
  }, [fetchProductDetail]);

  // Load Ingredient Evidence on Demand
  const handleOpenEvidence = async (ingredient: DiscoveryIngredientDetail) => {
    setActiveEvidenceIngredient(ingredient);
    setEvidenceLoading(true);
    setEvidenceError(null);
    setEvidenceList([]);
    try {
      const res = await catalogService.getIngredientEvidence(ingredient.ingredient_id);
      setEvidenceList(res.items || []);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : "Failed to load evidence citations for this ingredient.";
      setEvidenceError(msg);
    } finally {
      setEvidenceLoading(false);
    }
  };

  const handleCloseEvidence = () => {
    setActiveEvidenceIngredient(null);
    setEvidenceList([]);
    setEvidenceError(null);
  };

  // ---------------------------------------------------------------------------
  // Invalid UUID / Error View
  // ---------------------------------------------------------------------------
  if (error) {
    return (
      <div className="space-y-4 text-left py-6">
        <button
          type="button"
          onClick={() => onNavigate("/discovery")}
          className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Discovery</span>
        </button>

        <div className="p-6 rounded-2xl bg-rose-950/40 border border-rose-500/40 text-center space-y-3">
          <div className="w-12 h-12 rounded-2xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400 mx-auto">
            <AlertTriangle className="w-6 h-6" />
          </div>
          <div className="space-y-1">
            <h3 className="text-sm font-bold text-white">Product Load Error</h3>
            <p className="text-xs text-rose-300 leading-relaxed">{error}</p>
          </div>
          <div className="pt-2 flex justify-center gap-2">
            <Button size="sm" variant="secondary" onClick={() => onNavigate("/discovery")}>
              Browse Catalogue
            </Button>
            {isValidUuid(productId) && (
              <Button size="sm" variant="primary" onClick={fetchProductDetail}>
                Retry
              </Button>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Loading Skeleton View
  // ---------------------------------------------------------------------------
  if (loading || !product) {
    return (
      <div className="space-y-4 text-left py-2 animate-pulse">
        <div className="h-4 bg-white/10 rounded w-28"></div>
        <div className="p-4 rounded-2xl bg-[#11171E] border border-white/10 space-y-3">
          <div className="flex gap-4">
            <div className="w-20 h-20 rounded-xl bg-white/10 shrink-0"></div>
            <div className="space-y-2 flex-1">
              <div className="h-3 bg-white/10 rounded w-1/3"></div>
              <div className="h-5 bg-white/15 rounded w-3/4"></div>
              <div className="h-3 bg-white/5 rounded w-1/2"></div>
            </div>
          </div>
        </div>
        <div className="h-40 rounded-2xl bg-[#11171E] border border-white/10"></div>
      </div>
    );
  }

  return (
    <div className="space-y-5 text-left pb-20">
      {/* ------------------------------------------------------------------- */}
      {/* 1. Navigation Breadcrumb                                            */}
      {/* ------------------------------------------------------------------- */}
      <div className="flex items-center justify-between pt-1">
        <button
          type="button"
          onClick={() => onNavigate("/discovery")}
          aria-label="Back to discovery catalogue"
          className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Discovery</span>
        </button>

        <span className="text-xxs font-mono text-slate-500 uppercase">
          UUID: {product.product_id.slice(0, 8)}...
        </span>
      </div>

      {/* ------------------------------------------------------------------- */}
      {/* 2. Product Header & Provenance Card                                 */}
      {/* ------------------------------------------------------------------- */}
      <GlassCard variant="default" className="p-4 space-y-3.5">
        <div className="flex items-start gap-3.5">
          {/* Designed Image with Soft-Glass Fallback */}
          <div className="w-20 h-20 rounded-2xl bg-[#090D11] border border-white/12 shrink-0 overflow-hidden flex items-center justify-center relative shadow-glass">
            {product.image_url ? (
              <img
                src={product.image_url}
                alt={product.name}
                className="w-full h-full object-cover"
                onError={(e) => {
                  (e.target as HTMLElement).style.display = "none";
                }}
              />
            ) : (
              <div className="flex flex-col items-center justify-center text-slate-500">
                <FlaskConical className="w-7 h-7 text-emerald-400" />
                <span className="text-[10px] font-mono mt-1 uppercase font-bold tracking-tight text-slate-400">
                  {product.brand.slice(0, 3).toUpperCase()}
                </span>
              </div>
            )}
          </div>

          <div className="flex-1 min-w-0 space-y-1">
            <span className="text-xs font-semibold text-emerald-400 block truncate">
              {product.brand}
            </span>
            <h1 className="text-base font-bold text-white tracking-tight leading-tight">
              {product.name}
            </h1>

            <div className="flex items-center gap-1.5 flex-wrap pt-0.5">
              <Chip variant="neutral" size="sm">
                {product.category}
              </Chip>
              {product.ean_or_upc && (
                <Chip variant="neutral" size="sm" className="font-mono">
                  UPC: {product.ean_or_upc}
                </Chip>
              )}
            </div>
          </div>
        </div>

        {/* Product Description */}
        {product.description && (
          <p className="text-xs text-slate-300 leading-relaxed border-t border-white/5 pt-2.5">
            {product.description}
          </p>
        )}

        {/* Provenance & Formula Context */}
        <div className="pt-2 border-t border-white/5 flex items-center justify-between text-xxs text-slate-400">
          <span>Source: {product.source_id.split(":")[0]?.toUpperCase() || "CATALOGUE"}</span>
          <span>Formula: {product.formula_version || "Current formulation"}</span>
        </div>
      </GlassCard>

      {/* ------------------------------------------------------------------- */}
      {/* 3. Formulation Suitability Assessment Card                          */}
      {/* ------------------------------------------------------------------- */}
      {product.recommendation && (
        <div
          className={`p-3.5 rounded-2xl border shadow-glass space-y-2 ${
            product.recommendation.decision === "suitable_for_skin_profile"
              ? "bg-emerald-950/30 border-emerald-500/30 text-emerald-200"
              : product.recommendation.decision.includes("sensitivities")
              ? "bg-amber-950/30 border-amber-500/30 text-amber-200"
              : "bg-white/[0.03] border-white/10 text-slate-300"
          }`}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs font-bold">
              <Sparkles className="w-3.5 h-3.5 text-champagne" />
              <span>Rule-Based Suitability Assessment</span>
            </div>
            <Chip
              variant={
                product.recommendation.decision === "suitable_for_skin_profile"
                  ? "verified"
                  : "caution"
              }
              size="sm"
            >
              {product.recommendation.decision.replace(/_/g, " ")}
            </Chip>
          </div>

          <p className="text-xs leading-relaxed text-slate-300">
            {product.recommendation.summary}
          </p>

          {/* Epistemic Transparency Guardrail Notice */}
          <div className="pt-2 border-t border-white/5 flex items-start gap-1.5 text-xxs text-slate-400">
            <Info className="w-3.5 h-3.5 text-champagne shrink-0 mt-0.5" />
            <span>
              Recommendations are transparent, rule-based cosmetic suitability evaluations. ToneTrace AI never guarantees clinical results and never claims a formulation is &quot;safe for all skin.&quot;
            </span>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* 4. Ordered Ingredients List                                         */}
      {/* ------------------------------------------------------------------- */}
      <GlassCard variant="default" className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <FlaskConical className="w-4 h-4 text-emerald-400" />
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-200">
              Ordered Ingredient List ({product.ingredients?.length || 0})
            </h2>
          </div>
          <span className="text-xxs text-slate-400 font-mono">Descending by &gt;1%</span>
        </div>

        {/* Concentration Epistemic Disclosure */}
        <div className="p-2.5 rounded-xl bg-white/[0.02] border border-white/5 flex items-start gap-1.5 text-xxs text-slate-400 leading-relaxed">
          <Info className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-0.5" />
          <span>
            Exact ingredient concentrations are unknown unless explicitly declared by a verified source. Packaging order indicates relative descending order above 1% only and cannot be used to infer exact percentage concentration.
          </span>
        </div>

        {/* Itemized Ingredients */}
        {product.ingredients && product.ingredients.length > 0 ? (
          <div className="space-y-2 pt-1">
            {product.ingredients.map((ing) => (
              <div
                key={ing.ingredient_id}
                className={`p-2.5 rounded-xl border transition-colors ${
                  ing.is_user_sensitivity_match
                    ? "bg-amber-950/30 border-amber-500/40 text-amber-200"
                    : "bg-[#0C1217] border-white/5 text-slate-300"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="space-y-0.5 min-w-0">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-xxs font-mono text-slate-400 font-bold">
                        #{ing.position}
                      </span>
                      <span className="text-xs font-bold text-white tracking-tight">
                        {ing.inci_name}
                      </span>
                      {ing.common_name && (
                        <span className="text-xxs text-slate-400 italic">
                          ({ing.common_name})
                        </span>
                      )}
                    </div>

                    {ing.function && (
                      <span className="text-xxs text-slate-400 block">
                        Function: {ing.function}
                      </span>
                    )}
                  </div>

                  {/* Evidence Link Trigger */}
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => handleOpenEvidence(ing)}
                    aria-label={`View evidence for ${ing.inci_name}`}
                    className="shrink-0 text-xxs px-2 py-1 flex items-center gap-1 text-slate-300 hover:text-white"
                  >
                    <BookOpen className="w-3 h-3 text-emerald-400" />
                    <span>Evidence</span>
                  </Button>
                </div>

                {/* Sensitivity Alert Banner */}
                {ing.is_user_sensitivity_match && (
                  <div className="mt-2 p-2 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xxs text-amber-300 flex items-start gap-1.5 leading-normal">
                    <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
                    <span>
                      Matches your reported allergen/sensitivity ({ing.inci_name}). This flag is informational based on your declared profile and does not constitute a clinical allergy diagnosis or medical guarantee.
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="p-4 rounded-xl border border-dashed border-white/10 text-center text-xs text-slate-400">
            No itemized INCI ingredients linked.
          </div>
        )}

        {/* Accordion: Raw Packaging Declaration */}
        {product.full_ingredient_list && (
          <div className="pt-2 border-t border-white/5 space-y-1.5">
            <button
              type="button"
              onClick={() => setShowRawFormula((prev) => !prev)}
              className="w-full flex items-center justify-between text-xxs text-slate-400 hover:text-slate-200 transition-colors"
            >
              <span>View Raw Packaging Declaration</span>
              {showRawFormula ? (
                <ChevronUp className="w-3.5 h-3.5" />
              ) : (
                <ChevronDown className="w-3.5 h-3.5" />
              )}
            </button>

            {showRawFormula && (
              <div className="p-2.5 rounded-xl bg-black/40 border border-white/5 text-xxs font-mono text-slate-300 leading-relaxed whitespace-pre-wrap">
                {product.full_ingredient_list}
              </div>
            )}
          </div>
        )}
      </GlassCard>

      {/* ------------------------------------------------------------------- */}
      {/* 5. Commercial Merchant Offers & Prices                              */}
      {/* ------------------------------------------------------------------- */}
      <GlassCard variant="default" className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <ShoppingBag className="w-4 h-4 text-champagne" />
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-200">
              Verified Merchant Offers
            </h2>
          </div>
          <span className="text-xxs text-slate-400 font-mono">Channel3 / Retail</span>
        </div>

        {/* Commercial Segregation Transparency Notice */}
        <p className="text-xxs text-slate-400 leading-relaxed">
          Commercial retail availability and prices are strictly separated from scientific formulation data. Paid or affiliate offers never influence suitability scores or scientific recommendations.
        </p>

        {product.commercial_offers && product.commercial_offers.length > 0 ? (
          <div className="space-y-2 pt-1">
            {product.commercial_offers.map((offer) => (
              <div
                key={offer.offer_id}
                className="p-2.5 rounded-xl bg-[#0C1217] border border-white/5 flex items-center justify-between"
              >
                <div>
                  <span className="text-xs font-bold text-white block">
                    {offer.merchant_name}
                  </span>
                  <span className="text-xxs text-slate-400">
                    Checked {new Date(offer.retrieved_at).toLocaleDateString()} •{" "}
                    {offer.is_in_stock ? "In Stock" : "Out of Stock"}
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono font-bold text-emerald-400">
                    ${(offer.price_minor_units / 100).toFixed(2)} {offer.currency}
                  </span>
                  {offer.offer_url && (
                    <a
                      href={offer.offer_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="p-1 rounded-lg hover:bg-white/10 text-slate-400 hover:text-white transition-colors"
                      title="Visit merchant offer"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          /* Honest State when no merchant offers are available */
          <div className="p-3.5 rounded-xl border border-dashed border-white/10 text-center text-xs text-slate-400">
            No commercial merchant offers currently recorded for this product.
          </div>
        )}
      </GlassCard>

      {/* ------------------------------------------------------------------- */}
      {/* 6. Ingredient Evidence Modal / Bottom Sheet                         */}
      {/* ------------------------------------------------------------------- */}
      {activeEvidenceIngredient && (
        <div
          role="dialog"
          aria-labelledby="evidence-modal-title"
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-end sm:items-center justify-center p-3 animate-in fade-in"
        >
          <div className="w-full max-w-lg bg-[#0C1217] border border-white/12 rounded-2xl p-4 space-y-3 max-h-[85vh] overflow-y-auto shadow-2xl text-left">
            <div className="flex items-center justify-between border-b border-white/10 pb-2.5">
              <div className="space-y-0.5">
                <span className="text-xxs text-emerald-400 font-semibold uppercase">
                  Scientific Research & Regulatory Evidence
                </span>
                <h3
                  id="evidence-modal-title"
                  className="text-sm font-bold text-white tracking-tight"
                >
                  {activeEvidenceIngredient.inci_name}
                </h3>
              </div>

              <button
                type="button"
                onClick={handleCloseEvidence}
                aria-label="Close evidence panel"
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
              >
                ✕
              </button>
            </div>

            {evidenceLoading ? (
              <div className="py-8 text-center space-y-2">
                <RefreshCw className="w-5 h-5 text-emerald-400 animate-spin mx-auto" />
                <p className="text-xs text-slate-400">
                  Retrieving peer-reviewed citations and CosIng monographs...
                </p>
              </div>
            ) : evidenceError ? (
              <div className="p-3 rounded-xl bg-rose-950/40 border border-rose-500/40 text-rose-300 text-xs">
                {evidenceError}
              </div>
            ) : evidenceList.length === 0 ? (
              <div className="py-6 text-center text-xs text-slate-400 space-y-1">
                <p>No published PubMed citations or CosIng records attached to this ingredient yet.</p>
              </div>
            ) : (
              <div className="space-y-3 pt-1">
                {evidenceList.map((item) => (
                  <div
                    key={item.id}
                    className="p-3 rounded-xl bg-[#11171E] border border-white/8 space-y-2 text-xxs"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <Tag className="w-3 h-3 text-champagne" />
                        <span className="font-semibold text-slate-200">
                          {item.topic_or_target.replace(/_/g, " ")}
                        </span>
                      </div>
                      <Chip variant="neutral" size="sm">
                        {item.study_type || item.evidence_category}
                      </Chip>
                    </div>

                    <p className="text-xs text-slate-300 leading-relaxed">
                      {item.summary_statement}
                    </p>

                    {item.limitations_and_caveats && (
                      <p className="text-slate-400 italic">
                        Limitations: {item.limitations_and_caveats}
                      </p>
                    )}

                    {/* Backing Sources (PubMed, CosIng) */}
                    {item.source_links && item.source_links.length > 0 && (
                      <div className="pt-2 border-t border-white/5 space-y-1.5">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                          Primary Sources:
                        </span>
                        {item.source_links.map((link) => (
                          <div
                            key={link.id}
                            className="p-2 rounded-lg bg-black/30 border border-white/5 flex items-center justify-between gap-2"
                          >
                            <div className="min-w-0">
                              <span className="text-white font-medium block truncate">
                                {link.research_record.title}
                              </span>
                              <span className="text-[10px] text-slate-400 block truncate">
                                {link.research_record.source_type.toUpperCase()} •{" "}
                                {link.research_record.journal_or_authority || "Authority"}{" "}
                                {link.research_record.publication_year ? `(${link.research_record.publication_year})` : ""}
                              </span>
                            </div>

                            {/* Clicking PubMed reference opens the actual source URL */}
                            {link.research_record.source_url && (
                              <a
                                href={link.research_record.source_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                aria-label={`Open external citation: ${link.research_record.title}`}
                                className="p-1 rounded-md text-emerald-400 hover:text-emerald-300 hover:bg-emerald-500/10 transition-colors shrink-0 flex items-center gap-1"
                              >
                                <span className="text-[10px]">View</span>
                                <ExternalLink className="w-3 h-3" />
                              </a>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            <div className="pt-2 border-t border-white/10 flex justify-end">
              <Button size="sm" variant="secondary" onClick={handleCloseEvidence}>
                Close
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
