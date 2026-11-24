/**
 * Run-level plan graph (the Plan graph tab): one node per node name with its status mix over all
 * candidates; clicking a node lists the candidates per status. See documentation/design/core.md,
 * Reporting: run view.
 */
import Chip from "@mui/material/Chip";
import Drawer from "@mui/material/Drawer";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useMemo, useState } from "react";
import { FlowCanvas } from "../components/FlowCanvas";
import { STATUS_ORDER, buildRunGraph } from "../graph/model";
import { candidateHref } from "../router";
import { useRun } from "../store";

/** The run-level graph page. */
export function PlanGraphPage() {
  const run = useRun();
  const { nodes, edges } = useMemo(() => buildRunGraph(run), [run]);
  const [selected, setSelected] = useState<string | null>(null);
  const node = nodes.find((n) => n.id === selected);
  return (
    <Stack spacing={2}>
      <Typography variant="h5" component="h1">Plan graph</Typography>
      <Typography variant="body2" color="text.secondary">
        One node per node name, with its status across all candidates. Click a node to see which candidates are in each status.
      </Typography>
      <FlowCanvas nodes={nodes} edges={edges} height={560} onNodeClick={setSelected} />
      <Drawer anchor="right" open={!!node} onClose={() => setSelected(null)} role="dialog" aria-label={node ? `Node ${node.data.name}` : undefined}>
        {node && (
          <Stack spacing={1.5} sx={{ width: 360, p: 2 }}>
            <Typography variant="h6">{node.data.name}</Typography>
            <Typography variant="caption" color="text.secondary">{node.data.kind}{node.data.shared ? " · shared by all candidates" : ""}</Typography>
            {node.data.shared ? (
              <Typography variant="body2">Status: {Object.keys(node.data.counts)[0]}</Typography>
            ) : (
              STATUS_ORDER.filter((s) => node.data.byStatus[s]).map((s) => (
                <div key={s}>
                  <Typography variant="subtitle2">{s} ({node.data.byStatus[s].length})</Typography>
                  <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", gap: 0.5 }}>
                    {node.data.byStatus[s].map((id) => (
                      <Chip key={id} size="small" component="a" clickable href={candidateHref(id)} label={id} />
                    ))}
                  </Stack>
                </div>
              ))
            )}
          </Stack>
        )}
      </Drawer>
    </Stack>
  );
}
