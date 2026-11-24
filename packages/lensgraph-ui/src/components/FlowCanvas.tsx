/** The React Flow canvas shared by both graph levels. */
import Box from "@mui/material/Box";
import { useTheme } from "@mui/material/styles";
import { Background, Controls, ReactFlow, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { nodeTypes } from "../graph/nodes";

/** Pan/zoomable, read-only graph. `onNodeClick` receives the clicked node's id. */
export function FlowCanvas({
  nodes,
  edges,
  height = 520,
  onNodeClick,
}: {
  nodes: Node[];
  edges: Edge[];
  height?: number;
  onNodeClick?: (id: string) => void;
}) {
  const theme = useTheme();
  return (
    <Box sx={{ height, border: 1, borderColor: "divider" }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        nodesDraggable={false}
        nodesConnectable={false}
        onNodeClick={onNodeClick ? (_e, node) => onNodeClick(node.id) : undefined}
        proOptions={{ hideAttribution: true }}
      >
        <Background color={theme.palette.divider} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </Box>
  );
}
