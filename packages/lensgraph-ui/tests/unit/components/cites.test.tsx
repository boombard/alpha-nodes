import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithRun } from "../helpers/render";
import { loadToyRun } from "../helpers/fixture";
import { CandidatePage } from "@/pages/Candidate";

test("a cite link opens the cited value", async () => {
  renderWithRun(<CandidatePage id="S1" />);
  const links = screen.getAllByRole("button", { name: "growth_rate" });
  await userEvent.click(links[0]);
  const dialog = screen.getByRole("dialog", { name: /growth_rate/ });
  expect(within(dialog).getByText(/0\.1244/)).toBeInTheDocument();
});

test("a table cite renders as a table", async () => {
  const run = loadToyRun();
  const id = Object.keys(run.cited)[0];
  run.cited[id] = {
    ...run.cited[id],
    kind: "frame",
    json_value: {},
    table: { columns: ["t", "v"], rows: [[1, 2.5]], total_rows: 9, truncated: true, units: {}, display_rows: null },
  };
  renderWithRun(<CandidatePage id="S1" />, run);
  await userEvent.click(screen.getAllByRole("button", { name: "growth_rate" })[0]);
  const dialog = screen.getByRole("dialog");
  expect(within(dialog).getByRole("columnheader", { name: "v" })).toBeInTheDocument();
  expect(within(dialog).getByText(/1 of 9 rows/)).toBeInTheDocument();
});

test("a null cite shows unresolved", () => {
  const run = loadToyRun();
  const s1 = run.candidates.find((c) => c.id === "S1")!;
  s1.claims[0].cites = { growth_rate: null };
  renderWithRun(<CandidatePage id="S1" />, run);
  expect(screen.getByText("growth_rate (unresolved)")).toBeInTheDocument();
});

