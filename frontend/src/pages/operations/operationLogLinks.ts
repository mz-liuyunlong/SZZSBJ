/** Resolve safe saved operation-log destinations without allowing executable schemes. */
export function resolveOperationLogLink(raw: string | null | undefined): string | null {
  const value = raw?.trim() ?? "";
  if (!value || /[\u0000-\u001f\u007f\\]/.test(value)) return null;
  if (value.startsWith("/") && !value.startsWith("//")) return value;
  try {
    const url = new URL(value);
    if (
      (url.protocol === "https:" || url.protocol === "http:") &&
      url.hostname && !url.username && !url.password
    ) return url.href;
  } catch {
    // Relative and invalid URLs cannot be opened as external shortcuts.
  }
  return null;
}
