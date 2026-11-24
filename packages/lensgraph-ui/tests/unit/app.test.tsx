import { ThemeProvider } from "@mui/material/styles";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "@/App";
import { RunStore, StoreProvider } from "@/store";
import { createAppTheme } from "@/theme";
import { loadToyRun } from "./helpers/fixture";

function renderApp() {
  const store = new RunStore();
  store.setRun(loadToyRun());
  return render(
    <ThemeProvider theme={createAppTheme("light")}>
      <StoreProvider store={store}><App /></StoreProvider>
    </ThemeProvider>,
  );
}

test("navigation has Summary and Plan graph tabs and no per-candidate tabs", () => {
  renderApp();
  const tabs = within(screen.getByRole("tablist")).getAllByRole("tab");
  expect(tabs.map((t) => t.textContent)).toEqual(["Summary", "Plan graph"]);
});

test("the candidate picker lists candidate ids and opens the chosen candidate", async () => {
  renderApp();
  await userEvent.click(screen.getByRole("combobox", { name: /candidate/i }));
  const options = screen.getAllByRole("option").map((o) => o.textContent);
  expect(options.map((o) => o?.slice(0, 2))).toEqual(["S1", "S2", "S3"]);
  expect(options[0]).toContain("0.41"); // overall stance
  const s3 = screen.getByRole("option", { name: /S3/ });
  expect(within(s3).getByLabelText("has failures")).toBeInTheDocument();
  expect(within(screen.getByRole("option", { name: /S1/ })).queryByLabelText("has failures")).toBeNull();
  await userEvent.click(screen.getByRole("option", { name: /S3/ }));
  expect(window.location.hash).toBe("#/candidate/S3");
});
