// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import {
  readUserPreference,
  removeUserPreference,
  writeUserPreference,
} from "@/shared/preferences/userPreferenceCache";

afterEach(() => {
  window.localStorage.clear();
});

describe("user preference cache", () => {
  it("isolates preferences by account scope and schema version", () => {
    writeUserPreference("user-a", "table", 1, { columns: ["sku"] });

    expect(readUserPreference("user-a", "table", 1)).toEqual({ columns: ["sku"] });
    expect(readUserPreference("user-b", "table", 1)).toBeUndefined();
    expect(readUserPreference("user-a", "table", 2)).toBeUndefined();
  });

  it("removes only the selected account preference", () => {
    writeUserPreference("user-a", "table", 1, { columns: ["sku"] });
    writeUserPreference("user-b", "table", 1, { columns: ["image"] });
    removeUserPreference("user-a", "table");

    expect(readUserPreference("user-a", "table", 1)).toBeUndefined();
    expect(readUserPreference("user-b", "table", 1)).toEqual({ columns: ["image"] });
  });
});
