import { EMPTY_TEXT } from "@/shared/formatters/number";

export function formatText(value: unknown, emptyText = EMPTY_TEXT) {
  if (value === null || value === undefined) return emptyText;

  const text = String(value).trim();
  return text === "" ? emptyText : text;
}

export function truncateText(value: unknown, maxLength = 32, emptyText = EMPTY_TEXT) {
  const text = formatText(value, emptyText);
  if (text === emptyText || text.length <= maxLength) return text;

  return `${text.slice(0, Math.max(0, maxLength - 1))}…`;
}

export function joinText(values: unknown[], separator = " / ", emptyText = EMPTY_TEXT) {
  const text = values
    .map((value) => formatText(value, ""))
    .filter(Boolean)
    .join(separator);

  return text || emptyText;
}
