import { SummaryPage } from "@/pages/Summary";
import { createAppTheme, statusColor } from "@/theme";
import { renderWithRun } from "./helpers/render";

test("light and dark themes have their own palette and one status colour table", () => {
  const light = createAppTheme("light");
  const dark = createAppTheme("dark");
  expect(light.palette.mode).toBe("light");
  expect(dark.palette.mode).toBe("dark");
  expect(statusColor(light, "failed")).not.toBe(statusColor(dark, "failed"));
  expect(statusColor(light, "no-such-status")).toBe(light.palette.status.unknown);
});

test("emotion injects the component styles (the single-file build relies on this)", () => {
  renderWithRun(<SummaryPage />);
  expect(document.head.querySelectorAll("style[data-emotion]").length).toBeGreaterThan(0);
});
