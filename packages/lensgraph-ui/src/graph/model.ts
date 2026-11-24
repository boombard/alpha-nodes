/**
 * Pure builders for the two plan-graph levels, laid out with dagre. See
 * documentation/design/core.md, Reporting: run view.
 *
 * Run level: one node per node *name* (edges deduplicated by name) carrying a status mix over
 * all candidates. Candidate level: one candidate's node instances plus the shared nodes.
 */
import dagre from "@dagrejs/dagre";
import type { Edge, Node } from "@xyflow/react";
import type { PlanEdge, PlanNode, RunView } from "../types/run-view";

/** Status display order in mixes and panels. */
export const STATUS_ORDER = ["ok", "recovered", "abstained", "skipped", "failed", "unknown"];

/** Size of a run-level node card. */
export const RUN_NODE = { width: 200, height: 78 };
/** Size of a candidate-level node card. */
export const CANDIDATE_NODE = { width: 170, height: 52 };

/** Data of a run-level node: one node name across all candidates. */
export interface RunNodeData extends Record<string, unknown> {
  name: string;
  kind: string;
  shared: boolean;
  /** Status -> number of candidates (shared nodes: their single status counts 1). */
  counts: Record<string, number>;
  /** Status -> candidate ids, for the node panel (empty for shared nodes). */
  byStatus: Record<string, string[]>;
}

/** Data of a candidate-level node: one node instance. */
export interface InstanceNodeData extends Record<string, unknown> {
  name: string;
  candidate: string | null;
  kind: string;
  status: string;
  shared: boolean;
}

function layout(
  ids: string[],
  links: [string, string][],
  size: { width: number; height: number },
): Map<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 16, ranksep: 60 });
  g.setDefaultEdgeLabel(() => ({}));
  ids.forEach((id) => g.setNode(id, { ...size })); // dagre writes x,y into the label: never share one
  links.forEach(([s, t]) => g.setEdge(s, t));
  dagre.layout(g);
  return new Map(ids.map((id) => {
    const { x, y } = g.node(id);
    return [id, { x: x - size.width / 2, y: y - size.height / 2 }];
  }));
}

const dashed = (optional: boolean) => (optional ? { strokeDasharray: "6 4" } : {});

/** The run-level graph: one node per node name with its status mix, edges deduplicated by name. */
export function buildRunGraph(view: RunView): { nodes: Node<RunNodeData>[]; edges: Edge[] } {
  const info = new Map<string, { kind: string; shared: boolean }>();
  for (const n of view.plan.nodes) {
    if (!info.has(n.key.name)) info.set(n.key.name, { kind: n.kind, shared: n.scope === "shared" });
  }
  const byStatus = new Map<string, Record<string, string[]>>();
  const sharedStatus = new Map<string, string>();
  for (const c of view.candidates) {
    for (const [name, status] of Object.entries(c.node_status)) {
      if (info.get(name)?.shared) {
        if (!sharedStatus.has(name)) sharedStatus.set(name, status);
        continue;
      }
      const groups = byStatus.get(name) ?? {};
      (groups[status] ??= []).push(c.id);
      byStatus.set(name, groups);
    }
  }
  const edgeInfo = new Map<string, { source: string; target: string; optional: boolean }>();
  for (const e of view.plan.edges) {
    const key = `${e.source.name}->${e.target.name}`;
    const prev = edgeInfo.get(key);
    edgeInfo.set(key, { source: e.source.name, target: e.target.name, optional: (prev?.optional ?? true) && e.optional });
  }
  const names = [...info.keys()];
  const pos = layout(names, [...edgeInfo.values()].map((e) => [e.source, e.target]), RUN_NODE);
  const nodes = names.map((name): Node<RunNodeData> => {
    const { kind, shared } = info.get(name)!;
    const groups = shared ? {} : (byStatus.get(name) ?? {});
    const counts = shared
      ? { [sharedStatus.get(name) ?? "unknown"]: 1 }
      : Object.fromEntries(Object.entries(groups).map(([s, ids]) => [s, ids.length]));
    return {
      id: name,
      type: "run",
      position: pos.get(name)!,
      ...RUN_NODE,
      className: `kind-${kind}`,
      data: { name, kind, shared, counts, byStatus: groups },
    };
  });
  const edges = [...edgeInfo.entries()].map(([id, e]): Edge => ({
    id, source: e.source, target: e.target, style: dashed(e.optional),
  }));
  return { nodes, edges };
}

/** Flow id of a node instance within one candidate's graph: its node name. */
function instanceKey(n: PlanNode | PlanEdge["source"]): string {
  return "key" in n ? n.key.name : n.name;
}

/** The candidate-level graph: `candidateId`'s node instances plus shared nodes, coloured by its status. */
export function buildCandidateGraph(
  view: RunView,
  candidateId: string,
): { nodes: Node<InstanceNodeData>[]; edges: Edge[] } {
  const status = view.candidates.find((c) => c.id === candidateId)?.node_status ?? {};
  const own = (c: string | null) => c === null || c === candidateId;
  const planNodes = view.plan.nodes.filter((n) => own(n.key.candidate));
  const planEdges = view.plan.edges.filter((e) => own(e.source.candidate) && own(e.target.candidate));
  const ids = planNodes.map(instanceKey);
  const pos = layout(ids, planEdges.map((e) => [e.source.name, e.target.name]), CANDIDATE_NODE);
  const nodes = planNodes.map((n): Node<InstanceNodeData> => {
    const name = n.key.name;
    const s = status[name] ?? "unknown";
    return {
      id: name,
      type: "instance",
      position: pos.get(name)!,
      ...CANDIDATE_NODE,
      className: `kind-${n.kind} status-${s}`,
      data: { name, candidate: n.key.candidate, kind: n.kind, status: s, shared: n.scope === "shared" },
    };
  });
  const edges = planEdges.map((e): Edge => ({
    id: `${e.source.name}->${e.target.name}:${e.kwarg}`,
    source: e.source.name,
    target: e.target.name,
    style: dashed(e.optional),
  }));
  return { nodes, edges };
}
