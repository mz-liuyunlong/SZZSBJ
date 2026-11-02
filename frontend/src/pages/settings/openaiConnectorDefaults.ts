/** OpenAI GPT-6 Luna Standard API pricing; 2026-10-30.
 * Standard, short-context list prices in USD per 1,000,000 tokens.
 * The provider's actual bill may differ for cache, long context, tier or residency.
 * https://developers.openai.com/api/docs/pricing
 */
export const OPENAI_FIXED_MODEL = "gpt-6-luna" as const;
export const OPENAI_INPUT_USD_PER_MTOK = 0.10;
export const OPENAI_OUTPUT_USD_PER_MTOK = 0.50;
export const OPENAI_DEFAULT_SCENES = ["keyword_launch", "ai_assistant", "listing_optimization"] as const;

/** Distinguish missing prices from invalid persisted values: never overwrite either silently. */
function parsePersistedRate(value: string | number | null | undefined, fallback: number): number {
  if (value === null || value === undefined) return fallback;
  if (typeof value === "string" && value.trim() === "") {
    throw new Error("INVALID_OPENAI_BILLING_PRICE");
  }
  const parsed = typeof value === "number" ? value : Number(value.trim());
  if (!Number.isFinite(parsed) || parsed < 0) {
    throw new Error("INVALID_OPENAI_BILLING_PRICE");
  }
  return parsed;
}

/** Preserve persisted per-connector billing parameters on ordinary edits. */
export function resolveOpenAIBillingRates(config?: {
  input_price_per_million?: string | number | null;
  output_price_per_million?: string | number | null;
}) {
  return {
    input_price_per_million: parsePersistedRate(
      config?.input_price_per_million, OPENAI_INPUT_USD_PER_MTOK,
    ),
    output_price_per_million: parsePersistedRate(
      config?.output_price_per_million, OPENAI_OUTPUT_USD_PER_MTOK,
    ),
  };
}
