import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithRun } from "../helpers/render";
import { loadToyRun } from "../helpers/fixture";
import { SummaryPage } from "@/pages/Summary";
import { orderedCandidateIds } from "@/listOrder";
import { EMPTY_LIST, listToQuery } from "@/listState";
import { makeScaleRun } from "../helpers/scale";

function rowIds(): string[] {
  const rows = within(screen.getByRole("grid", { name: "Candidates" })).getAllByRole("row");
  return rows.slice(1).map((r) => within(r).getAllByRole("gridcell")[0].textContent ?? "");
}

test("lists three candidate rows and S3 has no overall", () => {
  renderWithRun(<SummaryPage />);
  expect(rowIds()).toEqual(["S1", "S2", "S3"]);
  const s3 = screen.getByRole("row", { name: /S3/ });
  expect(within(s3).getByTestId("overall")).toHaveTextContent("—");
  const s1 = screen.getByRole("row", { name: /S1/ });
  expect(within(s1).getByTestId("overall")).toHaveTextContent("0.41");
});

test("sorting by evidence share reorders rows and is kept in the URL", async () => {
  renderWithRun(<SummaryPage />);
  await userEvent.click(screen.getByRole("columnheader", { name: /evidence share/i }));
  await waitFor(() => expect(rowIds()).toEqual(["S3", "S2", "S1"]));
  expect(window.location.hash).toContain("sort=share%3Aasc");
  await userEvent.click(screen.getByRole("columnheader", { name: /evidence share/i }));
  await waitFor(() => expect(rowIds()).toEqual(["S1", "S2", "S3"]));
  expect(window.location.hash).toContain("sort=share%3Adesc");
});

test("cost is 'unknown' when null and a number otherwise", () => {
  const run = loadToyRun();
  const { unmount } = renderWithRun(<SummaryPage />, run);
  expect(screen.getByTestId("cost")).toHaveTextContent("unknown");
  unmount();
  run.summary.llm_cost_usd = 0.0123;
  renderWithRun(<SummaryPage />, run);
  expect(screen.getByTestId("cost")).toHaveTextContent("$0.0123");
});

test("review flags show as an integer count", () => {
  const run = loadToyRun();
  run.candidates[0].record.review!.flags = [
    { severity: "warn", code: "thin", text: "t", cites: [] },
    { severity: "info", code: "x", text: "t", cites: [] },
  ];
  renderWithRun(<SummaryPage />, run);
  const s1 = screen.getByRole("row", { name: /S1/ });
  expect(within(s1).getByTestId("flags")).toHaveTextContent(/^2$/);
});

test("rows with no value sort last in both directions", async () => {
  renderWithRun(<SummaryPage />);
  const header = screen.getByRole("columnheader", { name: /overall/i });
  await userEvent.click(header);
  await waitFor(() => expect(rowIds()).toEqual(["S2", "S1", "S3"]));
  await userEvent.click(header);
  await waitFor(() => expect(rowIds()).toEqual(["S1", "S2", "S3"]));
});

test("clicking a candidate row opens its page", async () => {
  renderWithRun(<SummaryPage />);
  await userEvent.click(within(screen.getByRole("row", { name: /S2/ })).getAllByRole("gridcell")[1]);
  expect(window.location.hash).toBe("#/candidate/S2");
});

test("list state in the URL is restored on load", () => {
  window.location.hash = "#/?sort=share:asc";
  renderWithRun(<SummaryPage />);
  expect(rowIds()).toEqual(["S3", "S2", "S1"]);
});

test("a preset chip filters the list and is kept in the URL", async () => {
  renderWithRun(<SummaryPage />);
  await userEvent.click(screen.getByRole("button", { name: "Failures" }));
  await waitFor(() => expect(rowIds()).toEqual(["S3"]));
  expect(window.location.hash).toContain("preset=failures");
  await userEvent.click(screen.getByRole("button", { name: "Failures" }));
  await waitFor(() => expect(rowIds()).toEqual(["S1", "S2", "S3"]));
});

test("quick search filters rows and is kept in the URL", async () => {
  renderWithRun(<SummaryPage />);
  await userEvent.click(screen.getByRole("button", { name: /search/i }));
  await userEvent.type(screen.getByRole("searchbox"), "S2");
  await waitFor(() => expect(rowIds()).toEqual(["S2"]));
  expect(window.location.hash).toContain("q=S2");
});

test("the footer shows the row count", () => {
  renderWithRun(<SummaryPage />);
  expect(screen.getByText(/1–3 of 3/)).toBeInTheDocument();
});

test("at 150 candidates the grid shows the first page in exactly the shared order", () => {
  const run = makeScaleRun(150);
  const state = { ...EMPTY_LIST, sort: { field: "share", dir: "desc" as const }, presets: ["thin" as const] };
  window.location.hash = `#/?${listToQuery(state)}`;
  renderWithRun(<SummaryPage />, run);
  const ids = orderedCandidateIds(run, state);
  expect(ids.length).toBeLessThan(150);
  expect(rowIds()).toEqual(ids.slice(0, 100));
  expect(screen.getByText(new RegExp(`of ${ids.length}`))).toBeInTheDocument();
});
