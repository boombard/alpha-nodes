/** Generates the toy report with the lensgraph CLI into a temp store; exports its path as REPORT_URL. */
import { execFileSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

export default function globalSetup(): void {
  const root = resolve(import.meta.dirname, "../../../..");
  const store = mkdtempSync(join(tmpdir(), "lensgraph-e2e-"));
  const tests = join(root, "packages/lensgraph/tests");
  const out = execFileSync(
    "uv",
    ["run", "lensgraph", "run", join(tests, "toy/toy_run.yaml"), "--path", tests, "--store", store],
    { cwd: root, encoding: "utf8" },
  );
  const report = /^report: (.+)$/m.exec(out)?.[1];
  if (!report) throw new Error(`no report path in CLI output:\n${out}`);
  process.env.REPORT_URL = pathToFileURL(report).href;
  process.env.REPORT_DIR = join(report, "..");
}
