// @vitest-environment jsdom
import { beforeEach, expect, it } from "vitest";
import { writeUserPreference } from "@/shared/preferences/userPreferenceCache";
import { domesticColumnPreferenceKey, readDomesticColumns } from "./domesticColumnPreferences";

beforeEach(() => localStorage.clear());

it("adds identity columns to old preferences without restoring other hidden columns or losing widths", () => {
  writeUserPreference("user", domesticColumnPreferenceKey, 1, { keys: ["sku", "store", "balance"], widths: { sku: 231 } });
  const settings = readDomesticColumns("user");
  expect(settings.keys).toEqual(["arrival", "draft", "sku", "store", "item", "gtin", "owner", "balance"]);
  expect(settings.widths.sku).toBe(231);
  expect(settings.keys).not.toContain("purchase");
});

it("inserts 草稿号 when upgrading a saved v2 layout, then keeps that layout", () => {
  writeUserPreference("user", domesticColumnPreferenceKey, 2, { keys: ["arrival", "sku", "store"], widths: {} });
  expect(readDomesticColumns("user").keys).toEqual(["arrival", "draft", "sku", "store"]);
  expect(readDomesticColumns("user").keys).toEqual(["arrival", "draft", "sku", "store"]);
});

it("keeps a v3 layout that hid 草稿号", () => {
  writeUserPreference("user", domesticColumnPreferenceKey, 3, { keys: ["arrival", "sku"], widths: {} });
  expect(readDomesticColumns("user").keys).toEqual(["arrival", "sku"]);
});

it("shows all new columns for a new user", () => {
  expect(readDomesticColumns("new-user").keys).toEqual(expect.arrayContaining(["draft", "item", "gtin", "owner"]));
});
