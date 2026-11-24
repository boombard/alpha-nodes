/** Cite links: each cite of a claim or flag opens the stored value it cites. */
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import { useState } from "react";
import { useRun } from "../store";
import { CitedValue } from "./CitedValue";

/**
 * A list of cites as chips; a resolved cite opens a dialog with the cited value.
 *
 * @param cites cite -> `CitedView.id`, or null when the cite could not be resolved.
 */
export function Cites({ cites }: { cites: Record<string, string | null> }) {
  const run = useRun();
  const [open, setOpen] = useState<string | null>(null);
  const cited = open ? run.cited[open] : undefined;
  return (
    <>
      <Stack direction="row" spacing={0.5} useFlexGap component="span" sx={{ display: "inline-flex", flexWrap: "wrap" }}>
        {Object.entries(cites).map(([cite, id]) =>
          id && run.cited[id] ? (
            <Chip key={cite} size="small" color="primary" variant="outlined" label={cite} onClick={() => setOpen(id)} />
          ) : (
            <Chip key={cite} size="small" color="warning" variant="outlined" label={`${cite} (unresolved)`} />
          ),
        )}
      </Stack>
      {cited && (
        <Dialog open onClose={() => setOpen(null)} maxWidth="md" fullWidth aria-labelledby="cited-title">
          <DialogTitle id="cited-title">
            {cited.cite} ({cited.kind}, source {cited.source_hash.slice(0, 8)})
          </DialogTitle>
          <DialogContent><CitedValue cited={cited} /></DialogContent>
          <DialogActions><Button onClick={() => setOpen(null)}>Close</Button></DialogActions>
        </Dialog>
      )}
    </>
  );
}
