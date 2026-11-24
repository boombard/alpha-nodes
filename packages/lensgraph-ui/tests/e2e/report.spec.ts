/** Smoke test of the real report: the CLI-generated toy run, opened from file:// in Chromium. */
import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

interface Plan {
  nodes: { key: { name: string } }[];
  edges: { source: { name: string }; target: { name: string } }[];
}

test("toy report: summary, claim to cited value, review, plan graph", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(process.env.REPORT_URL!);

  // Summary lists S1 to S3.
  for (const id of ["S1", "S2", "S3"]) await expect(page.getByRole("link", { name: id, exact: true })).toBeVisible();

  // Open S1, click a claim citation, see the cited value.
  await page.getByRole("link", { name: "S1", exact: true }).click();
  const verdict = page.locator("article[aria-label^=\"Verdict\"]").filter({ has: page.locator(".MuiChip-clickable") }).first();
  await expect(verdict).toBeVisible();
  await verdict.locator(".MuiChip-clickable").first().click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("heading")).toContainText("source");
  await expect(dialog.locator("table, [role=grid], pre, .MuiDataGrid-root").first()).toBeVisible();
  await dialog.getByRole("button", { name: "Close" }).click();

  // The review is shown.
  await expect(page.getByRole("region", { name: "Review" })).toContainText("Grows well");

  // The plan graph has one rendered node per plan node name and one edge per distinct plan edge.
  const plan: Plan = JSON.parse(readFileSync(join(process.env.REPORT_DIR!, "run.json"), "utf8")).plan;
  const names = new Set(plan.nodes.map((n) => n.key.name));
  const edges = new Set(plan.edges.map((e) => `${e.source.name}->${e.target.name}`));
  await page.goto(`${process.env.REPORT_URL!}#/graph`);
  await expect(page.locator(".react-flow__node")).toHaveCount(names.size);
  await expect(page.locator(".react-flow__edge")).toHaveCount(edges.size);

  expect(errors).toEqual([]);
});
