import { buildCandidateGraph, buildRunGraph } from "@/graph/model";
import { loadToyRun } from "../helpers/fixture";
import { makeScaleRun } from "../helpers/scale";

const N = 150;

test("the run-level graph has one node per node name", () => {
  const run = makeScaleRun(N);
  const { nodes } = buildRunGraph(run);
  const names = new Set(run.plan.nodes.map((n) => n.key.name));
  expect(nodes).toHaveLength(names.size);
  expect(new Set(nodes.map((n) => n.id))).toEqual(names);
});

test("status counts of per-candidate nodes sum to the candidate count; shared nodes are marked", () => {
  const run = makeScaleRun(N);
  const { nodes } = buildRunGraph(run);
  for (const node of nodes) {
    const total = Object.values(node.data.counts).reduce((a, b) => a + b, 0);
    if (node.data.shared) expect(total).toBe(1);
    else expect(total).toBe(N);
  }
  expect(nodes.filter((n) => n.data.shared).map((n) => n.id)).toEqual(["reference_panel"]);
  const clean = nodes.find((n) => n.id === "assay_clean")!;
  expect(clean.data.counts.failed).toBeGreaterThan(0);
  expect(clean.data.byStatus.failed.length).toBe(clean.data.counts.failed);
});

test("run-level edges are deduplicated by node name and dashed only if optional", () => {
  const run = makeScaleRun(N);
  const { edges } = buildRunGraph(run);
  const pairs = new Set(run.plan.edges.map((e) => `${e.source.name}->${e.target.name}`));
  expect(edges).toHaveLength(pairs.size);
  const optional = new Set(run.plan.edges.filter((e) => e.optional).map((e) => `${e.source.name}->${e.target.name}`));
  expect(edges.filter((e) => e.style?.strokeDasharray)).toHaveLength(optional.size);
});

test("the run-level graph for 1000 candidates builds well under a second", () => {
  const run = makeScaleRun(1000);
  const start = performance.now();
  buildRunGraph(run);
  expect(performance.now() - start).toBeLessThan(1000);
});

test("the candidate graph has this candidate's nodes plus shared ones, coloured by its status", () => {
  const run = loadToyRun();
  const { nodes, edges } = buildCandidateGraph(run, "S3");
  const expected = run.plan.nodes.filter((n) => n.key.candidate === "S3" || n.key.candidate == null);
  expect(nodes).toHaveLength(expected.length);
  expect(nodes.find((n) => n.data.name === "assay_clean")!.data.status).toBe("failed");
  expect(nodes.find((n) => n.id === "review")!.className).toContain("kind-reviewer");
  const ids = new Set(nodes.map((n) => n.id));
  expect(edges.length).toBeGreaterThan(0);
  expect(edges.every((e) => ids.has(e.source) && ids.has(e.target))).toBe(true);
  expect(edges.filter((e) => e.style?.strokeDasharray).length).toBe(
    run.plan.edges.filter((e) => e.optional && ids.has(e.source.name) && ids.has(e.target.name)
      && (e.source.candidate ?? "S3") === "S3" && (e.target.candidate ?? "S3") === "S3").length,
  );
});

test("layout gives every node its own position, left-to-right along edges", () => {
  const run = loadToyRun();
  for (const { nodes, edges } of [buildRunGraph(run), buildCandidateGraph(run, "S1")]) {
    const at = new Map(nodes.map((n) => [n.id, n.position]));
    expect(new Set([...at.values()].map((p) => `${p.x},${p.y}`)).size).toBe(nodes.length);
    for (const e of edges) expect(at.get(e.source)!.x).toBeLessThan(at.get(e.target)!.x);
  }
});
