/**
 * The candidate table's columns as plain data (field, type, value accessor), shared by the grid
 * and by `orderedCandidateIds` so both always agree. See documentation/design/core.md, Reporting: run view.
 */
import { fmt } from "./format";
import { reviewFlagCount } from "./presets";
import type { CandidateView, RunView } from "./types/run-view";

/** One table column. `value` is null for a missing value (shown as an em dash, sorted last). */
export interface ColumnSpec {
  field: string;
  headerName: string;
  type: "string" | "number";
  digits: number;
  value: (c: CandidateView) => string | number | null;
}

/** The columns for a run: id, the numeric dossier columns, one status column per lens, review flags. */
export function columnSpecs(view: RunView): ColumnSpec[] {
  const num = (field: string, headerName: string, value: ColumnSpec["value"], digits = 2): ColumnSpec => ({
    field, headerName, type: "number", digits, value,
  });
  const lenses = [...new Set(view.candidates.flatMap((c) => Object.keys(c.record.dossier.coverage)))].sort();
  return [
    { field: "id", headerName: "Candidate", type: "string", digits: 0, value: (c) => c.id },
    num("overall", "Overall", (c) => c.record.dossier.overall_stance),
    num("direction", "Direction", (c) => c.record.dossier.direction ?? null),
    num("share", "Evidence share", (c) => c.record.dossier.evidence_share ?? null),
    num("agreement", "Agreement", (c) => c.record.dossier.agreement),
    ...lenses.map((lens): ColumnSpec => ({
      field: `lens:${lens}`,
      headerName: lens,
      type: "string",
      digits: 0,
      value: (c) => c.record.dossier.coverage[lens] ?? null,
    })),
    num("flags", "Review flags", reviewFlagCount, 0),
  ];
}

/** The text a cell shows (and quick search matches against). */
export function cellText(spec: ColumnSpec, c: CandidateView): string {
  const v = spec.value(c);
  if (v == null) return "—";
  return typeof v === "number" ? fmt(v, spec.digits) : v;
}
