/**
 * Profile & Formulation Taxonomy Constants
 *
 * Grounded in verified backend Pydantic models and formulation evaluation rules.
 */

export const SUPPORTED_SKIN_TYPES = [
  {
    id: "combination",
    label: "Combination",
    description: "Oily T-zone, normal to dry cheeks",
  },
  {
    id: "oily",
    label: "Oily",
    description: "Excess sebum production, visible pores",
  },
  {
    id: "dry",
    label: "Dry",
    description: "Tight feeling, prone to flakiness or roughness",
  },
  {
    id: "sensitive",
    label: "Sensitive",
    description: "Easily irritated, prone to stinging or flushing",
  },
  {
    id: "normal",
    label: "Normal",
    description: "Balanced moisture and oil levels",
  },
] as const;

export const SUPPORTED_SKIN_CONCERNS = [
  { id: "acne", label: "Acne & Blemishes" },
  { id: "redness", label: "Redness & Irritation" },
  { id: "hyperpigmentation", label: "Hyperpigmentation & Dark Spots" },
  { id: "barrier_damage", label: "Compromised Barrier" },
  { id: "dryness", label: "Dryness & Dehydration" },
  { id: "pores", label: "Enlarged Pores" },
  { id: "aging", label: "Fine Lines & Aging" },
  { id: "dullness", label: "Dullness & Uneven Tone" },
] as const;

export const SUPPORTED_SKIN_GOALS = [
  { id: "barrier_support", label: "Barrier Support & Protection" },
  { id: "hydration", label: "Hydration & Moisture Balance" },
  { id: "brightening", label: "Brightening & Glow" },
  { id: "acne_control", label: "Blemish & Sebum Control" },
  { id: "soothing", label: "Calming & Anti-Redness" },
  { id: "anti_aging", label: "Firming & Elasticity" },
] as const;

export const COMMON_SENSITIVITIES = [
  "Fragrance (Parfum)",
  "Niacinamide",
  "Salicylic Acid",
  "Retinoids",
  "Benzoyl Peroxide",
  "Essential Oils",
  "Denatured Alcohol",
  "Linalool",
] as const;

export const FACIAL_SCAN_CONSENT_PURPOSE = "facial_scan_processing";
