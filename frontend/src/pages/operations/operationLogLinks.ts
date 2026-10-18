/** Resolve safe saved operation-log destinations without allowing executable schemes. */
export function resolveOperationLogLink(raw: string | null | undefined): string | null {
  const value = raw?.trim() ?? "";
  if (!value || [...value].some((character) => {
    const code = character.charCodeAt(0);
    return code < 32 || code === 127 || character === "\\";
  })) return null;
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
