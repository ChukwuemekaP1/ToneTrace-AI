import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AskAiPage, GENERAL_AI_DISCLAIMER } from "@/pages/AskAiPage";
import { aiService } from "@/api/ai";
import { ApiError, ExplanationResponse } from "@/api/types";

// Mock scrollIntoView for jsdom
window.HTMLElement.prototype.scrollIntoView = vi.fn();

const mockValidResponse: ExplanationResponse = {
  schema_version: "1.0",
  explanation_id: "e1111111-2222-3333-4444-555555555555",
  grounding_status: "verified",
  summary:
    "Niacinamide (Vitamin B3) supports skin barrier integrity by upregulating ceramide synthesis in the stratum corneum.",
  findings: [
    {
      statement:
        "Niacinamide application increases epidermal ceramide levels and reduces transepidermal water loss.",
      cited_source_ids: ["ev:e1111111-0000-0000-0000-000000000001", "res:r1111111-0000-0000-0000-000000000001"],
      epistemic_category: "published_research",
      evidence_strength: "strong",
    },
    {
      statement:
        "Niacinamide is catalogued in CosIng as an authorized skin conditioning and smoothing agent.",
      cited_source_ids: ["ing:i1111111-0000-0000-0000-000000000001"],
      epistemic_category: "identity_reference",
      evidence_strength: "reference_only",
    },
  ],
  source_references: [
    {
      source_id: "ev:e1111111-0000-0000-0000-000000000001",
      entity_type: "ingredient_evidence",
      entity_uuid: "e1111111-0000-0000-0000-000000000001",
      title_or_name: "Barrier Lipid Synthesis & TEWL (published_research)",
      source_type: "pubmed",
      external_id: "PMID:12100180",
      source_url: "https://pubmed.ncbi.nlm.nih.gov/12100180/",
      citation_label: "PubMed PMID 12100180 (2002)",
      epistemic_category: "published_research",
      has_full_text: false,
      retrieved_at: "2026-10-28T10:00:00Z",
    },
    {
      source_id: "res:r1111111-0000-0000-0000-000000000001",
      entity_type: "research_record",
      entity_uuid: "r1111111-0000-0000-0000-000000000001",
      title_or_name: "Nicotinamide increases biosynthesis of ceramides in stratum corneum",
      source_type: "pubmed",
      external_id: "12100180",
      source_url: "https://pubmed.ncbi.nlm.nih.gov/12100180/",
      citation_label: "PUBMED 12100180 (2002): Nicotinamide increases biosynthesis",
      epistemic_category: "published_research",
      has_full_text: false,
      retrieved_at: "2026-10-28T10:00:00Z",
    },
    {
      source_id: "ing:i1111111-0000-0000-0000-000000000001",
      entity_type: "ingredient",
      entity_uuid: "i1111111-0000-0000-0000-000000000001",
      title_or_name: "NIACINAMIDE",
      source_type: "cosing",
      external_id: "NIACINAMIDE",
      source_url: null,
      citation_label: "Canonical Ingredient: NIACINAMIDE (Vitamin B3)",
      epistemic_category: "identity_reference",
      has_full_text: true,
      retrieved_at: "2026-10-28T10:00:00Z",
    },
  ],
  uncertainty_and_limitations: {
    missing_concentrations_noted: true,
    abstract_only_research_noted: true,
    conflicting_or_limited_evidence_noted: false,
    untrusted_label_or_ocr_noted: false,
    statements: [
      "Exact percentage concentrations on consumer labels vary and are rarely disclosed by manufacturers.",
    ],
  },
  safety_notice: {
    is_diagnostic_service: false,
    requires_professional_care_escalation: false,
    escalation_guidance: null,
    general_disclaimer: GENERAL_AI_DISCLAIMER,
  },
  generation_metadata: {
    provider: "google_gemini",
    model: "gemini-3.5-flash-lite",
    latency_ms: 1250.5,
    fallback_used: false,
    fallback_reason: null,
    rejected_source_ids: [],
    prompt_injection_detected: false,
    retrieved_products_count: 0,
    retrieved_ingredients_count: 1,
    retrieved_evidence_count: 2,
    search_backend_used: "postgresql",
    generated_at: "2026-10-28T10:00:01Z",
  },
};

