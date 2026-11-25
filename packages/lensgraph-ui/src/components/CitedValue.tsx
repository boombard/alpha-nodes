/**
 * Drill-down from a claim's cite to the stored value it cites. Rendering is by `CitedView.kind`
 * through `renderers`: charts (`chart` kind) and flat models (a field/value table) are built in;
 * anything else is a table or JSON.
 */
import Box from "@mui/material/Box";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";
import { DataTable } from "./DataTable";
import { LineChartView } from "./LineChartView";
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

/** True for a plain object whose values are all scalars (or null): fit for a field/value table. */
function isFlat(value: unknown): value is Record<string, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    Object.values(value).every((v) => v === null || typeof v !== "object")
  );
}

/** A flat model as a two-column field/value table. */
function FieldTable({ cited, fields }: { cited: CitedView; fields: Record<string, unknown> }) {
  return (
    <Table size="small" aria-label={`Fields of ${cited.cite}`}>
      <TableBody>
        {Object.entries(fields).map(([k, v]) => (
          <TableRow key={k}>
            <TableCell component="th" scope="row">
              {k}
            </TableCell>
            <TableCell>{v == null ? "—" : String(v)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

/** Renderers by `CitedView.kind`; unlisted kinds use the default view. */
export const renderers: Partial<Record<CitedView["kind"], CitedRenderer>> = {
  chart: (cited) => <LineChartView chart={cited.chart!} />,
};

/** Render a cited value with its kind's renderer, else as a table or JSON. */
export function CitedValue({ cited }: { cited: CitedView }) {
  const custom = renderers[cited.kind];
  if (custom) return <>{custom(cited)}</>;
  if (cited.table) return <TableView cited={cited} />;
  if (cited.kind === "model" && isFlat(cited.json_value)) {
    return <FieldTable cited={cited} fields={cited.json_value} />;
  }
  return <JsonView cited={cited} />;
}
