/**
 * Preset list filters ("Failures", "Review flags", ...) and the thresholds behind them, in one
 * place. Presets combine with AND. See documentation/design/core.md, Reporting: run view.
 */
import type { CandidateView } from "./types/run-view";

/** "Contested" presets: candidates whose lenses' agreement is at least this. */
export const CONTESTED_AGREEMENT_MIN = 1.0;
/** "Thin evidence" preset: candidates whose evidence share is below this. */
export const THIN_EVIDENCE_SHARE_MAX = 0.5;

/** Ids of the presets, as used in the URL (`preset=failures,flags`). */
export type PresetId = "failures" | "flags" | "contested" | "thin";

/** True if any lens failed or any node of the candidate failed. */
export function hasFailures(c: CandidateView): boolean {
  return (
    Object.values(c.record.dossier.coverage).includes("failed") ||
    Object.values(c.node_status).includes("failed")
  );
}

/** Number of flags raised by the candidate's review. */
export function reviewFlagCount(c: CandidateView): number {
  return c.record.review?.flags?.length ?? 0;
}

/** A preset: chip label and the predicate a candidate must satisfy. */
export interface Preset {
  id: PresetId;
  label: string;
  matches: (c: CandidateView) => boolean;
}

/** All presets, in chip order. */
export const PRESETS: Preset[] = [
  { id: "failures", label: "Failures", matches: hasFailures },
  { id: "flags", label: "Review flags", matches: (c) => reviewFlagCount(c) > 0 },
  {
    id: "contested",
    label: "Contested",
    matches: (c) => (c.record.dossier.agreement ?? -Infinity) >= CONTESTED_AGREEMENT_MIN,
  },
  {
    id: "thin",
    label: "Thin evidence",
    matches: (c) => (c.record.dossier.evidence_share ?? Infinity) < THIN_EVIDENCE_SHARE_MAX,
  },
];

/** Type guard for ids read from the URL. */
export function isPresetId(s: string): s is PresetId {
  return PRESETS.some((p) => p.id === s);
}
