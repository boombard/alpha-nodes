import { screen } from "@testing-library/react";
import { renderWithRun } from "../helpers/render";
import { LineChartView } from "@/components/LineChartView";
import type { LineChart } from "@/types/run-view";

const chart: LineChart = {
  title: "Prices",
  x: ["2024-01-01", "2024-01-02", "2024-01-03"],
  series: { AAA: [1, 2, null], BBB: [3, 2, 1] },
  y_label: "usd",
};

test("renders the title and a legend entry per series", () => {
  renderWithRun(<LineChartView chart={chart} />);
  expect(screen.getByText("Prices")).toBeInTheDocument();
  expect(screen.getByText("AAA")).toBeInTheDocument();
  expect(screen.getByText("BBB")).toBeInTheDocument();
});
