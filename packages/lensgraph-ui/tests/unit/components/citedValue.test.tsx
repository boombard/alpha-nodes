import { screen } from "@testing-library/react";
import { renderWithRun } from "../helpers/render";
import { CitedValue } from "@/components/CitedValue";
import type { CitedView } from "@/types/run-view";

const base: CitedView = {
  id: "h:x",
  cite: "x",
  source_hash: "h",
  kind: "model",
  table: null,
  json_value: {},
  display: null,
  chart: null,
};

test("a chart kind cite draws the chart", () => {
  const cited: CitedView = {
    ...base,
    kind: "chart",
    chart: { title: "Prices", x: ["2024-01-01"], series: { AAA: [1] }, y_label: null },
  };
  renderWithRun(<CitedValue cited={cited} />);
  expect(screen.getByText("Prices")).toBeInTheDocument();
  expect(screen.getByText("AAA")).toBeInTheDocument();
});

test("a flat model renders as a field/value table", () => {
  renderWithRun(<CitedValue cited={{ ...base, json_value: { ret: 0.5, name: "n", none: null } }} />);
  expect(screen.getByRole("table", { name: /fields of x/i })).toBeInTheDocument();
  expect(screen.getByText("ret")).toBeInTheDocument();
  expect(screen.getByText("0.5")).toBeInTheDocument();
});

test("a nested model stays a JSON block", () => {
  renderWithRun(<CitedValue cited={{ ...base, json_value: { a: { b: 1 } } }} />);
  expect(screen.queryByRole("table")).toBeNull();
  expect(screen.getByText(/"b": 1/)).toBeInTheDocument();
});

test("a model with display strings shows them instead of raw values", () => {
  const cited = { ...base, json_value: { roe: 0.153, name: "n" }, display: { roe: "15.3%" } };
  renderWithRun(<CitedValue cited={cited} />);
  expect(screen.getByText("15.3%")).toBeInTheDocument();
  expect(screen.queryByText("0.153")).toBeNull();
  expect(screen.getByText("n")).toBeInTheDocument();
});

test("a single cited field shows its display string", () => {
  renderWithRun(<CitedValue cited={{ ...base, kind: "field", cite: "x.roe", json_value: 0.153 as never, display: { roe: "15.3%" } }} />);
  expect(screen.getByText("15.3%")).toBeInTheDocument();
});

const tableCite: CitedView = {
  ...base,
  kind: "frame",
  json_value: null as never,
  table: {
    columns: ["name", "ret"],
    rows: [["a", 0.05], ["b", 0.5], ["c", 0.2]],
    total_rows: 3,
    truncated: false,
    units: { ret: "fraction" },
    display_rows: [[null, "5%"], [null, "50%"], [null, "20%"]],
  },
};

test("a table shows display cells and the unit id in the header", () => {
  renderWithRun(<CitedValue cited={tableCite} />);
  expect(screen.getByText("ret (fraction)")).toBeInTheDocument();
  expect(screen.getByText("50%")).toBeInTheDocument();
  expect(screen.getByText("a")).toBeInTheDocument();
});

test("a table with display cells still sorts on the raw numbers", async () => {
  const { default: userEvent } = await import("@testing-library/user-event");
  renderWithRun(<CitedValue cited={tableCite} />);
  await userEvent.click(screen.getByText("ret (fraction)"));
  await userEvent.click(screen.getByText("ret (fraction)")); // descending
  const cells = screen.getAllByText(/%$/).map((c) => c.textContent);
  expect(cells).toEqual(["50%", "20%", "5%"]); // a text sort would put "5%" first
});

test("an old run's table without units or display still renders", () => {
  const old = { ...tableCite, table: { columns: ["ret"], rows: [[0.5]], total_rows: 1, truncated: false } };
  renderWithRun(<CitedValue cited={old as unknown as CitedView} />);
  expect(screen.getByText("ret")).toBeInTheDocument();
  expect(screen.getByText("0.5")).toBeInTheDocument();
});
