/** React Flow node cards for the two plan-graph levels. Every card has Handles so edges attach. */
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import type { Theme } from "@mui/material/styles";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { statusColor } from "../theme";
import { CANDIDATE_NODE, RUN_NODE, STATUS_ORDER, type InstanceNodeData, type RunNodeData } from "./model";

const HANDLE_STYLE = { opacity: 0, pointerEvents: "none" } as const;

function Handles() {
  // Handles are what React Flow attaches edges to; without them no edge is drawn.
  return (
    <>
      <Handle type="target" position={Position.Left} isConnectable={false} style={HANDLE_STYLE} />
      <Handle type="source" position={Position.Right} isConnectable={false} style={HANDLE_STYLE} />
    </>
  );
}

const kindColor = (kind: string) => (t: Theme) =>
  kind === "reviewer" ? t.palette.secondary.main : kind === "aggregator" ? t.palette.primary.main : t.palette.divider;

/** "97 ok · 3 failed": the non-zero statuses in display order. */
export function statusMixText(counts: Record<string, number>): string {
  const keys = [...STATUS_ORDER, ...Object.keys(counts).filter((k) => !STATUS_ORDER.includes(k))];
  return keys.filter((k) => counts[k]).map((k) => `${counts[k]} ${k}`).join(" · ");
}

/** A thin stacked bar of the status mix in theme status colours. */
export function StatusBar({ counts }: { counts: Record<string, number> }) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1;
  return (
    <Box role="img" aria-label={`Status mix: ${statusMixText(counts)}`} sx={{ display: "flex", height: 6, borderRadius: 3, overflow: "hidden", mt: 0.5 }}>
      {STATUS_ORDER.filter((s) => counts[s]).map((s) => (
        <Box key={s} sx={{ width: `${(counts[s] / total) * 100}%`, bgcolor: (t) => statusColor(t, s) }} />
      ))}
    </Box>
  );
}

/** Run-level node: node name, kind, status mix and bar; shared nodes marked. */
export function RunNodeCard({ data }: NodeProps<Node<RunNodeData>>) {
  return (
    <Box sx={{ px: 1, py: 0.5, fontSize: 12, borderRadius: 1, width: RUN_NODE.width, height: RUN_NODE.height, boxSizing: "border-box",
      bgcolor: "background.paper", border: 2, borderColor: kindColor(data.kind), cursor: "pointer" }}>
      <Handles />
      <strong>{data.name}</strong>
      <Typography variant="caption" color="text.secondary" component="div">
        {data.kind}{data.shared ? " · shared" : ""}
      </Typography>
      <Typography variant="caption" component="div">{statusMixText(data.counts)}</Typography>
      <StatusBar counts={data.counts} />
    </Box>
  );
}

/** Candidate-level node: one instance, with a left edge coloured by its status. */
export function InstanceNodeCard({ data }: NodeProps<Node<InstanceNodeData>>) {
  return (
    <Box sx={{ px: 1, py: 0.5, fontSize: 12, borderRadius: 1, width: CANDIDATE_NODE.width, height: CANDIDATE_NODE.height,
      boxSizing: "border-box", bgcolor: "background.paper", border: 2, borderColor: kindColor(data.kind),
      borderLeftWidth: 8, borderLeftColor: (t) => statusColor(t, data.status),
      borderStyle: data.kind === "lens" ? "double" : "solid" }}>
      <Handles />
      <strong>{data.name}</strong>
      <Typography variant="caption" color="text.secondary" component="div">
        {data.kind} · {data.status}{data.shared ? " · shared" : ""}
      </Typography>
    </Box>
  );
}

/** Node types for `ReactFlow`. */
export const nodeTypes = { run: RunNodeCard, instance: InstanceNodeCard };
