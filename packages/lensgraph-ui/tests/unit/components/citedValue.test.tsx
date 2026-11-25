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
