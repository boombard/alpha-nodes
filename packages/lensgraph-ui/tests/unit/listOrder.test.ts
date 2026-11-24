import { listNeighbours, orderedCandidateIds } from "@/listOrder";
import { EMPTY_LIST, listFromQuery, listToQuery, type ListState } from "@/listState";
import { CONTESTED_AGREEMENT_MIN, PRESETS, THIN_EVIDENCE_SHARE_MAX } from "@/presets";
import { makeScaleRun } from "./helpers/scale";
import { loadToyRun } from "./helpers/fixture";

const N = 150;
const run = makeScaleRun(N);
const by = (id: string) => run.candidates.find((c) => c.id === id)!;
const state = (p: Partial<ListState>): ListState => ({ ...EMPTY_LIST, ...p });

test("list state round-trips through the URL query", () => {
  const s: ListState = {
    sort: { field: "lens:growth", dir: "desc" },
    q: "S1 foo",
    presets: ["flags", "thin"],
    filters: [{ field: "overall", operator: ">", value: "0.2" }, { field: "id", operator: "contains", value: "a|b" }],
  };
  expect(listFromQuery(listToQuery(s))).toEqual(s);
  expect(listToQuery(EMPTY_LIST)).toBe("");
  expect(listFromQuery("sort=share:desc&q=S1&preset=flags,bogus")).toEqual(
    state({ sort: { field: "share", dir: "desc" }, q: "S1", presets: ["flags"] }),
  );
});

test("no state keeps the run's candidate order", () => {
  expect(orderedCandidateIds(run, EMPTY_LIST)).toEqual(run.candidates.map((c) => c.id));
});

test("sorting is stable and puts missing values last in both directions", () => {
  for (const dir of ["asc", "desc"] as const) {
    const ids = orderedCandidateIds(run, state({ sort: { field: "overall", dir } }));
    const values = ids.map((id) => by(id).record.dossier.overall_stance);
    const firstNull = values.indexOf(null);
    expect(values.slice(firstNull).every((v) => v === null)).toBe(true);
    const present = values.slice(0, firstNull) as number[];
    expect(present).toEqual([...present].sort((a, b) => (dir === "asc" ? a - b : b - a)));
  }
});

test("presets reduce the list by their predicates and combine with AND", () => {
  const ids = (presets: ListState["presets"]) => orderedCandidateIds(run, state({ presets }));
  const failures = ids(["failures"]);
  expect(failures.length).toBeGreaterThan(0);
  for (const id of failures) {
    const c = by(id);
    expect(Object.values(c.node_status).includes("failed") || Object.values(c.record.dossier.coverage).includes("failed")).toBe(true);
  }
  const flags = ids(["flags"]);
  expect(flags.length).toBe(run.candidates.filter((c) => (c.record.review?.flags?.length ?? 0) > 0).length);
  const thin = ids(["thin"]);
  expect(thin.every((id) => by(id).record.dossier.evidence_share! < THIN_EVIDENCE_SHARE_MAX)).toBe(true);
  const contested = ids(["contested"]);
  expect(contested.length).toBeGreaterThan(0);
  expect(contested.every((id) => by(id).record.dossier.agreement! >= CONTESTED_AGREEMENT_MIN)).toBe(true);
  const both = ids(["flags", "thin"]);
  expect(both).toEqual(flags.filter((id) => thin.includes(id)));
  expect(PRESETS.map((p) => p.id)).toEqual(["failures", "flags", "contested", "thin"]);
});

test("quick search matches any cell text, all tokens must match", () => {
  expect(orderedCandidateIds(run, state({ q: "C0007" }))).toEqual(["C0007"]);
  expect(orderedCandidateIds(run, state({ q: "failed" })).length).toBeGreaterThan(0);
  expect(orderedCandidateIds(run, state({ q: "C0007 C0008" }))).toEqual([]);
  expect(orderedCandidateIds(run, state({ q: "zzz" }))).toEqual([]);
});

test("column filters apply string and number operators", () => {
  const some = orderedCandidateIds(run, state({ filters: [{ field: "share", operator: ">=", value: "0.8" }] }));
  expect(some.length).toBeGreaterThan(0);
  expect(some.every((id) => by(id).record.dossier.evidence_share! >= 0.8)).toBe(true);
  expect(orderedCandidateIds(run, state({ filters: [{ field: "id", operator: "startsWith", value: "C001" }] })).length).toBe(10);
  expect(orderedCandidateIds(run, state({ filters: [{ field: "overall", operator: "isEmpty", value: "" }] })).length)
    .toBe(run.candidates.filter((c) => c.record.dossier.overall_stance == null).length);
  expect(orderedCandidateIds(run, state({ filters: [{ field: "share", operator: ">", value: "" }] }))).toHaveLength(N);
});

test("a toy run orders the same way", () => {
  const toy = loadToyRun();
  expect(orderedCandidateIds(toy, state({ sort: { field: "share", dir: "desc" } }))).toEqual(["S1", "S2", "S3"]);
});

test("Previous/Next walk the ordered list and stop at its ends", () => {
  const ids = orderedCandidateIds(run, state({ sort: { field: "share", dir: "desc" }, presets: ["thin"] }));
  expect(ids.length).toBeGreaterThan(5);
  expect(listNeighbours(ids, ids[0])).toEqual({ index: 0, total: ids.length, prev: null, next: ids[1] });
  const walked = [ids[0]];
  for (let n = listNeighbours(ids, ids[0]); n.next; n = listNeighbours(ids, n.next)) walked.push(n.next);
  expect(walked).toEqual(ids);
  expect(listNeighbours(ids, ids.at(-1)!).next).toBeNull();
  expect(listNeighbours(ids, "not-in-list")).toEqual({ index: -1, total: ids.length, prev: null, next: null });
});
