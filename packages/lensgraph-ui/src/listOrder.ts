/**
 * The candidate list's order: filter by presets, quick search and column filters, then sort.
 * One pure function used by the summary grid and the candidate page's Previous/Next, so they
 * can never disagree. See documentation/design/core.md, Reporting: run view.
 */
import { cellText, columnSpecs, type ColumnSpec } from "./candidateColumns";
import type { ColumnFilter, ListState } from "./listState";
import { PRESETS } from "./presets";
import type { CandidateView, RunView } from "./types/run-view";

const NO_VALUE_OPERATORS = new Set(["isEmpty", "isNotEmpty"]);

/** Whether `v` passes a DataGrid-style column filter; incomplete filters (no value) pass everything. */
function passes(spec: ColumnSpec, v: string | number | null, f: ColumnFilter): boolean {
  const { operator: op, value } = f;
  if (op === "isEmpty") return v == null || v === "";
  if (op === "isNotEmpty") return !(v == null || v === "");
  if (!NO_VALUE_OPERATORS.has(op) && value === "") return true;
  if (op === "isAnyOf") {
    const items = (JSON.parse(value) as unknown[]).map(String);
    return v != null && items.includes(String(v));
  }
  if (v == null) return op === "!=" || op === "doesNotEqual" || op === "doesNotContain";
  if (spec.type === "number") {
    const n = Number(value);
    const x = v as number;
    switch (op) {
      case "=": return x === n;
      case "!=": return x !== n;
      case ">": return x > n;
      case ">=": return x >= n;
      case "<": return x < n;
      case "<=": return x <= n;
      default: return true;
    }
  }
  const s = String(v).toLowerCase();
  const t = value.toLowerCase();
  switch (op) {
    case "contains": return s.includes(t);
    case "doesNotContain": return !s.includes(t);
    case "equals": return s === t;
    case "doesNotEqual": return s !== t;
    case "startsWith": return s.startsWith(t);
    case "endsWith": return s.endsWith(t);
    default: return true;
  }
}

/** Ascending comparison with missing values last; direction is applied by the caller to present values only. */
function compare(a: string | number | null, b: string | number | null, sign: 1 | -1): number {
  if (a == null || b == null) return a == null ? (b == null ? 0 : 1) : -1;
  const c = typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b));
  return sign * c;
}

/** Candidates after the list state's presets, quick search and column filters, then its sort (stable; missing values last). */
export function orderedCandidates(view: RunView, state: ListState): CandidateView[] {
  const specs = columnSpecs(view);
  const byField = new Map(specs.map((s) => [s.field, s]));
  const presets = PRESETS.filter((p) => state.presets.includes(p.id));
  const tokens = state.q.toLowerCase().split(/\s+/).filter(Boolean);
  const filters = state.filters.filter((f) => byField.has(f.field));
  const rows = view.candidates.filter(
    (c) =>
      presets.every((p) => p.matches(c)) &&
      tokens.every((t) => specs.some((s) => cellText(s, c).toLowerCase().includes(t))) &&
      filters.every((f) => passes(byField.get(f.field)!, byField.get(f.field)!.value(c), f)),
  );
  const sortSpec = state.sort ? byField.get(state.sort.field) : undefined;
  if (!sortSpec || !state.sort) return rows;
  const sign = state.sort.dir === "desc" ? -1 : 1;
  return rows
    .map((c, i) => ({ c, i, v: sortSpec.value(c) }))
    .sort((x, y) => compare(x.v, y.v, sign) || x.i - y.i)
    .map((x) => x.c);
}

/** Ids of `orderedCandidates`: the order the grid shows and Previous/Next walks. */
export function orderedCandidateIds(view: RunView, state: ListState): string[] {
  return orderedCandidates(view, state).map((c) => c.id);
}

/** Where `id` sits in an ordered id list: index (-1 if absent), list size and its neighbours. */
export function listNeighbours(ids: string[], id: string) {
  const index = ids.indexOf(id);
  return {
    index,
    total: ids.length,
    prev: index > 0 ? ids[index - 1] : null,
    next: index >= 0 && index < ids.length - 1 ? ids[index + 1] : null,
  };
}
