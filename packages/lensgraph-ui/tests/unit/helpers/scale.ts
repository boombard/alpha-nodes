import type { CandidateView, NodeKey, RunView } from "@/types/run-view";
import { loadToyRun } from "./fixture";

/** Zero-padded id of the i-th synthetic candidate: C001, C002, ... */
export function scaleId(i: number): string {
  return `C${String(i + 1).padStart(4, "0")}`;
}

/**
 * A synthetic RunView with `n` candidates, built in memory from the toy fixture's S1/S2/S3
 * (cycled) with varied ids and numbers; the plan is scaled to match. No Python, no new fixture.
 *
 * Deterministic variation, by index i: overall_stance, direction, evidence_share (i % 10 / 10),
 * agreement (1.0 for every 11th), a review flag on every 7th, and a failed node on every 3rd
 * S3-derived candidate (S3 is the fixture's failing candidate; its overall stance stays null).
 */
export function makeScaleRun(n: number): RunView {
  const base = loadToyRun();
  const templates = ["S1", "S2", "S3"].map((id) => base.candidates.find((c) => c.id === id)!);
  const rename = (k: NodeKey, from: string, to: string): NodeKey =>
    k.candidate === from ? { ...k, candidate: to } : k;

  const candidates: CandidateView[] = [];
  const nodes = base.plan.nodes.filter((nd) => nd.key.candidate == null);
  const edges = base.plan.edges.filter((e) => e.source.candidate == null && e.target.candidate == null);

  for (let i = 0; i < n; i++) {
    const t = templates[i % 3];
    const id = scaleId(i);
    const c = structuredClone(t);
    c.id = id;
    const d = c.record.dossier;
    d.candidate.id = id;
    if (d.overall_stance != null) d.overall_stance = ((i * 37) % 100) / 100;
    if (d.direction != null) d.direction = ((i * 17) % 100) / 100;
    d.evidence_share = (i % 10) / 10;
    d.agreement = d.agreement == null ? null : i % 11 === 0 ? 1.0 : ((i * 13) % 100) / 100;
    if (i % 7 === 0 && c.record.review) {
      c.record.review.flags = [{ severity: "warn", code: "thin_evidence", text: "thin", cites: [] }];
    }
    if (t.id === "S3" && i % 2 === 0) c.node_status = { ...c.node_status, assay_clean: "ok", growth_rate: "ok" };
    candidates.push(c);

    nodes.push(...base.plan.nodes.filter((nd) => nd.key.candidate === t.id)
      .map((nd) => ({ ...nd, key: rename(nd.key, t.id, id) })));
    edges.push(...base.plan.edges
      .filter((e) => e.source.candidate === t.id || e.target.candidate === t.id)
      .map((e) => ({ ...e, source: rename(e.source, t.id, id), target: rename(e.target, t.id, id) })));
  }
  return { ...base, candidates, plan: { nodes, edges } };
}
