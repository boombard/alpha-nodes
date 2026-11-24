/** Compact label/value layout shared by the summary, verdict and review cards. */
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";

/** One labelled value; `testId` marks the value element for tests. */
export interface Fact {
  label: string;
  value: ReactNode;
  testId?: string;
}

/** A compact wrapping grid of labelled values. */
export function Facts({ facts }: { facts: Fact[] }) {
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 1.5 }}>
      {facts.map((f) => (
        <Box key={f.label}>
          <Typography variant="caption" color="text.secondary" component="div">{f.label}</Typography>
          <Typography variant="body2" component="div" data-testid={f.testId}>{f.value}</Typography>
        </Box>
      ))}
    </Box>
  );
}