describe("Grounded AI Skincare Assistant (/ask-ai) (Phase 9)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders calm chat surface, session-only disclosure, and suggested prompt chips", () => {
    render(<AskAiPage onNavigate={vi.fn()} />);

    // Header and Accessible Name
    expect(screen.getByRole("heading", { name: "Ask AI" })).toBeInTheDocument();
    expect(
      screen.getByText("Grounded formulation intelligence backed by verified research.")
    ).toBeInTheDocument();

    // Session-only disclosure
    expect(
      screen.getByText(/Session-only exchange. Responses do not persist after page refresh/i)
    ).toBeInTheDocument();

    // Suggested questions
    expect(
      screen.getByText("What does Niacinamide do in skin barrier repair?")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Could this ingredient be irritating for my known sensitivity?")
    ).toBeInTheDocument();
    expect(
      screen.getByText("How do these two ingredient lists differ?")
    ).toBeInTheDocument();

    // Non-diagnostic boundary
    expect(
      screen.getByText(/ToneTrace AI is an educational skincare companion, not a medical or diagnostic service/i)
    ).toBeInTheDocument();

    // Input & Send button
    const input = screen.getByRole("textbox", {
      name: "Ask ToneTrace AI a skincare question",
    });
    expect(input).toBeInTheDocument();

    const sendBtn = screen.getByRole("button", { name: "Send question" });
    expect(sendBtn).toBeDisabled(); // Disabled on empty input
  });

  it("clicking a suggested question populates the textarea for quick submission", () => {
    render(<AskAiPage onNavigate={vi.fn()} />);

    const chip = screen.getByText("What does Niacinamide do in skin barrier repair?");
    fireEvent.click(chip);

    const input = screen.getByRole("textbox", {
      name: "Ask ToneTrace AI a skincare question",
    }) as HTMLTextAreaElement;
    expect(input.value).toBe("What does Niacinamide do in skin barrier repair?");

    // Send button is now enabled
    const sendBtn = screen.getByRole("button", { name: "Send question" });
    expect(sendBtn).toBeEnabled();
  });

  it("submits question, shows 3-dot typing indicator, and renders grounded response with citations", async () => {
    const createExplanationSpy = vi
      .spyOn(aiService, "createExplanation")
      .mockResolvedValue(mockValidResponse);

    render(<AskAiPage onNavigate={vi.fn()} />);

    const input = screen.getByRole("textbox", {
      name: "Ask ToneTrace AI a skincare question",
    });
    fireEvent.change(input, {
      target: { value: "How does Niacinamide repair skin barrier?" },
    });

    const sendBtn = screen.getByRole("button", { name: "Send question" });
    fireEvent.click(sendBtn);

    // Typing indicator should appear
    expect(
      screen.getByText(/Researching verified evidence & synthesizing explanation.../i)
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText("ToneTrace AI is researching and synthesizing response")
    ).toBeInTheDocument();

    // Wait for response to be rendered
    await waitFor(() => {
      expect(createExplanationSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          question: "How does Niacinamide repair skin barrier?",
          include_user_skin_profile: true,
        })
      );
    });

    // Verification badges & Summary
    expect(await screen.findByText("Verified Grounded Synthesis")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Niacinamide (Vitamin B3) supports skin barrier integrity by upregulating ceramide synthesis in the stratum corneum."
      )
    ).toBeInTheDocument();

    // Findings and Epistemic classifications
    expect(screen.getByText("PubMed Research")).toBeInTheDocument();
    expect(screen.getByText("Official Identity Reference")).toBeInTheDocument();
    expect(screen.getByText("Strong Evidence")).toBeInTheDocument();

    // Clickable citation buttons
    expect(
      screen.getByRole("button", {
        name: "View source citation: PubMed PMID 12100180 (2002)",
      })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "View source citation: Canonical Ingredient: NIACINAMIDE (Vitamin B3)",
      })
    ).toBeInTheDocument();

    // Uncertainty and limitation notices
    expect(
      screen.getByText("Formulation Uncertainty & Limitations")
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /Exact ingredient concentrations are not disclosed on packaging and cannot be determined from ingredient ordering/i
      )
    ).toBeInTheDocument();
  });

  it("clicking a citation badge opens the source details modal with provenance and external link", async () => {
    vi.spyOn(aiService, "createExplanation").mockResolvedValue(mockValidResponse);

    render(<AskAiPage onNavigate={vi.fn()} />);

    const input = screen.getByRole("textbox", {
      name: "Ask ToneTrace AI a skincare question",
    });
    fireEvent.change(input, {
      target: { value: "Tell me about Niacinamide" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send question" }));

    const citationBtn = await screen.findByRole("button", {
      name: "View source citation: PubMed PMID 12100180 (2002)",
    });
    fireEvent.click(citationBtn);

    // Source Inspector Modal is visible
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        name: "Barrier Lipid Synthesis & TEWL (published_research)",
      })
    ).toBeInTheDocument();
    expect(screen.getByText("PMID:12100180")).toBeInTheDocument();

    // Authoritative external permalink
    const externalLink = screen.getByRole("link", { name: "Open upstream source" });
    expect(externalLink).toHaveAttribute("href", "https://pubmed.ncbi.nlm.nih.gov/12100180/");
    expect(externalLink).toHaveAttribute("target", "_blank");
    expect(externalLink).toHaveAttribute("rel", "noopener noreferrer");

    // Close modal
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("renders valid response with no citations cleanly without errors", async () => {
    const noCitationResponse: ExplanationResponse = {
      ...mockValidResponse,
      findings: [
        {
          statement: "General cosmetic guidance indicates patch testing new products.",
          cited_source_ids: [],
          epistemic_category: "general_guidance",
          evidence_strength: "reference_only",
        },
      ],
      source_references: [],
    };

    vi.spyOn(aiService, "createExplanation").mockResolvedValue(noCitationResponse);

    render(<AskAiPage onNavigate={vi.fn()} />);

    const input = screen.getByRole("textbox", {
      name: "Ask ToneTrace AI a skincare question",
    });
    fireEvent.change(input, {
      target: { value: "Should I patch test?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send question" }));

    expect(
      await screen.findByText(
        "General cosmetic guidance indicates patch testing new products."
      )
    ).toBeInTheDocument();
    expect(screen.getByText("General Guidance")).toBeInTheDocument();
    expect(screen.queryByText("Sources:")).not.toBeInTheDocument();
  });

  it("handles unresolvable/invalid citation IDs safely by flagging them instead of fabricating links", async () => {
    const invalidCitationResponse: ExplanationResponse = {
      ...mockValidResponse,
      findings: [
        {
          statement: "Some finding referencing an unresolvable source.",
          cited_source_ids: ["unresolvable-source-id-999"],
          epistemic_category: "published_research",
          evidence_strength: "limited",
        },
      ],
      source_references: [], // Empty source references
    };

    vi.spyOn(aiService, "createExplanation").mockResolvedValue(invalidCitationResponse);

    render(<AskAiPage onNavigate={vi.fn()} />);

    const input = screen.getByRole("textbox", {
      name: "Ask ToneTrace AI a skincare question",
    });
    fireEvent.change(input, {
      target: { value: "Tell me about unresolvable source" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send question" }));

    // Unverified reference chip rendered safely
    expect(
      await screen.findByText("Unverified reference (unresolvable-source-id-999)")
    ).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /upstream/i })).not.toBeInTheDocument();
  });

  it("renders honest insufficient evidence state when no catalog or research records match", async () => {
    const insufficientEvidenceResponse: ExplanationResponse = {
      ...mockValidResponse,
      grounding_status: "insufficient_evidence",
      summary:
        "No matching product, ingredient, or research evidence records were found in the ToneTrace catalogue to ground an explanation for this request.",
      findings: [],
      source_references: [],
      uncertainty_and_limitations: {
        missing_concentrations_noted: true,
        abstract_only_research_noted: false,
        conflicting_or_limited_evidence_noted: false,
        untrusted_label_or_ocr_noted: false,
        statements: [
          "No retrieved catalog or evidence records matched the query; ToneTrace AI refuses to generate ungrounded claims without source records.",
        ],
      },
    };

    vi.spyOn(aiService, "createExplanation").mockResolvedValue(insufficientEvidenceResponse);

    render(<AskAiPage onNavigate={vi.fn()} />);

    const input = screen.getByRole("textbox", {
      name: "Ask ToneTrace AI a skincare question",
    });
    fireEvent.change(input, {
      target: { value: "What is XYZ Unknown Herb?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send question" }));

    expect(
      await screen.findByText("Insufficient Catalogue Evidence")
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /No matching product, ingredient, or research evidence records were found/i
      )
    ).toBeInTheDocument();
    expect(
      screen.getByText(/ToneTrace AI refuses to generate ungrounded claims without source records/i)
    ).toBeInTheDocument();
  });

  it("displays prominent clinical escalation alert when backend flags concerning medical symptoms", async () => {
    const safetyEscalationResponse: ExplanationResponse = {
      ...mockValidResponse,
      grounding_status: "safety_escalation",
      summary:
        "Concerning symptoms were detected in your inquiry. ToneTrace AI does not diagnose or treat medical conditions.",
      safety_notice: {
        is_diagnostic_service: false,
        requires_professional_care_escalation: true,
        escalation_guidance:
          "Concerning dermatological symptoms were mentioned (such as bleeding lesion, severe blistering, or acute swelling). Please seek immediate evaluation from a board-certified dermatologist.",
        general_disclaimer: GENERAL_AI_DISCLAIMER,
      },
      findings: [],
    };

    vi.spyOn(aiService, "createExplanation").mockResolvedValue(safetyEscalationResponse);

    render(<AskAiPage onNavigate={vi.fn()} />);

    const input = screen.getByRole("textbox", {
      name: "Ask ToneTrace AI a skincare question",
    });
    fireEvent.change(input, {
      target: { value: "I have a bleeding mole on my cheek" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send question" }));

    expect(await screen.findByText("Clinical Safety Escalation")).toBeInTheDocument();
    expect(screen.getByText("Clinical Medical Care Notice")).toBeInTheDocument();
    expect(
      screen.getByText(/Concerning dermatological symptoms were mentioned/i)
    ).toBeInTheDocument();
  });

  it("handles provider quota / rate limit (429) gracefully with recoverable retry state", async () => {
    const rateLimitError = new ApiError(
      "Rate limit exceeded. Please wait.",
      429,
      "RATE_LIMIT_EXCEEDED"
    );
    const createExplanationSpy = vi
      .spyOn(aiService, "createExplanation")
      .mockRejectedValueOnce(rateLimitError)
      .mockResolvedValueOnce(mockValidResponse);

    render(<AskAiPage onNavigate={vi.fn()} />);

    const input = screen.getByRole("textbox", {
      name: "Ask ToneTrace AI a skincare question",
    });
    fireEvent.change(input, {
      target: { value: "Tell me about Ceramides" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send question" }));

    // Error banner displayed
    expect(
      await screen.findByText(
        "AI service rate limit reached. Please wait a moment before trying again."
      )
    ).toBeInTheDocument();
    expect(screen.getByText("RATE_LIMIT_EXCEEDED")).toBeInTheDocument();

    // Click Retry
    const retryBtn = screen.getByRole("button", { name: "Retry question" });
    fireEvent.click(retryBtn);

    // Resolves successfully
    expect(await screen.findByText("Verified Grounded Synthesis")).toBeInTheDocument();
    expect(createExplanationSpy).toHaveBeenCalledTimes(2);
  });

  it("handles network error / timeout gracefully with clear error state", async () => {
    const networkError = new ApiError("Network error occurred", 0, "NETWORK_ERROR");
    vi.spyOn(aiService, "createExplanation").mockRejectedValue(networkError);

    render(<AskAiPage onNavigate={vi.fn()} />);

    const input = screen.getByRole("textbox", {
      name: "Ask ToneTrace AI a skincare question",
    });
    fireEvent.change(input, {
      target: { value: "Will this cause acne?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send question" }));

    expect(
      await screen.findByText(
        "Network connection error. Please verify your internet connection and retry."
      )
    ).toBeInTheDocument();
    expect(screen.getByText("NETWORK_ERROR")).toBeInTheDocument();
  });

  it("handles server / dependency error (503) gracefully", async () => {
    const serverError = new ApiError(
      "Gemini provider unavailable",
      503,
      "DEPENDENCY_ERROR"
    );
    vi.spyOn(aiService, "createExplanation").mockRejectedValue(serverError);

    render(<AskAiPage onNavigate={vi.fn()} />);

    const input = screen.getByRole("textbox", {
      name: "Ask ToneTrace AI a skincare question",
    });
    fireEvent.change(input, {
      target: { value: "Explain Hyaluronic Acid" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send question" }));

    expect(
      await screen.findByText(
        "AI explanation provider is temporarily unavailable. Please retry shortly."
      )
    ).toBeInTheDocument();
  });

  it("prevents repeated send when button is clicked multiple times while request is pending", async () => {
    let resolvePromise: (val: ExplanationResponse) => void;
    const pendingPromise = new Promise<ExplanationResponse>((resolve) => {
      resolvePromise = resolve;
    });

    const createExplanationSpy = vi
      .spyOn(aiService, "createExplanation")
      .mockReturnValue(pendingPromise);

    render(<AskAiPage onNavigate={vi.fn()} />);

    const input = screen.getByRole("textbox", {
      name: "Ask ToneTrace AI a skincare question",
    });
    fireEvent.change(input, {
      target: { value: "What does Centella Asiatica do?" },
    });

    const sendBtn = screen.getByRole("button", { name: "Send question" });
    fireEvent.click(sendBtn);

    // Rapid double click
    fireEvent.click(sendBtn);
    fireEvent.click(sendBtn);

    expect(createExplanationSpy).toHaveBeenCalledTimes(1);

    // Resolve promise
    resolvePromise!(mockValidResponse);
    expect(await screen.findByText("Verified Grounded Synthesis")).toBeInTheDocument();
  });

  it("handles Enter key to send and Shift+Enter for newline without sending", async () => {
    const createExplanationSpy = vi
      .spyOn(aiService, "createExplanation")
      .mockResolvedValue(mockValidResponse);

    render(<AskAiPage onNavigate={vi.fn()} />);

    const input = screen.getByRole("textbox", {
      name: "Ask ToneTrace AI a skincare question",
    });
    fireEvent.change(input, {
      target: { value: "Line 1" },
    });

    // Shift + Enter should NOT send
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
    expect(createExplanationSpy).not.toHaveBeenCalled();

    // Plain Enter SHOULD send
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false });
    await waitFor(() => {
      expect(createExplanationSpy).toHaveBeenCalledTimes(1);
    });
  });
});
