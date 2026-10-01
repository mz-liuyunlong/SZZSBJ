import { describe, expect, it } from "vitest";
import {
  normalizeSyncTaskBackfillDays,
  parseSyncTaskSchedule,
} from "@/pages/data-center/syncTaskDisplayFormatters";

describe("parseSyncTaskSchedule", () => {
  it("restores fixed China-local run times from the persisted UTC cron", () => {
    expect(parseSyncTaskSchedule("0 19,0 * * *")).toEqual({
      preset: "daily_fixed",
      fixedRunTimes: ["03:00", "08:00"],
    });
  });

  it("restores the supported interval presets", () => {
    expect(parseSyncTaskSchedule("*/30 * * * *")?.preset).toBe("30m");
    expect(parseSyncTaskSchedule("0 * * * *")?.preset).toBe("1h");
    expect(parseSyncTaskSchedule("0 */2 * * *")?.preset).toBe("2h");
  });
});

describe("normalizeSyncTaskBackfillDays", () => {
  it("keeps a supported saved value", () => {
    expect(normalizeSyncTaskBackfillDays(7, 3)).toBe(7);
  });

  it("falls back when a legacy max-pages value is not a backfill option", () => {
    expect(normalizeSyncTaskBackfillDays(10_000, 3)).toBe(3);
  });
});
