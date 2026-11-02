import { describe, expect, it } from "vitest";
import { OPENAI_FIXED_MODEL, OPENAI_INPUT_USD_PER_MTOK, OPENAI_OUTPUT_USD_PER_MTOK, resolveOpenAIBillingRates } from "./openaiConnectorDefaults";

describe("OpenAI fixed model and official short-context Standard rates", () => {
  it("pins only the supported model", () => {
    expect(OPENAI_FIXED_MODEL).toBe("gpt-6-luna");
  });
  it("uses non-zero published default prices", () => {
    expect(OPENAI_INPUT_USD_PER_MTOK).toBe(0.10);
    expect(OPENAI_OUTPUT_USD_PER_MTOK).toBe(0.50);
  });
});

describe("OpenAI billing persistence", () => {
  it("preserves explicitly stored historical prices including zero", () => {
    expect(resolveOpenAIBillingRates({ input_price_per_million: 2.4, output_price_per_million: 9.5 })).toEqual({
      input_price_per_million: 2.4,
      output_price_per_million: 9.5,
    });
    expect(resolveOpenAIBillingRates({ input_price_per_million: 0, output_price_per_million: 0 })).toEqual({
      input_price_per_million: 0,
      output_price_per_million: 0,
    });
  });
  it("uses defaults only when no prices were configured", () => {
    expect(resolveOpenAIBillingRates()).toEqual({
      input_price_per_million: OPENAI_INPUT_USD_PER_MTOK,
      output_price_per_million: OPENAI_OUTPUT_USD_PER_MTOK,
    });
  });
});

describe("OpenAI billing API string/number contract", () => {
  it("accepts persisted numeric strings without changing the cost values", () => {
    expect(resolveOpenAIBillingRates({
      input_price_per_million: "2.40",
      output_price_per_million: "9.50",
    })).toEqual({
      input_price_per_million: 2.4,
      output_price_per_million: 9.5,
    });
  });
  it("accepts numeric values and retains both numeric and string zero", () => {
    expect(resolveOpenAIBillingRates({
      input_price_per_million: 1.25,
      output_price_per_million: 3.75,
    })).toEqual({
      input_price_per_million: 1.25,
      output_price_per_million: 3.75,
    });
    expect(resolveOpenAIBillingRates({
      input_price_per_million: "0",
      output_price_per_million: 0,
    })).toEqual({
      input_price_per_million: 0,
      output_price_per_million: 0,
    });
  });
  it("defaults only missing values, never existing valid prices", () => {
    expect(resolveOpenAIBillingRates({
      input_price_per_million: "2.4",
    })).toEqual({
      input_price_per_million: 2.4,
      output_price_per_million: OPENAI_OUTPUT_USD_PER_MTOK,
    });
  });
  it("rejects invalid prices rather than silently replacing saved settings", () => {
    for (const invalid of ["", " ", "NaN", "-2", "Infinity"]) {
      expect(() => resolveOpenAIBillingRates({
        input_price_per_million: invalid,
      })).toThrow("INVALID_OPENAI_BILLING_PRICE");
    }
  });
});
