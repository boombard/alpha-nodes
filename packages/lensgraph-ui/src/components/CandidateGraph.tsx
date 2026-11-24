/** Collapsible "Graph" section of the candidate page: this candidate's nodes plus shared ones. */
import ExpandMore from "@mui/icons-material/ExpandMore";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Typography from "@mui/material/Typography";
import { useMemo } from "react";
import { buildCandidateGraph } from "../graph/model";
import { useRun } from "../store";
import { FlowCanvas } from "./FlowCanvas";

/** Collapsed by default; the canvas is only mounted while expanded. */
export function CandidateGraph({ id }: { id: string }) {
  const run = useRun();
  return (
    <Accordion variant="outlined" disableGutters slotProps={{ transition: { unmountOnExit: true } }}>
      <AccordionSummary expandIcon={<ExpandMore />}>
        <Typography variant="h6" component="h2">Graph</Typography>
      </AccordionSummary>
      <AccordionDetails>
        <GraphBody id={id} run={run} />
      </AccordionDetails>
    </Accordion>
  );
}

function GraphBody({ id, run }: { id: string; run: ReturnType<typeof useRun> }) {
  const { nodes, edges } = useMemo(() => buildCandidateGraph(run, id), [run, id]);
  return <FlowCanvas nodes={nodes} edges={edges} height={420} />;
}
