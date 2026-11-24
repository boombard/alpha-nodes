// Generate src/types/run-view.ts from the Python `RunView` model (the contract).
//
//   node packages/lensgraph-ui/scripts/gen-types.mjs      (or: pnpm -C packages/lensgraph-ui gen:types)
//
// The JSON Schema comes from `lensgraph.view.schema.main`; json-schema-to-typescript runs
// through `pnpm dlx`, so nothing is installed. The first line of the output carries the schema
// hash, which a Python test compares with the current schema (no Node needed in CI).
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const J2TS = "json-schema-to-typescript@15.0.4";
const here = dirname(fileURLToPath(import.meta.url));
const uiRoot = resolve(here, "..");
const repoRoot = resolve(uiRoot, "..", "..");
const out = join(uiRoot, "src", "types", "run-view.ts");

const raw = execFileSync("uv", ["run", "python", "-c", "from lensgraph.view.schema import main; main()"], {
  cwd: repoRoot,
  encoding: "utf8",
  maxBuffer: 64 * 1024 * 1024,
});
const { hash, schema } = JSON.parse(raw);

const tmp = mkdtempSync(join(tmpdir(), "run-view-"));
const schemaFile = join(tmp, "run-view.schema.json");
const tsFile = join(tmp, "run-view.ts");
writeFileSync(schemaFile, JSON.stringify(schema));
execFileSync(
  "pnpm",
  ["dlx", J2TS, "--input", schemaFile, "--output", tsFile, "--no-additionalProperties"],
  { cwd: tmp, stdio: "inherit" },
);

const header = `// schema-hash: ${hash}\n// Generated from lensgraph.view.models.RunView by scripts/gen-types.mjs. Do not edit.\n`;
const body = readFileSync(tsFile, "utf8").replace(/^\/\* eslint-disable \*\/\n/, "");
writeFileSync(out, header + body);
console.log(`wrote ${out} (schema-hash ${hash})`);
