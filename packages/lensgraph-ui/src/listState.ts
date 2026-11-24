/**
 * The candidate list's view state (sort, quick search, preset chips, column filters) and its
 * round trip through the hash URL query, e.g. `#/?sort=evidence_share:desc&q=S1&preset=flags`,
 * so it survives navigation and can be shared. See documentation/design/core.md, Reporting: run view.
 */
import { isPresetId, type PresetId } from "./presets";

/** One column filter, as the DataGrid filter panel produces it. `value` is "" when unused; for `isAnyOf` it is a JSON array. */
export interface ColumnFilter {
  field: string;
  operator: string;
  value: string;
}

/** Sort by one column. */
export interface SortState {
  field: string;
  dir: "asc" | "desc";
}

/** Everything that determines the order and membership of the candidate list. */
export interface ListState {
  sort: SortState | null;
  /** Quick-search text; whitespace-separated tokens must all match. */
  q: string;
  presets: PresetId[];
  filters: ColumnFilter[];
}

/** No sorting, search or filtering: the run's own candidate order. */
export const EMPTY_LIST: ListState = { sort: null, q: "", presets: [], filters: [] };

/** Serialise to a URL query string (no leading "?"); an empty state gives "". */
export function listToQuery(s: ListState): string {
  const p = new URLSearchParams();
  if (s.sort) p.set("sort", `${s.sort.field}:${s.sort.dir}`);
  if (s.q) p.set("q", s.q);
  if (s.presets.length) p.set("preset", s.presets.join(","));
  for (const f of s.filters) p.append("f", `${f.field}|${f.operator}|${f.value}`);
  return p.toString();
}

/** Parse a query string produced by `listToQuery`; unknown or malformed parts are ignored. */
export function listFromQuery(query: string): ListState {
  const p = new URLSearchParams(query);
  const sortRaw = p.get("sort");
  const cut = sortRaw ? sortRaw.lastIndexOf(":") : -1;
  const dir = cut > 0 ? sortRaw!.slice(cut + 1) : "";
  const sort: SortState | null =
    dir === "asc" || dir === "desc" ? { field: sortRaw!.slice(0, cut), dir } : null;
  const filters = p.getAll("f").flatMap((raw): ColumnFilter[] => {
    const [field, operator, ...rest] = raw.split("|");
    return field && operator ? [{ field, operator, value: rest.join("|") }] : [];
  });
  return {
    sort,
    q: p.get("q") ?? "",
    presets: (p.get("preset") ?? "").split(",").filter(isPresetId),
    filters,
  };
}
