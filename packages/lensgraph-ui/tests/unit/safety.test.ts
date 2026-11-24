import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? sources(p) : [p];
  });
}

test("app code never uses dangerouslySetInnerHTML or innerHTML", () => {
  const files = sources(join(__dirname, "..", "..", "src")).filter((p) => /\.tsx?$/.test(p) && true);
  expect(files.length).toBeGreaterThan(5);
  for (const f of files) expect(readFileSync(f, "utf8"), f).not.toMatch(/dangerouslySetInnerHTML|\.innerHTML/);
});
