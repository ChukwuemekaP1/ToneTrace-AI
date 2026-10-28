import React, { useState, useRef, useEffect } from "react";
import {
  Sparkles,
  Send,
  AlertTriangle,
  Info,
  ExternalLink,
  ShieldAlert,
  RotateCcw,
  BookOpen,
  FlaskConical,
  CheckCircle2,
  Trash2,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { GlassCard } from "@/components/ui/GlassCard";
import { Chip } from "@/components/ui/Chip";
import { aiService } from "@/api/ai";
import {
  ExplanationResponse,
  SourceReferenceItem,
  ApiError,
  ExplanationEpistemicCategory,
  ExplanationEvidenceStrength,
  GroundingStatusType,
} from "@/api/types";

export interface AskAiPageProps {
  onNavigate?: (route: string) => void;
  initialQuestion?: string;
  initialProductId?: string;
  initialIngredientId?: string;
}

interface ChatExchange {
  id: string;
  question: string;
  response?: ExplanationResponse;
  error?: string;
  errorCode?: string;
  status: "pending" | "success" | "error";
  timestamp: string;
}

export const SUGGESTED_PROMPTS = [
  "What does Niacinamide do in skin barrier repair?",
  "Could this ingredient be irritating for my known sensitivity?",
  "How do these two ingredient lists differ?",
  "What does Ceramide NP do in moisturizers?",
  "Is Centella Asiatica suitable for sensitive or redness-prone skin?",
];

export const GENERAL_AI_DISCLAIMER =
  "ToneTrace AI is an educational skincare companion, not a medical or diagnostic service. Explanations summarize general ingredient reference data and product-label findings without diagnosing conditions, inferring cause from scans, or guaranteeing outcomes.";

export const AskAiPage: React.FC<AskAiPageProps> = ({
  onNavigate,
  initialQuestion,
  initialProductId,
  initialIngredientId,
}) => {
  const [question, setQuestion] = useState<string>(initialQuestion || "");
  const [exchanges, setExchanges] = useState<ChatExchange[]>([]);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [selectedSource, setSelectedSource] = useState<SourceReferenceItem | null>(null);
  const [expandedSources, setExpandedSources] = useState<Record<string, boolean>>({});

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom of chat on new exchange or status change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [exchanges, isSubmitting]);

  // Adjust textarea height automatically
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 140)}px`;
    }
  }, [question]);

  const handleSendQuestion = async (overrideText?: string) => {
    const rawText = overrideText ?? question;
    const cleanQuestion = rawText.trim();
    if (cleanQuestion.length < 3 || isSubmitting) return;

    const exchangeId = `ex-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    const newExchange: ChatExchange = {
      id: exchangeId,
      question: cleanQuestion,
      status: "pending",
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setExchanges((prev) => [...prev, newExchange]);
    setQuestion("");
    setIsSubmitting(true);

    try {
      const response = await aiService.createExplanation({
        question: cleanQuestion,
        product_ids: initialProductId ? [initialProductId] : undefined,
        ingredient_ids: initialIngredientId ? [initialIngredientId] : undefined,
        include_user_skin_profile: true,
      });

      setExchanges((prev) =>
        prev.map((ex) =>
          ex.id === exchangeId ? { ...ex, response, status: "success" } : ex
        )
      );
    } catch (err: unknown) {
      let errorMessage = "Unable to generate an AI explanation. Please check your connection and retry.";
      let errorCode = "UNKNOWN_ERROR";

      if (err instanceof ApiError) {
        errorCode = err.code;
        if (err.status === 429 || err.code === "RATE_LIMIT_EXCEEDED") {
          errorMessage =
            "AI service rate limit reached. Please wait a moment before trying again.";
        } else if (err.status === 504 || err.code === "GATEWAY_TIMEOUT") {
          errorMessage =
            "AI research request timed out. The provider or research database took too long to respond. Please retry.";
        } else if (err.status === 0 || err.code === "NETWORK_ERROR") {
          errorMessage =
            "Network connection error. Please verify your internet connection and retry.";
        } else if (err.status >= 500 || err.code === "DEPENDENCY_ERROR") {
          errorMessage =
            "AI explanation provider is temporarily unavailable. Please retry shortly.";
        } else {
          errorMessage = err.message || errorMessage;
        }
      }

      setExchanges((prev) =>
        prev.map((ex) =>
          ex.id === exchangeId
            ? { ...ex, error: errorMessage, errorCode, status: "error" }
            : ex
        )
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRetry = (cleanQuestion: string) => {
    if (isSubmitting) return;
    handleSendQuestion(cleanQuestion);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendQuestion();
    }
  };

  const handleClearHistory = () => {
    setExchanges([]);
    setQuestion("");
  };

  const toggleSourcesAccordion = (exchangeId: string) => {
    setExpandedSources((prev) => ({
      ...prev,
      [exchangeId]: !prev[exchangeId],
    }));
  };

  // ---------------------------------------------------------------------------
  // Helper Formatters
  // ---------------------------------------------------------------------------
  const getEpistemicBadge = (category: ExplanationEpistemicCategory) => {
    switch (category) {
      case "published_research":
        return { label: "PubMed Research", variant: "verified" as const };
      case "identity_reference":
        return { label: "Official Identity Reference", variant: "verified" as const };
      case "formulation_observation":
        return { label: "Product Formulation", variant: "champagne" as const };
      case "human_interpretation":
        return { label: "Expert Review", variant: "champagne" as const };
      case "marketing_claim":
        return { label: "Commercial Packaging Claim", variant: "caution" as const };
      case "general_guidance":
      default:
        return { label: "General Guidance", variant: "neutral" as const };
    }
  };

  const getStrengthBadge = (strength: ExplanationEvidenceStrength) => {
    switch (strength) {
      case "strong":
        return { label: "Strong Evidence", variant: "verified" as const };
      case "moderate":
        return { label: "Moderate Evidence", variant: "champagne" as const };
      case "limited":
        return { label: "Limited Evidence", variant: "caution" as const };
      case "preliminary":
        return { label: "Preliminary Study", variant: "caution" as const };
      case "conflicting":
        return { label: "Conflicting Data", variant: "caution" as const };
      case "insufficient":
        return { label: "Insufficient Evidence", variant: "neutral" as const };
      case "reference_only":
        return { label: "Reference Only", variant: "neutral" as const };
      case "unknown":
      default:
        return { label: "Unspecified Strength", variant: "neutral" as const };
    }
  };

  const getGroundingStatusHeader = (status: GroundingStatusType) => {
    switch (status) {
      case "verified":
        return {
          label: "Verified Grounded Synthesis",
          color: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
          icon: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />,
        };
      case "fallback_applied":
        return {
          label: "Deterministic Catalogue Fallback",
          color: "text-amber-400 bg-amber-500/10 border-amber-500/20",
          icon: <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />,
        };
      case "insufficient_evidence":
        return {
          label: "Insufficient Catalogue Evidence",
          color: "text-slate-300 bg-white/[0.04] border-white/10",
          icon: <Info className="w-3.5 h-3.5 text-slate-400 shrink-0" />,
        };
      case "safety_escalation":
        return {
          label: "Clinical Safety Escalation",
          color: "text-rose-400 bg-rose-500/10 border-rose-500/20",
          icon: <ShieldAlert className="w-3.5 h-3.5 text-rose-400 shrink-0" />,
        };
      default:
        return {
          label: "AI Synthesis",
          color: "text-slate-300 bg-white/[0.04] border-white/10",
          icon: <Sparkles className="w-3.5 h-3.5 text-emerald-400 shrink-0" />,
        };
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-8.5rem)] max-w-lg mx-auto text-left">
      {/* ------------------------------------------------------------------- */}
      {/* 1. Header & Non-Diagnostic Notice Banner                            */}
      {/* ------------------------------------------------------------------- */}
      <div className="shrink-0 space-y-2 pb-2">
        <div className="flex items-center justify-between">
          <div>
            <h1 aria-label="Ask AI" className="text-xl font-bold tracking-tight text-white leading-tight">
              Ask <span className="font-serif italic font-normal text-champagne">AI</span>
            </h1>
            <p className="text-xs text-slate-400">
              Grounded formulation intelligence backed by verified research.
            </p>
          </div>

          {exchanges.length > 0 && (
            <Button
              size="sm"
              variant="ghost"
              onClick={handleClearHistory}
              aria-label="Clear chat session"
              className="text-slate-400 hover:text-white text-xxs px-2 h-7"
            >
              <Trash2 className="w-3.5 h-3.5 mr-1" />
              <span>Clear</span>
            </Button>
          )}
        </div>

        {/* Ephemeral Session Notice */}
        <div className="p-2.5 rounded-xl bg-[#0C1217] border border-white/8 text-slate-300 text-xxs flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5 text-slate-400">
            <Info className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
            <span>
              Session-only exchange. Responses do not persist after page refresh.
            </span>
          </div>
          <span className="shrink-0 text-xxs text-slate-500 font-mono">schema 1.0</span>
        </div>
      </div>

      {/* ------------------------------------------------------------------- */}
      {/* 2. Chat Conversation Scroll Area                                    */}
      {/* ------------------------------------------------------------------- */}
      <div
        className="flex-1 overflow-y-auto space-y-4 pr-0.5 scrollbar-thin scrollbar-thumb-white/10"
        role="log"
        aria-live="polite"
        aria-label="Skincare conversation history"
      >
        {exchanges.length === 0 && (
          <div className="py-6 space-y-4 text-center">
            <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mx-auto text-emerald-400">
              <FlaskConical className="w-6 h-6" />
            </div>

            <div className="space-y-1">
              <h2 className="text-sm font-bold text-white tracking-tight">
                Grounded Skincare Research Assistant
              </h2>
              <p className="text-xs text-slate-400 max-w-xs mx-auto leading-relaxed">
                ToneTrace AI grounds every answer in peer-reviewed PubMed citations, CosIng regulatory identity records, and catalogue ingredient formulations.
              </p>
            </div>

            {/* Suggested Prompts List */}
            <div className="text-left space-y-1.5 pt-2">
              <p className="text-xxs font-semibold uppercase tracking-wider text-slate-400 px-1">
                Suggested questions:
              </p>
              <div className="flex flex-col gap-1.5">
                {SUGGESTED_PROMPTS.map((promptText) => (
                  <button
                    key={promptText}
                    type="button"
                    onClick={() => {
                      setQuestion(promptText);
                      textareaRef.current?.focus();
                    }}
                    className="p-2.5 rounded-xl bg-surface-elevated/60 hover:bg-surface-elevated border border-white/8 hover:border-emerald-500/30 text-xs text-slate-200 text-left transition-all active:scale-[0.99] flex items-center justify-between gap-2 group"
                  >
                    <span>{promptText}</span>
                    <Sparkles className="w-3.5 h-3.5 text-emerald-400 shrink-0 opacity-60 group-hover:opacity-100 transition-opacity" />
                  </button>
                ))}
              </div>
            </div>

            {/* Non-diagnostic Boundary Reminder */}
            <div className="p-3 rounded-xl bg-[#090D10] border border-white/6 text-xxs text-slate-400 text-left leading-relaxed">
              <span className="font-semibold text-slate-300">Non-Clinical Educational Framework: </span>
              {GENERAL_AI_DISCLAIMER}
            </div>
          </div>
        )}

        {/* Active Conversation Exchanges */}
        {exchanges.map((ex) => (
          <div key={ex.id} className="space-y-3">
            {/* User Message Bubble */}
            <div className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-emerald-500/20 border border-emerald-500/30 text-white px-3.5 py-2.5 text-xs shadow-sm">
                <p className="whitespace-pre-wrap leading-relaxed">{ex.question}</p>
                <div className="text-right mt-1">
                  <span className="text-[10px] text-emerald-300/70">{ex.timestamp}</span>
                </div>
              </div>
            </div>

            {/* AI Response Area */}
            {ex.status === "pending" && (
              <div className="flex justify-start">
                <GlassCard variant="default" className="max-w-[90%] p-3.5 space-y-2 border-white/10">
                  <div className="flex items-center gap-2 text-xs text-emerald-400 font-medium">
                    <Sparkles className="w-4 h-4 animate-spin" />
                    <span>Researching verified evidence & synthesizing explanation...</span>
                  </div>

                  {/* 3-Dot Typing Indicator */}
                  <div
                    className="flex items-center gap-1.5 py-1 px-1"
                    aria-label="ToneTrace AI is researching and synthesizing response"
                  >
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-bounce [animation-delay:-0.3s]" />
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-bounce [animation-delay:-0.15s]" />
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-bounce" />
                    <span className="sr-only">ToneTrace AI is researching and synthesizing response...</span>
                  </div>
                </GlassCard>
              </div>
            )}

            {/* Error & Recoverable State */}
            {ex.status === "error" && (
              <div className="flex justify-start">
                <GlassCard variant="default" className="max-w-[90%] p-3.5 space-y-2.5 border-rose-500/30 bg-rose-500/10">
                  <div className="flex items-center gap-2 text-rose-400 text-xs font-bold">
                    <AlertTriangle className="w-4 h-4 shrink-0" />
                    <span>Research Provider Notice</span>
                  </div>
                  <p className="text-xs text-slate-300 leading-relaxed">{ex.error}</p>
                  <div className="pt-1 flex items-center justify-between">
                    <span className="text-xxs text-rose-300/70 font-mono">
                      {ex.errorCode || "REQUEST_FAILED"}
                    </span>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => handleRetry(ex.question)}
                      aria-label="Retry question"
                      className="text-xxs px-2.5 h-7 flex items-center gap-1"
                    >
                      <RotateCcw className="w-3 h-3 text-rose-400" />
                      <span>Retry</span>
                    </Button>
                  </div>
                </GlassCard>
              </div>
            )}

            {/* Success Response Card */}
            {ex.status === "success" && ex.response && (
              <div className="flex justify-start w-full">
                <GlassCard variant="default" className="w-full p-4 space-y-3.5 border-white/10 text-left">
                  {/* Grounding Status Header */}
                  {(() => {
                    const statusInfo = getGroundingStatusHeader(ex.response.grounding_status);
                    return (
                      <div
                        className={`px-2.5 py-1.5 rounded-lg border text-xxs font-semibold flex items-center justify-between gap-1.5 ${statusInfo.color}`}
                      >
                        <div className="flex items-center gap-1.5">
                          {statusInfo.icon}
                          <span>{statusInfo.label}</span>
                        </div>
                        {ex.response.generation_metadata?.latency_ms && (
                          <span className="font-mono opacity-80">
                            {Math.round(ex.response.generation_metadata.latency_ms)}ms
                          </span>
                        )}
                      </div>
                    );
                  })()}

                  {/* Urgent Care / Safety Escalation Banner */}
                  {(ex.response.safety_notice.requires_professional_care_escalation ||
                    ex.response.grounding_status === "safety_escalation") && (
                    <div className="p-3 rounded-xl bg-rose-500/15 border border-rose-500/30 text-rose-300 space-y-1 text-xs">
                      <div className="flex items-center gap-1.5 font-bold text-rose-200">
                        <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0" />
                        <span>Clinical Medical Care Notice</span>
                      </div>
                      <p className="leading-relaxed text-slate-200">
                        {ex.response.safety_notice.escalation_guidance ||
                          "Concerning symptoms were described. Please consult a healthcare professional."}
                      </p>
                    </div>
                  )}

                  {/* Summary Synthesis */}
                  <div className="space-y-1">
                    <p className="text-xs text-slate-200 leading-relaxed font-normal">
                      {ex.response.summary}
                    </p>
                  </div>

                  {/* Grounded Findings with Epistemic Badges & Citations */}
                  {ex.response.findings && ex.response.findings.length > 0 && (
                    <div className="space-y-2 pt-1">
                      <div className="flex items-center justify-between">
                        <h2 className="text-xxs font-bold uppercase tracking-wider text-slate-400">
                          Grounded Findings ({ex.response.findings.length})
                        </h2>
                      </div>

                      <div className="space-y-2">
                        {ex.response.findings.map((finding, idx) => {
                          const epistemic = getEpistemicBadge(finding.epistemic_category);
                          const strength = getStrengthBadge(finding.evidence_strength);

                          return (
                            <div
                              key={idx}
                              className="p-3 rounded-xl bg-surface-elevated/50 border border-white/6 space-y-2 text-xs"
                            >
                              <div className="flex flex-wrap items-center gap-1.5">
                                <Chip variant={epistemic.variant} size="sm">
                                  {epistemic.label}
                                </Chip>
                                <Chip variant={strength.variant} size="sm">
                                  {strength.label}
                                </Chip>
                              </div>

                              <p className="text-slate-300 leading-relaxed text-xs">
                                {finding.statement}
                              </p>

                              {/* Citation Badges */}
                              {finding.cited_source_ids && finding.cited_source_ids.length > 0 && (
                                <div className="pt-1 flex flex-wrap items-center gap-1.5">
                                  <span className="text-[10px] text-slate-400 font-medium">
                                    Sources:
                                  </span>
                                  {finding.cited_source_ids.map((sid) => {
                                    const sourceRef = ex.response?.source_references?.find(
                                      (s) => s.source_id === sid
                                    );

                                    if (sourceRef) {
                                      return (
                                        <button
                                          key={sid}
                                          type="button"
                                          onClick={() => setSelectedSource(sourceRef)}
                                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-white/[0.06] hover:bg-emerald-500/20 border border-white/10 hover:border-emerald-500/30 text-[10px] font-mono text-emerald-300 transition-colors"
                                          aria-label={`View source citation: ${sourceRef.citation_label}`}
                                        >
                                          <BookOpen className="w-2.5 h-2.5" />
                                          <span className="truncate max-w-[150px]">
                                            {sourceRef.citation_label}
                                          </span>
                                        </button>
                                      );
                                    }

                                    // Unverified / unresolvable reference badge
                                    return (
                                      <span
                                        key={sid}
                                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-rose-500/10 border border-rose-500/20 text-[10px] font-mono text-rose-300"
                                        title={`Unverified context reference: ${sid}`}
                                      >
                                        <AlertTriangle className="w-2.5 h-2.5" />
                                        <span>Unverified reference ({sid})</span>
                                      </span>
                                    );
                                  })}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Uncertainty & Epistemic Limitations */}
                  {ex.response.uncertainty_and_limitations && (
                    <div className="p-3 rounded-xl bg-[#090D10] border border-white/6 space-y-1.5 text-xxs">
                      <div className="flex items-center gap-1.5 text-slate-300 font-semibold">
                        <Info className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                        <span>Formulation Uncertainty & Limitations</span>
                      </div>

                      <ul className="space-y-1 text-slate-400 list-disc list-inside">
                        {ex.response.uncertainty_and_limitations.missing_concentrations_noted && (
                          <li>
                            Exact ingredient concentrations are not disclosed on packaging and cannot be determined from ingredient ordering.
                          </li>
                        )}
                        {ex.response.uncertainty_and_limitations.abstract_only_research_noted && (
                          <li>
                            Scientific research citations reflect bibliographic metadata and abstracts only (full-text clinical papers were not retrieved).
                          </li>
                        )}
                        {ex.response.uncertainty_and_limitations.conflicting_or_limited_evidence_noted && (
                          <li>
                            Some retrieved evidence is preliminary or limited and cannot guarantee individual outcomes.
                          </li>
                        )}
                        {ex.response.uncertainty_and_limitations.untrusted_label_or_ocr_noted && (
                          <li>
                            Product packaging claims are treated as commercial marketing data rather than scientific proof.
                          </li>
                        )}
                        {ex.response.uncertainty_and_limitations.statements?.map((stmt, sIdx) => (
                          <li key={sIdx}>{stmt}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Accordion: All Retrieved Source References */}
                  {ex.response.source_references && ex.response.source_references.length > 0 && (
                    <div className="pt-1 border-t border-white/6">
                      <button
                        type="button"
                        onClick={() => toggleSourcesAccordion(ex.id)}
                        className="w-full flex items-center justify-between text-xxs font-medium text-slate-400 hover:text-white py-1 transition-colors"
                        aria-expanded={expandedSources[ex.id] ?? false}
                      >
                        <span className="flex items-center gap-1.5">
                          <BookOpen className="w-3 h-3 text-emerald-400" />
                          <span>
                            All Retrieved Source References ({ex.response.source_references.length})
                          </span>
                        </span>
                        {expandedSources[ex.id] ? (
                          <ChevronUp className="w-3.5 h-3.5" />
                        ) : (
                          <ChevronDown className="w-3.5 h-3.5" />
                        )}
                      </button>

                      {expandedSources[ex.id] && (
                        <div className="space-y-1.5 pt-2">
                          {ex.response.source_references.map((source) => (
                            <div
                              key={source.source_id}
                              className="p-2 rounded-lg bg-black/40 border border-white/6 text-xxs space-y-1"
                            >
                              <div className="flex items-center justify-between gap-2">
                                <span className="font-semibold text-slate-200 truncate">
                                  {source.title_or_name}
                                </span>
                                <span className="text-[10px] text-slate-500 uppercase font-mono shrink-0">
                                  {source.source_type}
                                </span>
                              </div>

                              <p className="text-slate-400 font-mono text-[10px]">
                                {source.citation_label}
                              </p>

                              <div className="flex items-center justify-between pt-0.5">
                                <span className="text-[10px] text-slate-500">
                                  {source.has_full_text ? "Full reference" : "Abstract / Bibliographic"}
                                </span>
                                {source.source_url && (
                                  <a
                                    href={source.source_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-emerald-400 hover:text-emerald-300 flex items-center gap-1 text-[10px] font-medium"
                                  >
                                    <span>External permalink</span>
                                    <ExternalLink className="w-2.5 h-2.5" />
                                  </a>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* General Non-Diagnostic Safety Disclaimer */}
                  <div className="text-[10px] text-slate-500 pt-1 leading-relaxed border-t border-white/6">
                    {ex.response.safety_notice.general_disclaimer || GENERAL_AI_DISCLAIMER}
                  </div>
                </GlassCard>
              </div>
            )}
          </div>
        ))}

        <div ref={messagesEndRef} />
      </div>

      {/* ------------------------------------------------------------------- */}
      {/* 3. Input & Send Bar                                                 */}
      {/* ------------------------------------------------------------------- */}
      <div className="shrink-0 pt-2 pb-1 space-y-1.5">
        <div className="relative rounded-2xl bg-surface-elevated border border-white/10 focus-within:border-emerald-500/50 p-2 shadow-card transition-all">
          <textarea
            ref={textareaRef}
            rows={1}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about ingredients, formulas, or sensitivities..."
            aria-label="Ask ToneTrace AI a skincare question"
            disabled={isSubmitting}
            maxLength={1500}
            className="w-full bg-transparent text-xs text-white placeholder-slate-500 resize-none outline-none pr-10 pl-1 py-1 max-h-36 leading-relaxed disabled:opacity-50"
          />

          <div className="flex items-center justify-between pt-1 border-t border-white/6 px-1">
            <span className="text-[10px] text-slate-500 font-mono">
              {question.length} / 1500
            </span>

            <Button
              size="sm"
              variant="primary"
              onClick={() => handleSendQuestion()}
              disabled={question.trim().length < 3 || isSubmitting}
              aria-label="Send question"
              className="h-7 px-3 rounded-lg flex items-center gap-1 text-xxs font-bold"
            >
              {isSubmitting ? (
                <>
                  <Sparkles className="w-3 h-3 animate-spin" />
                  <span>Researching...</span>
                </>
              ) : (
                <>
                  <span>Send</span>
                  <Send className="w-3 h-3" />
                </>
              )}
            </Button>
          </div>
        </div>

        <p className="text-[10px] text-slate-500 text-center">
          Press <kbd className="px-1 py-0.5 rounded bg-white/10 text-slate-300">Enter</kbd> to send, <kbd className="px-1 py-0.5 rounded bg-white/10 text-slate-300">Shift + Enter</kbd> for newline.
        </p>
      </div>

      {/* ------------------------------------------------------------------- */}
      {/* 4. Modal: Source Reference Details Viewer                           */}
      {/* ------------------------------------------------------------------- */}
      {selectedSource && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in"
          role="dialog"
          aria-modal="true"
          aria-labelledby="source-detail-modal-title"
        >
          <div className="bg-[#0C1217] border border-white/12 rounded-2xl max-w-sm w-full p-4 space-y-3.5 shadow-card text-left">
            <div className="flex items-start justify-between gap-2">
              <div>
                <span className="text-[10px] uppercase font-bold tracking-wider text-emerald-400">
                  {selectedSource.source_type} Reference
                </span>
                <h3
                  id="source-detail-modal-title"
                  className="text-xs font-bold text-white mt-0.5 leading-tight"
                >
                  {selectedSource.title_or_name}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setSelectedSource(null)}
                className="text-slate-400 hover:text-white p-1 rounded-md text-xs"
                aria-label="Close source detail"
              >
                ✕
              </button>
            </div>

            <div className="p-2.5 rounded-xl bg-white/[0.04] border border-white/6 text-xxs space-y-1.5 font-mono">
              <div>
                <span className="text-slate-500">Citation Label: </span>
                <span className="text-slate-300">{selectedSource.citation_label}</span>
              </div>
              {selectedSource.external_id && (
                <div>
                  <span className="text-slate-500">External ID: </span>
                  <span className="text-slate-300">{selectedSource.external_id}</span>
                </div>
              )}
              <div>
                <span className="text-slate-500">Entity Type: </span>
                <span className="text-slate-300 capitalize">{selectedSource.entity_type}</span>
              </div>
              <div>
                <span className="text-slate-500">Text Access: </span>
                <span className="text-slate-300">
                  {selectedSource.has_full_text ? "Full verified record" : "Abstract & metadata only"}
                </span>
              </div>
            </div>

            <div className="flex items-center justify-between pt-1">
              {selectedSource.source_url ? (
                <a
                  href={selectedSource.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs text-emerald-400 hover:text-emerald-300 font-medium"
                >
                  <span>Open upstream source</span>
                  <ExternalLink className="w-3 h-3" />
                </a>
              ) : selectedSource.entity_type === "product" && onNavigate ? (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    setSelectedSource(null);
                    onNavigate(`/products/${selectedSource.entity_uuid}`);
                  }}
                  className="text-xxs px-2.5 h-7"
                >
                  View Product Detail
                </Button>
              ) : (
                <span className="text-[10px] text-slate-500">
                  Direct database record (no public external link)
                </span>
              )}

              <Button
                size="sm"
                variant="ghost"
                onClick={() => setSelectedSource(null)}
                className="text-xxs px-2.5 h-7"
              >
                Close
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AskAiPage;
