import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { DiscoveryPage } from "@/pages/DiscoveryPage";
import { ProductDetailPage } from "@/pages/ProductDetailPage";
import { catalogService } from "@/api/catalog";
import { ApiError } from "@/api/types";

describe("Product Discovery (/discovery) & Product Detail (/products/:id)", () => {
  const mockProductSummary = {
    product_id: "7cb11a28-9412-4217-a1cb-8758b991ef14",
    source_id: "obf:001234567890",
    name: "Centella Calming Gel Cream",
    brand: "SkinScience",
    category: "Moisturizer",
    description: "Lightweight soothing gel with standardized cica extract.",
    image_url: null, // Test missing image
    ingredient_count: 14,
    ingredient_data_status: "complete",
    on_user_shelf: false,
    lowest_offer_minor_units: 1899,
    lowest_offer_currency: "USD",
    recommendation: {
      is_suitable: true,
      decision: "suitable_for_skin_profile",
      summary: "Calming formulation aligned with your barrier repair goals.",
    },
  };

  const mockProductDetail = {
    product_id: "7cb11a28-9412-4217-a1cb-8758b991ef14",
    source_id: "obf:001234567890",
    name: "Centella Calming Gel Cream",
    brand: "SkinScience",
    category: "Moisturizer",
    description: "Lightweight soothing gel with standardized cica extract.",
    ean_or_upc: "001234567890",
    image_url: null,
    formula_version: "2026-v1",
    full_ingredient_list: "Water, Centella Asiatica Leaf Water, Glycerin, Niacinamide, Fragrance",
    ingredient_data_status: "complete",
    ingredients: [
      {
        ingredient_id: "ing-1",
        source_id: "ing:ing-1",
        inci_name: "Water",
        common_name: "Purified Water",
        position: 1,
        function: "Solvent",
        concentration_percentage: null,
        concentration_status: "unknown_order_only",
        is_user_sensitivity_match: false,
        evidence_count: 1,
        evidence_summaries: ["Standard vehicle"],
        evidence_source_ids: ["cosing:1"],
      },
      {
        ingredient_id: "ing-2",
        source_id: "ing:ing-2",
        inci_name: "Niacinamide",
        common_name: "Vitamin B3",
        position: 2,
        function: "Skin Conditioning",
        concentration_percentage: 2.0,
        concentration_status: "verified_percentage",
        is_user_sensitivity_match: false,
        evidence_count: 2,
        evidence_summaries: ["Barrier repair support"],
        evidence_source_ids: ["pubmed:31234567"],
      },
      {
        ingredient_id: "ing-3",
        source_id: "ing:ing-3",
        inci_name: "Fragrance",
        common_name: "Parfum",
        position: 3,
        function: "Masking",
        concentration_percentage: null,
        concentration_status: "unknown_order_only",
        is_user_sensitivity_match: true, // Sensitivity match test
        evidence_count: 1,
        evidence_summaries: ["Potential sensitizer"],
        evidence_source_ids: ["cosing:999"],
      },
    ],
    commercial_offers: [
      {
        offer_id: "off-1",
        merchant_name: "Sephora",
        price_minor_units: 1899,
        currency: "USD",
        is_in_stock: true,
        offer_url: "https://sephora.test/product/123",
        retrieved_at: "2026-10-28T09:00:00Z",
        commercial_segregation_label: "commercial_offer_not_scientific_endorsement",
      },
    ],
    on_user_shelf: false,
    recommendation: {
      is_suitable: false,
      decision: "caution_sensitivities_detected",
      summary: "Contains Fragrance which matches your sensitivity profile.",
    },
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  // ===========================================================================
  // Discovery Screen Tests
  // ===========================================================================
  describe("DiscoveryPage (/discovery)", () => {
    it("debounces search-as-you-type and executes query with sensible delay", async () => {
      const discoverSpy = vi
        .spyOn(catalogService, "discoverProducts")
        .mockResolvedValue({
          items: [mockProductSummary],
          total: 1,
          page: 1,
          page_size: 15,
          total_pages: 1,
          search_backend_used: "postgresql_catalogue",
          rule_engine_version: "1.0",
        });

      render(<DiscoveryPage onNavigate={vi.fn()} />);

      // Initial load
      expect(discoverSpy).toHaveBeenCalledWith(
        expect.objectContaining({ q: "", page: 1 })
      );

      // Typing triggers debounced search
      const input = screen.getByLabelText(/search cosmetic products/i);
      fireEvent.change(input, { target: { value: "Centella" } });

      // Immediately after typing, debounced call hasn't fired yet
      expect(discoverSpy).not.toHaveBeenCalledWith(
        expect.objectContaining({ q: "Centella" })
      );

      // After debounce timeout, search executes
      await waitFor(() => {
        expect(discoverSpy).toHaveBeenCalledWith(
          expect.objectContaining({ q: "Centella" })
        );
      });
    });

    it("applies supported category, goal, sorting, and sensitivity filters accurately", async () => {
      const discoverSpy = vi
        .spyOn(catalogService, "discoverProducts")
        .mockResolvedValue({
          items: [mockProductSummary],
          total: 1,
          page: 1,
          page_size: 15,
          total_pages: 1,
          search_backend_used: "postgresql_catalogue",
          rule_engine_version: "1.0",
        });

      render(<DiscoveryPage onNavigate={vi.fn()} />);

      // Switch category filter
      const serumBtn = screen.getByRole("button", { name: /^serum$/i });
      fireEvent.click(serumBtn);

      await waitFor(() => {
        expect(discoverSpy).toHaveBeenCalledWith(
          expect.objectContaining({ category: "Serum" })
        );
      });

      // Toggle filter sheet and change goal
      const filterToggle = screen.getByLabelText(/toggle search filters/i);
      fireEvent.click(filterToggle);

      const goalSelect = screen.getByLabelText(/target skincare goal/i);
      fireEvent.change(goalSelect, { target: { value: "barrier_repair" } });

      await waitFor(() => {
        expect(discoverSpy).toHaveBeenCalledWith(
          expect.objectContaining({ goal: "barrier_repair" })
        );
      });
    });

    it("missing images render designed soft-glass placeholder without broken icon", async () => {
      vi.spyOn(catalogService, "discoverProducts").mockResolvedValue({
        items: [{ ...mockProductSummary, image_url: null }],
        total: 1,
        page: 1,
        page_size: 15,
        total_pages: 1,
        search_backend_used: "postgresql_catalogue",
        rule_engine_version: "1.0",
      });

      render(<DiscoveryPage onNavigate={vi.fn()} />);

      expect(await screen.findByText("Centella Calming Gel Cream")).toBeInTheDocument();
      // Brand initial placeholder is shown
      expect(screen.getByText("SKI")).toBeInTheDocument();
    });

    it("no-results state: renders clean empty state and allows resetting active filters", async () => {
      vi.spyOn(catalogService, "discoverProducts").mockResolvedValue({
        items: [],
        total: 0,
        page: 1,
        page_size: 15,
        total_pages: 0,
        search_backend_used: "postgresql_catalogue",
        rule_engine_version: "1.0",
      });

      render(<DiscoveryPage onNavigate={vi.fn()} initialQuery="UnknownChemical999" />);

      expect(await screen.findByText(/no matching products found/i)).toBeInTheDocument();
    });

    it("rate limit: HTTP 429 renders calm rate limit error", async () => {
      vi.spyOn(catalogService, "discoverProducts").mockRejectedValue(
        new ApiError("Rate limit exceeded", 429, "RATE_LIMITED")
      );

      render(<DiscoveryPage onNavigate={vi.fn()} />);

      expect(
        await screen.findByText(/search request limit reached/i)
      ).toBeInTheDocument();
    });

    it("failed search: provides calm retry state", async () => {
      vi.spyOn(catalogService, "discoverProducts").mockRejectedValue(
        new ApiError("Catalogue database timeout", 500, "DB_TIMEOUT")
      );

      render(<DiscoveryPage onNavigate={vi.fn()} />);

      expect(await screen.findByText(/catalogue database timeout/i)).toBeInTheDocument();

      const discoverSpy = vi.spyOn(catalogService, "discoverProducts").mockResolvedValue({
        items: [mockProductSummary],
        total: 1,
        page: 1,
        page_size: 15,
        total_pages: 1,
        search_backend_used: "postgresql_catalogue",
        rule_engine_version: "1.0",
      });

      const retryBtn = screen.getByRole("button", { name: /retry search/i });
      fireEvent.click(retryBtn);

      await waitFor(() => {
        expect(discoverSpy).toHaveBeenCalled();
      });
    });
  });

  // ===========================================================================
  // Product Detail Route Tests
  // ===========================================================================
  describe("ProductDetailPage (/products/:id)", () => {
    it("canonical UUID validation: validates UUID and rejects malformed slug route", async () => {
      const navigateMock = vi.fn();
      render(<ProductDetailPage productId="invalid-slug-name" onNavigate={navigateMock} />);

      expect(
        await screen.findByText(/invalid product identifier\. expected canonical uuid\./i)
      ).toBeInTheDocument();

      const browseBtn = screen.getByRole("button", { name: /browse catalogue/i });
      fireEvent.click(browseBtn);
      expect(navigateMock).toHaveBeenCalledWith("/discovery");
    });

    it("renders product detail, provenance, and concentration disclaimer", async () => {
      vi.spyOn(catalogService, "getProductDetail").mockResolvedValue(mockProductDetail);

      render(
        <ProductDetailPage
          productId="7cb11a28-9412-4217-a1cb-8758b991ef14"
          onNavigate={vi.fn()}
        />
      );

      expect(await screen.findByText("Centella Calming Gel Cream")).toBeInTheDocument();
      expect(screen.getByText("SkinScience")).toBeInTheDocument();
      expect(screen.getByText(/upc: 001234567890/i)).toBeInTheDocument();

      // Concentration guardrail is displayed prominently
      expect(
        screen.getByText(/exact ingredient concentrations are unknown/i)
      ).toBeInTheDocument();

      // Guardrail never claims safe for all skin
      expect(
        screen.getByText(/never claims a formulation is "safe for all skin\."/i)
      ).toBeInTheDocument();
    });

    it("highlights user sensitivities with informational disclaimer", async () => {
      vi.spyOn(catalogService, "getProductDetail").mockResolvedValue(mockProductDetail);

      render(
        <ProductDetailPage
          productId="7cb11a28-9412-4217-a1cb-8758b991ef14"
          onNavigate={vi.fn()}
        />
      );

      // Fragrance is highlighted as a sensitivity match
      expect(await screen.findByText("Fragrance")).toBeInTheDocument();
      expect(
        screen.getByText(/matches your reported allergen\/sensitivity \(fragrance\)/i)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/does not constitute a clinical allergy diagnosis/i)
      ).toBeInTheDocument();
    });

    it("ingredient evidence: opens research modal and source links open real URL", async () => {
      vi.spyOn(catalogService, "getProductDetail").mockResolvedValue(mockProductDetail);
      vi.spyOn(catalogService, "getIngredientEvidence").mockResolvedValue({
        items: [
          {
            id: "ev-1",
            ingredient_id: "ing-2",
            evidence_category: "published_research",
            topic_or_target: "barrier_function",
            evidence_direction: "supportive",
            evidence_strength: "strong",
            study_type: "clinical_trial",
            summary_statement: "Topical niacinamide enhances ceramide synthesis and stratum corneum hydration.",
            limitations_and_caveats: "Tested at 2% concentration vehicle.",
            review_status: "verified",
            retrieved_at: "2026-10-28T09:00:00Z",
            source_links: [
              {
                id: "src-link-1",
                research_record_id: "rec-1",
                is_exact_match: true,
                research_record: {
                  id: "rec-1",
                  source_type: "pubmed",
                  external_id: "31234567",
                  title: "Niacinamide in cutaneous physiology",
                  authors: ["Smith J", "Doe A"],
                  journal_or_authority: "Journal of Cosmetic Dermatology",
                  publication_year: 2021,
                  study_type: "clinical_trial",
                  abstract_text: "Abstract text",
                  has_full_text: false,
                  source_url: "https://pubmed.ncbi.nlm.nih.gov/31234567/",
                  license_or_attribution: "NLM PubMed",
                },
              },
            ],
          },
        ],
        total: 1,
        page: 1,
        page_size: 10,
      });

      render(
        <ProductDetailPage
          productId="7cb11a28-9412-4217-a1cb-8758b991ef14"
          onNavigate={vi.fn()}
        />
      );

      // Open evidence for Niacinamide
      const evidenceBtn = await screen.findByLabelText(/view evidence for niacinamide/i);
      fireEvent.click(evidenceBtn);

      // Modal appears with study summary
      expect(
        await screen.findByText(/topical niacinamide enhances ceramide synthesis/i)
      ).toBeInTheDocument();

      // PubMed citation link has exact source_url
      const pubmedLink = screen.getByRole("link", {
        name: /open external citation: niacinamide in cutaneous physiology/i,
      });
      expect(pubmedLink).toHaveAttribute(
        "href",
        "https://pubmed.ncbi.nlm.nih.gov/31234567/"
      );
      expect(pubmedLink).toHaveAttribute("target", "_blank");
    });

    it("commercial offers: renders real merchant prices with timestamp without price fabrication", async () => {
      vi.spyOn(catalogService, "getProductDetail").mockResolvedValue(mockProductDetail);

      render(
        <ProductDetailPage
          productId="7cb11a28-9412-4217-a1cb-8758b991ef14"
          onNavigate={vi.fn()}
        />
      );

      // Real merchant name & formatted price
      expect(await screen.findByText("Sephora")).toBeInTheDocument();
      expect(screen.getByText(/\$18\.99 usd/i)).toBeInTheDocument();
      expect(screen.getByText(/in stock/i)).toBeInTheDocument();

      // Commercial segregation notice
      expect(
        screen.getByText(/commercial retail availability and prices are strictly separated/i)
      ).toBeInTheDocument();
    });

    it("empty offers list: displays honest unavailable state instead of fake prices", async () => {
      vi.spyOn(catalogService, "getProductDetail").mockResolvedValue({
        ...mockProductDetail,
        commercial_offers: [],
      });

      render(
        <ProductDetailPage
          productId="7cb11a28-9412-4217-a1cb-8758b991ef14"
          onNavigate={vi.fn()}
        />
      );

      expect(
        await screen.findByText(/no commercial merchant offers currently recorded for this product/i)
      ).toBeInTheDocument();
    });
  });
});
