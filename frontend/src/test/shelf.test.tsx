import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ShelfPage, formatExpirationCountdown } from "@/pages/ShelfPage";
import { shelfService, isValidUuid } from "@/api/shelf";
import { catalogService } from "@/api/catalog";
import { ApiError, ShelfItemResponse } from "@/api/types";

describe("My Shelf Management (/shelf) (Phase 6)", () => {
  const mockShelfItem1: ShelfItemResponse = {
    id: "a1111111-2222-3333-4444-555555555555",
    user_id: "u1111111-2222-3333-4444-555555555555",
    product_id: "p1111111-2222-3333-4444-555555555555",
    variant_id: null,
    ocr_job_id: null,
    is_custom: false,
    display_name: "Centella Soothing Cream",
    display_brand: "SkinScience",
    display_category: "Moisturizer",
    catalogue_status: "catalogue_linked",
    ingredient_data_status: "complete",
    ingredient_names: ["Centella Asiatica Leaf Water", "Glycerin", "Niacinamide", "Parfum"],
    sensitivity_alerts: ["Parfum"],
    incomplete_ingredient_warning: null,
    status: "in_use",
    opened_at: "2026-10-01T08:00:00Z",
    expires_at: "2026-11-15T08:00:00Z", // Future / near expiry
    purchase_price_minor_units: 2400,
    purchase_currency: "USD",
    private_notes: "Morning hydration only.",
    is_public: false,
    reactions: [],
    created_at: "2026-10-01T08:00:00Z",
    updated_at: "2026-10-01T08:00:00Z",
  };

  const mockShelfItem2: ShelfItemResponse = {
    id: "b2222222-3333-4444-5555-666666666666",
    user_id: "u1111111-2222-3333-4444-555555555555",
    product_id: null,
    variant_id: null,
    ocr_job_id: null,
    is_custom: true,
    custom_name: "Compounded Azelaic 15%",
    custom_brand: "Derm Pharmacy",
    custom_category: "Treatment",
    display_name: "Compounded Azelaic 15%",
    display_brand: "Derm Pharmacy",
    display_category: "Treatment",
    catalogue_status: "custom_entry",
    ingredient_data_status: "partial_text_only",
    ingredient_names: ["Azelaic Acid", "Aqua", "Propylene Glycol"],
    sensitivity_alerts: [],
    incomplete_ingredient_warning: "Partial packaging text declaration.",
    status: "wishlist",
    opened_at: null,
    expires_at: null,
    purchase_price_minor_units: null,
    purchase_currency: null,
    private_notes: "Recommended by dermatologist for redness.",
    is_public: false,
    reactions: [],
    created_at: "2026-10-15T10:00:00Z",
    updated_at: "2026-10-15T10:00:00Z",
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe("Shelf Listing & Supported Status Filtering", () => {
    it("loads and displays authenticated user's shelf items with real counts and status badges", async () => {
      vi.spyOn(shelfService, "listShelfItems").mockResolvedValue({
        items: [mockShelfItem1, mockShelfItem2],
        total: 2,
        page: 1,
        page_size: 20,
        total_pages: 1,
      });

      render(<ShelfPage onNavigate={vi.fn()} />);

      expect(await screen.findByText("Centella Soothing Cream")).toBeInTheDocument();
      expect(screen.getByText("Compounded Azelaic 15%")).toBeInTheDocument();
      expect(screen.getByText("2 items")).toBeInTheDocument();

      // Badges
      expect(screen.getByText("Catalogue Linked")).toBeInTheDocument();
      expect(screen.getByText("Custom Entry")).toBeInTheDocument();

      // Sensitivity alert
      expect(screen.getByText(/Parfum Alert/i)).toBeInTheDocument();

      // Stored opened date
      expect(screen.getByText(/Opened: 10\/1\/2026/i)).toBeInTheDocument();
    });

    it("filters shelf items by all supported backend enum statuses accurately", async () => {
      const listSpy = vi.spyOn(shelfService, "listShelfItems").mockResolvedValue({
        items: [mockShelfItem1],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      });

      render(<ShelfPage onNavigate={vi.fn()} />);
      await screen.findByText("Centella Soothing Cream");

      // Supported tabs: In Use, Wishlist, Finished, Paused, Discontinued, Avoided
      const wishlistTab = screen.getByRole("button", { name: /^wishlist$/i });
      fireEvent.click(wishlistTab);

      await waitFor(() => {
        expect(listSpy).toHaveBeenCalledWith(
          expect.objectContaining({ status: "wishlist" })
        );
      });

      const finishedTab = screen.getByRole("button", { name: /^finished$/i });
      fireEvent.click(finishedTab);

      await waitFor(() => {
        expect(listSpy).toHaveBeenCalledWith(
          expect.objectContaining({ status: "finished" })
        );
      });

      const avoidedTab = screen.getByRole("button", { name: /^avoided$/i });
      fireEvent.click(avoidedTab);

      await waitFor(() => {
        expect(listSpy).toHaveBeenCalledWith(
          expect.objectContaining({ status: "avoided" })
        );
      });
    });
  });

  describe("Add Product (Catalog Search & Custom Product)", () => {
    it("adds a catalogue-linked product via search and selection", async () => {
      vi.spyOn(shelfService, "listShelfItems").mockResolvedValue({
        items: [],
        total: 0,
        page: 1,
        page_size: 20,
        total_pages: 0,
      });

      const searchSpy = vi.spyOn(catalogService, "discoverProducts").mockResolvedValue({
        items: [
          {
            product_id: "cat-prod-999",
            source_id: "obf:123",
            name: "Hydrating Cleanser",
            brand: "CeraPure",
            category: "Cleanser",
            description: "Gentle non-foaming lotion.",
            image_url: null,
            ingredient_count: 8,
            ingredient_data_status: "complete",
            on_user_shelf: false,
            lowest_offer_minor_units: 1499,
            lowest_offer_currency: "USD",
          },
        ],
        total: 1,
        page: 1,
        page_size: 6,
        total_pages: 1,
        search_backend_used: "postgresql_catalogue",
        rule_engine_version: "1.0",
      });

      const addSpy = vi.spyOn(shelfService, "addShelfItem").mockResolvedValue({
        ...mockShelfItem1,
        display_name: "Hydrating Cleanser",
      });

      render(<ShelfPage onNavigate={vi.fn()} />);

      // Open Add Modal
      const addBtn = screen.getByRole("button", { name: /add product to shelf/i });
      fireEvent.click(addBtn);

      // Search Catalog tab is default
      const searchInput = screen.getByPlaceholderText(/type brand or product name\.\.\./i);
      fireEvent.change(searchInput, { target: { value: "CeraPure" } });

      await waitFor(() => {
        expect(searchSpy).toHaveBeenCalledWith(expect.objectContaining({ q: "CeraPure" }));
      });

      expect(await screen.findByText("Hydrating Cleanser")).toBeInTheDocument();

      // Click "Add" button
      const addConfirmBtn = screen.getByRole("button", { name: /^add$/i });
      fireEvent.click(addConfirmBtn);

      await waitFor(() => {
        expect(addSpy).toHaveBeenCalledWith({
          product_id: "cat-prod-999",
          status: "in_use",
        });
      });
    });

    it("handles catalogue duplicate (409) conflict cleanly without breaking UI", async () => {
      vi.spyOn(shelfService, "listShelfItems").mockResolvedValue({
        items: [],
        total: 0,
        page: 1,
        page_size: 20,
        total_pages: 0,
      });

      vi.spyOn(catalogService, "discoverProducts").mockResolvedValue({
        items: [
          {
            product_id: "cat-prod-dup",
            source_id: "obf:dup",
            name: "Duplicate Toner",
            brand: "SkinBrand",
            category: "Toner",
            description: "Soothing toner.",
            image_url: null,
            ingredient_count: 5,
            ingredient_data_status: "complete",
            on_user_shelf: true,
          },
        ],
        total: 1,
        page: 1,
        page_size: 6,
        total_pages: 1,
        search_backend_used: "postgresql_catalogue",
        rule_engine_version: "1.0",
      });

      vi.spyOn(shelfService, "addShelfItem").mockRejectedValue(
        new ApiError("Product is already on your shelf", 409, "CONFLICT")
      );

      render(<ShelfPage onNavigate={vi.fn()} />);

      fireEvent.click(screen.getByRole("button", { name: /add product to shelf/i }));

      const searchInput = screen.getByPlaceholderText(/type brand or product name\.\.\./i);
      fireEvent.change(searchInput, { target: { value: "Duplicate Toner" } });

      expect(await screen.findByText("Duplicate Toner")).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: /^add$/i }));

      expect(
        await screen.findByText(/"Duplicate Toner" is already on your shelf\./i)
      ).toBeInTheDocument();
    });

    it("adds a custom product with user-entered brand, ingredients, status, and dates", async () => {
      vi.spyOn(shelfService, "listShelfItems").mockResolvedValue({
        items: [],
        total: 0,
        page: 1,
        page_size: 20,
        total_pages: 0,
      });

      const addCustomSpy = vi
        .spyOn(shelfService, "addShelfItem")
        .mockResolvedValue(mockShelfItem2);

      render(<ShelfPage onNavigate={vi.fn()} />);

      fireEvent.click(screen.getByRole("button", { name: /add product to shelf/i }));

      // Switch to Custom Product tab
      const customTabBtn = screen.getByRole("button", { name: /custom product/i });
      fireEvent.click(customTabBtn);

      // Fill in custom form
      fireEvent.change(screen.getByPlaceholderText(/e\.g\. daily soothing gel/i), {
        target: { value: "Compounded Azelaic 15%" },
      });
      fireEvent.change(screen.getByPlaceholderText(/e\.g\. skinscience/i), {
        target: { value: "Derm Pharmacy" },
      });
      fireEvent.change(screen.getByPlaceholderText(/e\.g\. water, glycerin, niacinamide/i), {
        target: { value: "Azelaic Acid, Aqua, Propylene Glycol" },
      });

      // Submit
      fireEvent.click(screen.getByRole("button", { name: /add to shelf/i }));

      await waitFor(() => {
        expect(addCustomSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            custom_name: "Compounded Azelaic 15%",
            custom_brand: "Derm Pharmacy",
            custom_ingredient_text: "Azelaic Acid, Aqua, Propylene Glycol",
            status: "in_use",
          })
        );
      });
    });
  });

  describe("Item Detail, Edit, and Delete Workflows", () => {
    it("opens item detail and updates status, dates, and private notes", async () => {
      vi.spyOn(shelfService, "listShelfItems").mockResolvedValue({
        items: [mockShelfItem1],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      });

      const updateSpy = vi.spyOn(shelfService, "updateShelfItem").mockResolvedValue({
        ...mockShelfItem1,
        status: "finished",
        private_notes: "Used up bottle completely.",
      });

      render(<ShelfPage onNavigate={vi.fn()} />);

      // Click card to open detail modal
      const itemCard = await screen.findByText("Centella Soothing Cream");
      fireEvent.click(itemCard);

      // Modal is open
      expect(screen.getByText("Formulation Sensitivity Notice")).toBeInTheDocument();

      // Click Edit
      const editBtn = screen.getByRole("button", { name: /^edit$/i });
      fireEvent.click(editBtn);

      // Change status to finished
      const statusSelect = screen.getByLabelText(/shelf status/i);
      fireEvent.change(statusSelect, { target: { value: "finished" } });

      // Change notes
      const notesArea = screen.getByPlaceholderText(/record personal observations/i);
      fireEvent.change(notesArea, { target: { value: "Used up bottle completely." } });

      // Save changes
      const saveBtn = screen.getByRole("button", { name: /save changes/i });
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(updateSpy).toHaveBeenCalledWith(
          mockShelfItem1.id,
          expect.objectContaining({
            status: "finished",
            private_notes: "Used up bottle completely.",
          })
        );
      });
    });

    it("requires clear confirmation before deleting an item and removes from list after server confirms", async () => {
      vi.spyOn(shelfService, "listShelfItems").mockResolvedValue({
        items: [mockShelfItem1],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      });

      const deleteSpy = vi.spyOn(shelfService, "deleteShelfItem").mockResolvedValue({
        message: "Shelf item removed successfully.",
        deleted_id: mockShelfItem1.id,
      });

      render(<ShelfPage onNavigate={vi.fn()} />);

      // Open detail
      const itemCard = await screen.findByText("Centella Soothing Cream");
      fireEvent.click(itemCard);

      // Click "Remove from Shelf"
      const removeBtn = screen.getByRole("button", { name: /remove from shelf/i });
      fireEvent.click(removeBtn);

      // Confirmation dialog is shown
      expect(screen.getByText(/remove from shelf\?/i)).toBeInTheDocument();
      expect(screen.getByText(/are you sure you want to remove/i)).toBeInTheDocument();
      expect(screen.getByText(`"${mockShelfItem1.display_name}"`)).toBeInTheDocument();

      // Confirm deletion
      const confirmRemoveBtn = screen.getByRole("button", { name: /yes, remove/i });
      fireEvent.click(confirmRemoveBtn);

      await waitFor(() => {
        expect(deleteSpy).toHaveBeenCalledWith(mockShelfItem1.id);
      });

      // After delete, item is removed and empty state appears
      expect(await screen.findByText(/your skincare shelf is empty/i)).toBeInTheDocument();
    });
  });

  describe("Edge Cases: Expiration Countdown & UUID Validation", () => {
    it("formatExpirationCountdown handles expired, near-expiry, future, and missing dates without guessing", () => {
      // 1. Missing date -> null (never guess expiration)
      expect(formatExpirationCountdown(null)).toBeNull();
      expect(formatExpirationCountdown(undefined)).toBeNull();
      expect(formatExpirationCountdown("")).toBeNull();
      expect(formatExpirationCountdown("invalid-date-string")).toBeNull();

      // 2. Expired date
      const pastDate = new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString();
      const pastResult = formatExpirationCountdown(pastDate);
      expect(pastResult?.isExpired).toBe(true);
      expect(pastResult?.label).toMatch(/expired on/i);

      // 3. Near expiry (within 30 days)
      const nearDate = new Date(Date.now() + 12 * 24 * 60 * 60 * 1000).toISOString();
      const nearResult = formatExpirationCountdown(nearDate);
      expect(nearResult?.isNearExpiry).toBe(true);
      expect(nearResult?.label).toMatch(/expires in 12 days/i);

      // 4. Distant future
      const distantDate = new Date(Date.now() + 100 * 24 * 60 * 60 * 1000).toISOString();
      const distantResult = formatExpirationCountdown(distantDate);
      expect(distantResult?.isExpired).toBe(false);
      expect(distantResult?.isNearExpiry).toBe(false);
      expect(distantResult?.label).toMatch(/in 100d/i);
    });

    it("isValidUuid rejects non-UUID or malformed strings", () => {
      expect(isValidUuid("a1111111-2222-3333-4444-555555555555")).toBe(true);
      expect(isValidUuid("slug-name-guess")).toBe(false);
      expect(isValidUuid("../etc/passwd")).toBe(false);
      expect(isValidUuid("12345")).toBe(false);
      expect(isValidUuid("")).toBe(false);
    });

    it("renders calm error banner when shelf fetch fails", async () => {
      vi.spyOn(shelfService, "listShelfItems").mockRejectedValue(
        new ApiError("Failed to fetch shelf items", 500, "SERVER_ERROR")
      );

      render(<ShelfPage onNavigate={vi.fn()} />);

      expect(await screen.findByText(/shelf error/i)).toBeInTheDocument();
      expect(screen.getByText("Failed to fetch shelf items")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /retry loading shelf/i })).toBeInTheDocument();
    });
  });
});
