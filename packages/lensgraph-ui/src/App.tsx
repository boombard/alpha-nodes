/** The run view app shell: app bar, tab navigation, hash routing and the loaded/loading/error states. */
import Alert from "@mui/material/Alert";
import AppBar from "@mui/material/AppBar";
import Autocomplete, { createFilterOptions } from "@mui/material/Autocomplete";
import ErrorOutlined from "@mui/icons-material/ErrorOutlined";
import FlagOutlined from "@mui/icons-material/FlagOutlined";
import Box from "@mui/material/Box";
import Container from "@mui/material/Container";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import TextField from "@mui/material/TextField";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import { fmt } from "./format";
import { hasFailures, reviewFlagCount } from "./presets";
import { candidateHref, routeList, summaryHref, useRoute, type Route } from "./router";
import { useStoreState } from "./store";
import { useMemo } from "react";
import { CandidatePage } from "./pages/Candidate";
import { PlanGraphPage } from "./pages/PlanGraph";
import { SummaryPage } from "./pages/Summary";

/** The tab value for a route (false on a candidate page: no tab is selected). */
function tabValue(route: Route): string | false {
  return route.page === "graph" ? "#/graph" : route.page === "summary" ? "#/" : false;
}

const jumpFilter = createFilterOptions<string>({ limit: 100 });

/** Secondary "jump to id" picker; the summary table is the main navigation. */
function CandidateJump({ route }: { route: Route }) {
  const { run } = useStoreState();
  const byId = useMemo(() => new Map((run?.candidates ?? []).map((c) => [c.id, c])), [run]);
  const list = routeList(route);
  return (
    <Autocomplete
      size="small"
      sx={{ width: 260 }}
      options={[...byId.keys()]}
      filterOptions={jumpFilter}
      value={route.page === "candidate" ? route.id : null}
      onChange={(_e, id) => { if (id) window.location.hash = candidateHref(id, list); }}
      renderInput={(params) => <TextField {...params} label="Jump to candidate" />}
      renderOption={(props, id) => {
        const c = byId.get(id)!;
        const { key, ...rest } = props as typeof props & { key: string };
        return (
          <Box component="li" key={key} {...rest} sx={{ display: "flex", gap: 1 }}>
            <span>{id}</span>
            <Typography variant="caption" color="text.secondary" sx={{ flexGrow: 1 }}>{fmt(c.record.dossier.overall_stance)}</Typography>
            {hasFailures(c) && <ErrorOutlined fontSize="small" color="error" titleAccess="has failures" aria-label="has failures" />}
            {reviewFlagCount(c) > 0 && <FlagOutlined fontSize="small" color="warning" titleAccess="has review flags" aria-label="has review flags" />}
          </Box>
        );
      }}
    />
  );
}

/** Root component; the store and theme must already be provided. */
export function App() {
  const { run, error } = useStoreState();
  const route = useRoute();
  if (error) return <Alert severity="error">Could not load the run: {error}</Alert>;
  if (!run) return <Typography sx={{ p: 2 }}>Loading…</Typography>;
  return (
    <>
      <AppBar position="static" color="default" enableColorOnDark>
        <Toolbar variant="dense">
          <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>Run {run.summary.run_id}</Typography>
          <CandidateJump route={route} />
        </Toolbar>
        <Tabs value={tabValue(route)} variant="scrollable" scrollButtons="auto" aria-label="Pages">
          <Tab label="Summary" value="#/" component="a" href={summaryHref()} />
          <Tab label="Plan graph" value="#/graph" component="a" href="#/graph" />
        </Tabs>
      </AppBar>
      <Container maxWidth="xl" component="main">
        <Box sx={{ py: 2 }}>
          {route.page === "summary" && <SummaryPage />}
          {route.page === "graph" && <PlanGraphPage />}
          {route.page === "candidate" && <CandidatePage id={route.id} />}
        </Box>
      </Container>
    </>
  );
}
