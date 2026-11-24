import { EmbeddedSource, FetchSource, pickSource } from "@/data/source";
import { loadToyRun } from "../helpers/fixture";

test("pickSource prefers window.__RUN__", async () => {
  const run = loadToyRun();
  (window as { __RUN__?: unknown }).__RUN__ = run;
  const source = pickSource();
  expect(source).toBeInstanceOf(EmbeddedSource);
  expect((await source.load()).summary.run_id).toBe("toy-run");
});

test("pickSource falls back to fetching run.json", () => {
  expect(pickSource()).toBeInstanceOf(FetchSource);
});

test("FetchSource loads a RunView from a url", async () => {
  const run = loadToyRun();
  const fetchStub = vi.fn(async () => new Response(JSON.stringify(run)));
  vi.stubGlobal("fetch", fetchStub);
  expect((await new FetchSource("run.json").load()).summary.run_id).toBe("toy-run");
  expect(fetchStub).toHaveBeenCalledWith("run.json");
  vi.unstubAllGlobals();
});

test("FetchSource rejects on an HTTP error", async () => {
  vi.stubGlobal("fetch", async () => new Response("no", { status: 404 }));
  await expect(new FetchSource("run.json").load()).rejects.toThrow(/404/);
  vi.unstubAllGlobals();
});
