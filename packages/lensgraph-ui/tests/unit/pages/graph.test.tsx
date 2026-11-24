import { fireEvent, screen, within } from "@testing-library/react";
import { PlanGraphPage } from "@/pages/PlanGraph";
import { loadToyRun } from "../helpers/fixture";
import { renderWithRun } from "../helpers/render";
import { makeScaleRun } from "../helpers/scale";

const names = (run = loadToyRun()) => new Set(run.plan.nodes.map((n) => n.key.name));

test("the run-level page renders one node per node name, each with target and source handles", () => {
  const run = loadToyRun();
  const { container } = renderWithRun(<PlanGraphPage />, run);
  expect(container.querySelectorAll(".react-flow__node")).toHaveLength(names(run).size);
  expect(container.querySelectorAll(".react-flow__handle-left")).toHaveLength(names(run).size);
  expect(container.querySelectorAll(".react-flow__handle-right")).toHaveLength(names(run).size);
  expect(container.querySelector(".react-flow__node.kind-reviewer")).not.toBeNull();
});

test("nodes show kind and a status mix, shared nodes are marked", () => {
  const run = makeScaleRun(150);
  const { container } = renderWithRun(<PlanGraphPage />, run);
  const clean = container.querySelector('.react-flow__node[data-id="assay_clean"]') as HTMLElement;
  expect(clean).toHaveTextContent(/transform/);
  expect(clean).toHaveTextContent(/\d+ ok · \d+ failed/);
  expect(within(clean).getByRole("img", { name: /status mix/i })).toBeInTheDocument();
  const shared = container.querySelector('.react-flow__node[data-id="reference_panel"]') as HTMLElement;
  expect(shared).toHaveTextContent(/shared/);
});

test("clicking a node lists its candidates per status, linking to their pages", () => {
  const { container } = renderWithRun(<PlanGraphPage />, loadToyRun());
  // fireEvent: userEvent's mousedown reaches d3-zoom, which needs a real window view.
  fireEvent.click(container.querySelector('.react-flow__node[data-id="assay_clean"]') as HTMLElement);
  const panel = screen.getByRole("dialog", { name: /assay_clean/ });
  expect(within(panel).getByText(/failed \(1\)/)).toBeInTheDocument();
  expect(within(panel).getByRole("link", { name: "S3" })).toHaveAttribute("href", "#/candidate/S3");
  expect(within(panel).getByText(/ok \(2\)/)).toBeInTheDocument();
});
