import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithRun } from "../helpers/render";
import { loadToyRun } from "../helpers/fixture";
import { CandidatePage } from "@/pages/Candidate";

test("the review summary and fit render", () => {
  renderWithRun(<CandidatePage id="S1" />);
  expect(screen.getByText("Grows well; safety evidence is thin.")).toBeInTheDocument();
  expect(screen.getByText("grows quickly")).toBeInTheDocument();
  expect(screen.getByText("priority: speed")).toBeInTheDocument();
});

test("verdict details render, including errors", () => {
  renderWithRun(<CandidatePage id="S3" />);
  expect(screen.getAllByText(/missing columns/).length).toBeGreaterThan(0);
});

test("a claim containing <script> renders as text", () => {
  const run = loadToyRun();
  const s1 = run.candidates.find((c) => c.id === "S1")!;
  s1.record.dossier.verdicts[0].claims![0].text = "<script>alert(1)</script>";
  const { container } = renderWithRun(<CandidatePage id="S1" />, run);
  expect(screen.getByText("<script>alert(1)</script>")).toBeInTheDocument();
  expect(container.querySelector("script")).toBeNull();
});

test("a review point shows text, priority badge and cite chips as separate elements", () => {
  renderWithRun(<CandidatePage id="S1" />);
  const text = screen.getByText("grows quickly");
  const priority = screen.getByText("priority: speed");
  const cite = screen.getByText("verdict.growth");
  expect(new Set([text, priority, cite]).size).toBe(3);
  expect(priority.closest(".badge")).not.toBeNull();
  expect(cite.closest(".chip")).not.toBeNull();
  expect(text).not.toContainElement(cite);
});

test("provenance shows model, attempts and tokens only for model-backed verdicts", () => {
  const run = loadToyRun();
  const growthVerdict = run.candidates
    .find((c) => c.id === "S1")!
    .record.dossier.verdicts.find((v) => v.lens === "growth")!;
  renderWithRun(<CandidatePage id="S1" />, run);
  const growth = screen.getByRole("article", { name: "Verdict growth" });
  const safety = screen.getByRole("article", { name: "Verdict safety" });
  expect(within(growth).getByText(new RegExp(`v${growthVerdict.provenance.lens_version}`))).toBeInTheDocument();
  expect(growth).not.toHaveTextContent(/attempt/);
  expect(growth).not.toHaveTextContent(/tokens/);
  expect(safety).toHaveTextContent(/function:_scripted:, default, 1 attempt\(s\), 153\/20 tokens/);
});

test("Back, Previous and Next follow the list's sort order and keep its state", () => {
  window.location.hash = "#/candidate/S2?sort=share:asc"; // list order: S3, S2, S1
  renderWithRun(<CandidatePage id="S2" />);
  expect(screen.getByText("2 of 3")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /previous/i })).toHaveAttribute("href", "#/candidate/S3?sort=share%3Aasc");
  expect(screen.getByRole("link", { name: /next/i })).toHaveAttribute("href", "#/candidate/S1?sort=share%3Aasc");
  expect(screen.getByRole("link", { name: /back to list/i })).toHaveAttribute("href", "#/?sort=share%3Aasc");
});

test("Previous is disabled on the first candidate of the list", () => {
  window.location.hash = "#/candidate/S3?sort=share:asc";
  renderWithRun(<CandidatePage id="S3" />);
  expect(screen.getByText("1 of 3")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /previous/i })).toBeDisabled();
});

test("a candidate outside the current list has no position and no Previous/Next", () => {
  window.location.hash = "#/candidate/S1?preset=failures"; // only S3 matches
  renderWithRun(<CandidatePage id="S1" />);
  expect(screen.getByText(/not in the current list/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /next/i })).toBeDisabled();
});

test("the Graph section is collapsible and shows only this candidate's nodes plus shared ones", async () => {
  const run = loadToyRun();
  const expected = run.plan.nodes.filter((n) => n.key.candidate === "S1" || n.key.candidate == null).length;
  const { container } = renderWithRun(<CandidatePage id="S1" />, run);
  expect(container.querySelectorAll(".react-flow__node")).toHaveLength(0);
  await userEvent.click(screen.getByRole("button", { name: /graph/i }));
  expect(container.querySelectorAll(".react-flow__node")).toHaveLength(expected);
  expect(container.querySelectorAll(".react-flow__handle-left")).toHaveLength(expected);
  expect(container.querySelectorAll(".react-flow__handle-right")).toHaveLength(expected);
});

test("an abstained verdict shows its reason as an info alert, a failed one as an error", () => {
  const run = loadToyRun();
  const verdicts = run.candidates.find((c) => c.id === "S2")!.record.dossier.verdicts;
  const safety = verdicts.find((v) => v.lens === "safety")!;
  expect(safety.status).toBe("abstained");
  renderWithRun(<CandidatePage id="S2" />, run);
  const alert = within(screen.getByRole("article", { name: "Verdict safety" })).getByRole("alert");
  expect(alert).toHaveTextContent("Abstained: critical input 'tox_notes' unavailable");
  expect(alert).toHaveClass("MuiAlert-colorInfo");
});

test("a failed verdict still shows Error: in an error alert", () => {
  renderWithRun(<CandidatePage id="S3" />);
  const alerts = screen.getAllByRole("alert").filter((a) => /^Error:/.test(a.textContent ?? ""));
  expect(alerts.length).toBeGreaterThan(0);
  expect(alerts[0]).toHaveClass("MuiAlert-colorError");
});
