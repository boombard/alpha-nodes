/** Entry point: load the run from the picked `DataSource` into the store and render the themed app. */
import CssBaseline from "@mui/material/CssBaseline";
import { ThemeProvider } from "@mui/material/styles";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { pickSource } from "./data/source";
import { RunStore, StoreProvider } from "./store";
import { useAppTheme } from "./theme";

const store = new RunStore();
void store.load(pickSource());

function Root() {
  return (
    <ThemeProvider theme={useAppTheme()}>
      <CssBaseline />
      <StoreProvider store={store}><App /></StoreProvider>
    </ThemeProvider>
  );
}

createRoot(document.getElementById("root")!).render(<Root />);
