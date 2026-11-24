import { ThemeProvider, createTheme } from "@mui/material/styles";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { RunStore, StoreProvider } from "@/store";
import { createAppTheme } from "@/theme";
import type { RunView } from "@/types/run-view";
import { loadToyRun } from "./fixture";

/** The app theme, with DataGrid virtualisation off because jsdom has no layout to measure. */
const testTheme = createTheme(createAppTheme("light"), {
  components: { MuiDataGrid: { defaultProps: { disableVirtualization: true } } },
});

/** Render `ui` inside the app theme and a store already holding `run` (default: the toy run). */
export function renderWithRun(ui: ReactElement, run: RunView = loadToyRun()) {
  const store = new RunStore();
  store.setRun(run);
  return render(
    <ThemeProvider theme={testTheme}>
      <StoreProvider store={store}>{ui}</StoreProvider>
    </ThemeProvider>,
  );
}
