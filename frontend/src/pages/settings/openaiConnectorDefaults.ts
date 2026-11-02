/** OpenAI GPT-6 Luna Standard API pricing; 2026-10-30.
 * Standard, short-context list prices in USD per 1,000,000 tokens.
 * The provider's actual bill may differ for cache, long context, tier or residency.
 * https://developers.openai.com/api/docs/pricing
 */
export const OPENAI_FIXED_MODEL = "gpt-6-luna" as const;
export const OPENAI_INPUT_USD_PER_MTOK = 0.10;
export const OPENAI_OUTPUT_USD_PER_MTOK = 0.50;
export const OPENAI_DEFAULT_SCENES = ["keyword_launch", "ai_assistant", "listing_optimization"] as const;
