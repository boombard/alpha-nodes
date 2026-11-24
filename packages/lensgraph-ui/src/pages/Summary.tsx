/**
 * Run summary page: headline numbers and the candidate list, the app's main navigation. The list
 * (presets, quick search, column filters, sort) lives in the hash URL; the grid shows exactly the
 * order `orderedCandidates` computes, which Previous/Next on candidate pages also walks.
 */
import Chip from "@mui/material/Chip";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { GridColDef, GridFilterModel, GridSortModel } from "@mui/x-data-grid";
import { useMemo } from "react";
import { cellText, columnSpecs } from "../candidateColumns";
import { DataTable } from "../components/DataTable";
import { Facts } from "../components/Facts";
import { fmtCost, fmtDuration } from "../format";
import { orderedCandidates } from "../listOrder";
import type { ListState } from "../listState";
import { PRESETS, type PresetId } from "../presets";
import { candidateHref, replaceHash, routeList, summaryHref, useRoute } from "../router";
import { useRun } from "../store";
import type { CandidateView } from "../types/run-view";

/** The run summary, preset chips and the candidate grid. */
export function SummaryPage() {
  const run = useRun();
  const list = routeList(useRoute());
  const { summary } = run;
  const specs = useMemo(() => columnSpecs(run), [run]);
  const rows = useMemo(() => orderedCandidates(run, list), [run, list]);

  const update = (next: Partial<ListState>) => replaceHash(summaryHref({ ...list, ...next }));
  const togglePreset = (id: PresetId) =>
    update({ presets: list.presets.includes(id) ? list.presets.filter((p) => p !== id) : [...list.presets, id] });

  const columns: GridColDef<CandidateView>[] = specs.map((spec) => ({
    field: spec.field,
    headerName: spec.headerName,
    type: spec.type,
    flex: 1,
    minWidth: spec.field === "id" ? 110 : 100,
    valueGetter: (_v, row) => spec.value(row),
    renderCell: ({ row }) =>
      spec.field === "id" ? (
        <Link href={candidateHref(row.id, list)}>{row.id}</Link>
      ) : (
        <span data-testid={spec.field}>{cellText(spec, row)}</span>
      ),
  }));

  const sortModel: GridSortModel = list.sort ? [{ field: list.sort.field, sort: list.sort.dir }] : [];
  const filterModel: GridFilterModel = {
    items: list.filters.map((f, i) => ({ id: i, field: f.field, operator: f.operator, value: f.value === "" ? undefined : f.value })),
    quickFilterValues: list.q.split(/\s+/).filter(Boolean),
  };

  return (
    <Stack spacing={2}>
      <Typography variant="h5" component="h1">Run {summary.run_id}</Typography>
      <Facts
        facts={[
          { label: "Status", value: summary.status, testId: "status" },
          { label: "Started", value: summary.started_at ?? "—" },
          { label: "Duration", value: fmtDuration(summary.started_at, summary.finished_at) },
          { label: "Nodes", value: Object.entries(summary.node_counts).map(([k, v]) => `${v} ${k}`).join(", ") || "—" },
          { label: "Cache hits", value: summary.cache_hits },
          { label: "LLM tokens", value: `${summary.llm_input_tokens} in / ${summary.llm_output_tokens} out` },
          { label: "LLM cost", value: fmtCost(summary.llm_cost_usd), testId: "cost" },
        ]}
      />
      <Typography variant="h6" component="h2">Candidates</Typography>
      <Stack direction="row" spacing={1} aria-label="Preset filters">
        {PRESETS.map((p) => (
          <Chip
            key={p.id}
            label={p.label}
            color={list.presets.includes(p.id) ? "primary" : "default"}
            variant={list.presets.includes(p.id) ? "filled" : "outlined"}
            onClick={() => togglePreset(p.id)}
          />
        ))}
      </Stack>
      <DataTable
        label="Candidates"
        columns={columns}
        rows={rows}
        footer
        maxHeight={640}
        showToolbar
        sortingMode="server"
        filterMode="server"
        sortModel={sortModel}
        onSortModelChange={(m) => update({ sort: m[0]?.sort ? { field: m[0].field, dir: m[0].sort } : null })}
        filterModel={filterModel}
        onFilterModelChange={(m) =>
          update({
            q: (m.quickFilterValues ?? []).join(" "),
            filters: m.items.map((i) => ({
              field: i.field,
              operator: i.operator,
              value: i.value == null ? "" : Array.isArray(i.value) ? JSON.stringify(i.value) : String(i.value),
            })),
          })
        }
        onRowClick={({ row }) => { window.location.hash = candidateHref(row.id, list); }}
      />
    </Stack>
  );
}

