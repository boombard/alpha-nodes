/** Small display formatters shared by the pages. */

/** A number to `digits` places, or an em dash for null/undefined. */
export function fmt(value: number | null | undefined, digits = 2): string {
  return value == null ? "—" : value.toFixed(digits);
}

/** LLM cost: dollars, or "unknown" when any call had no known price. */
export function fmtCost(cost: number | null): string {
  return cost == null ? "unknown" : `$${cost.toFixed(4)}`;
}

/** Seconds between two ISO times, formatted; an em dash if either is missing. */
export function fmtDuration(start: string | null, end: string | null): string {
  if (!start || !end) return "—";
  const seconds = (Date.parse(end) - Date.parse(start)) / 1000;
  return Number.isFinite(seconds) ? `${seconds.toFixed(1)} s` : "—";
}
