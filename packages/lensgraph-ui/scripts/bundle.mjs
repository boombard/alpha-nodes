// Copy the built single-file app into the Python package and record what it was built from.
//
//   pnpm -C packages/lensgraph-ui bundle        (runs `vite build` first)
//
// BUILD_INFO.json's source_hash must equal the hash recomputed by
// packages/lensgraph/tests/test_view_app.py (`ui_source_hash`): keep both in step.
import { createHash } from "node:crypto";
import { copyFileSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const uiRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const appDir = resolve(uiRoot, "..", "lensgraph", "src", "lensgraph", "view", "app");
const ROOT_FILES = ["package.json", "pnpm-lock.yaml", "index.html", "vite.config.ts", "tsconfig.json"];

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

/** Files that shape the bundle: the root build files plus all of src/** (tests live in tests/). */
function sourceFiles() {
  return [...ROOT_FILES.map((f) => join(uiRoot, f)), ...walk(join(uiRoot, "src"))]
    .map((p) => relative(uiRoot, p).split(sep).join("/"))
    .sort();
}

const digest = createHash("sha256");
for (const rel of sourceFiles()) {
  digest.update(Buffer.concat([Buffer.from(rel), Buffer.from([0]), readFileSync(join(uiRoot, rel)), Buffer.from([0])]));
}

mkdirSync(appDir, { recursive: true });
copyFileSync(join(uiRoot, "dist", "index.html"), join(appDir, "index.html"));
writeFileSync(
  join(appDir, "BUILD_INFO.json"),
  JSON.stringify({ source_hash: digest.digest("hex"), built_at: new Date().toISOString() }, null, 2) + "\n",
);
console.log(`bundled ${appDir}`);
