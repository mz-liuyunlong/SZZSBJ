import { describe, expect, it } from "vitest";
import { resolveOperationLogLink } from "./operationLogLinks";

describe("operation log shortcut link resolution", () => {
  it.each([
    ["/keywords/item-123", "/keywords/item-123"],
    ["/ads/item-123", "/ads/item-123"],
    ["/ads/keyword-library?item=123", "/ads/keyword-library?item=123"],
    ["https://example.com/ads", "https://example.com/ads"],
    ["http://example.com/keywords", "http://example.com/keywords"],
    ["  /ads/item-123  ", "/ads/item-123"],
  ])("accepts safe internal or HTTP(S) destination %s", (input, expected) => {
    expect(resolveOperationLogLink(input)).toBe(expected);
  });

  it.each([
    null,
    undefined,
    "",
    "//malicious.example/ads",
    "javascript:alert(1)",
    "data:text/html,boom",
    "file:///etc/passwd",
    "https://user:password@example.com/",
    "/ads\\\\redirect",
    "/ads\nredirect",
    "ads/relative-route",
  ])("rejects unsafe or ambiguous destination %s", (input) => {
    expect(resolveOperationLogLink(input)).toBeNull();
  });
});
