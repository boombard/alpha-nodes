/** A read-only, compact, virtualised MUI X DataGrid (community edition) used for all tables. */
import Box from "@mui/material/Box";
import { DataGrid, type DataGridProps, type GridValidRowModel } from "@mui/x-data-grid";

const ROW_HEIGHT = 36;
const FOOTER_HEIGHT = 52;

/**
 * Compact grid sized to its rows up to `maxHeight`; beyond that it scrolls (rows are virtualised).
 *
 * @param label accessible name of the grid.
 * @param footer show the footer (row count and paging); the community grid pages at 100 rows.
 */
export function DataTable<R extends GridValidRowModel>({
  label,
  maxHeight = 420,
  footer = false,
  ...props
}: Omit<DataGridProps<R>, "density" | "hideFooter"> & { label: string; maxHeight?: number; footer?: boolean }) {
  const content = ((props.rows?.length ?? 0) + 1) * ROW_HEIGHT + 2 + (footer ? FOOTER_HEIGHT : 0);
  return (
    <Box sx={{ height: Math.min(maxHeight, content), width: "100%" }}>
      <DataGrid<R>
        aria-label={label}
        density="compact"
        hideFooter={!footer}
        disableRowSelectionOnClick
        {...props}
      />
    </Box>
  );
}
