/** Tracking decisions require a non-blank review note, irrespective of outcome. */
export const TRACKING_REVIEW_REASON_MIN = 10;
export function trackingReviewReasonLength(value: string): number {
  // Match Python str.isspace(), counting Unicode code points rather than UTF-16 units.
  return Array.from(value).filter(char => {
    const code = char.charCodeAt(0);
    const whitespace = (code >= 0x09 && code <= 0x0d)
      || (code >= 0x1c && code <= 0x20)
      || (code >= 0x2000 && code <= 0x200a)
      || [0x85, 0xa0, 0x1680, 0x2028, 0x2029, 0x202f, 0x205f, 0x3000].includes(code);
    return !whitespace;
  }).length;
}
export function validTrackingReviewReason(value: string): boolean {
  return trackingReviewReasonLength(value) >= TRACKING_REVIEW_REASON_MIN;
}
