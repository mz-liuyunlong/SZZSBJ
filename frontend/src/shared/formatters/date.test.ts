import { describe, expect, it } from "vitest";
import {
  formatDate,
  formatDateTimeSeconds,
  formatShortDateTime,
} from "@/shared/formatters/date";

describe("business date formatters", () => {
  it("converts UTC API timestamps to Asia/Shanghai", () => {
    expect(formatDateTimeSeconds("2026-09-13T08:46:06.355Z")).toBe(
      "2026-09-13 16:46:06",
    );
  });

  it("normalizes offset timestamps without exposing ISO syntax", () => {
    expect(formatDateTimeSeconds("2026-09-13T16:46:06.355669+08:00")).toBe(
      "2026-09-13 16:46:06",
    );
  });

  it("treats timezone-less business timestamps as Asia/Shanghai", () => {
    expect(formatShortDateTime("2026-09-13 16:46:06")).toBe("09-13 16:46");
  });

  it("returns the shared empty marker for invalid input", () => {
    expect(formatDate("not-a-date")).toBe("-");
  });
});
