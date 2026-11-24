/**
 * Drill-down from a claim's cite to the stored value it cites. Rendering is by `CitedView.kind`
 * through `renderers`: the hook where domains register e.g. a price chart in later milestones.
 */
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";
import { DataTable } from "./DataTable";
import type { CitedView } from "../types/run-view";

/** A renderer for one kind of cited value. */
export type CitedRenderer = (cited: CitedView) => ReactNode;

/** A capped table (frames and lists of models) in a read-only grid. */
function TableView({ cited }: { cited: CitedView }) {
  const table = cited.table!;
  const columns = table.columns.map((name, j) => ({
    field: `c${j}`,
    headerName: name,
    flex: 1,
    minWidth: 90,
    sortable: false,
  }));
  const rows = table.rows.map((row, i) => ({
    id: i,
    ...Object.fromEntries(row.map((v, j) => [`c${j}`, v == null ? "—" : String(v)])),
  }));
  return (
    <Box>
      <DataTable label={`Cited table ${cited.cite}`} columns={columns} rows={rows} />
      <Typography variant="caption" color="text.secondary">
        {table.rows.length} of {table.total_rows} rows{table.truncated ? " (truncated: last rows shown)" : ""}
      </Typography>
    </Box>
  );
}

/** Pretty-printed JSON in a monospace block, always as text. */
function JsonView({ cited }: { cited: CitedView }) {
  return (
    <Box component="pre" sx={{ fontFamily: "monospace", fontSize: 12, m: 0, maxHeight: 300, overflow: "auto" }}>
      {JSON.stringify(cited.json_value, null, 2)}
    </Box>
  );
}

/** Domain renderers by `CitedView.kind`; unlisted kinds use the default table/JSON view. */
export const renderers: Partial<Record<CitedView["kind"], CitedRenderer>> = {};

/** Render a cited value with its kind's renderer, else as a table or JSON. */
export function CitedValue({ cited }: { cited: CitedView }) {
  const custom = renderers[cited.kind];
  if (custom) return <>{custom(cited)}</>;
  return cited.table ? <TableView cited={cited} /> : <JsonView cited={cited} />;
}
