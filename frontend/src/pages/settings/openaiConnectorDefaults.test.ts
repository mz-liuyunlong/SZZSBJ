import { describe, expect, it } from "vitest";
import { OPENAI_FIXED_MODEL, OPENAI_INPUT_USD_PER_MTOK, OPENAI_OUTPUT_USD_PER_MTOK } from "./openaiConnectorDefaults";

describe("OpenAI fixed model and official short-context Standard rates", () => {
  it("pins only the supported model", () => {
    expect(OPENAI_FIXED_MODEL).toBe("gpt-6-luna");
  });
  it("uses non-zero published default prices", () => {
    expect(OPENAI_INPUT_USD_PER_MTOK).toBe(0.10);
    expect(OPENAI_OUTPUT_USD_PER_MTOK).toBe(0.50);
  });
});
