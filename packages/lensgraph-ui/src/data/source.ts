/**
 * Where the run view gets its `RunView`: the `DataSource` interface and its static
 * implementations. See documentation/design/core.md, Reporting: run view (one app, one contract).
 */
import type { RunView } from "../types/run-view";

declare global {
  interface Window {
    /** Set by `data/run.js` in a static report folder (works from file://, where fetch is blocked). */
    __RUN__?: RunView;
  }
}

/** A provider of the run's data. Live sources (TASK-23) add `subscribe`. */
export interface DataSource {
  load(): Promise<RunView>;
  /** Live sources only: receive run events; returns an unsubscribe function. */
  subscribe?(onEvent: (e: unknown) => void): () => void;
}

/** Reads the run embedded in the page by `data/run.js` (`window.__RUN__`). */
export class EmbeddedSource implements DataSource {
  async load(): Promise<RunView> {
    if (!window.__RUN__) throw new Error("window.__RUN__ is not set");
    return window.__RUN__;
  }
}

/** Fetches `run.json` (or any URL) over HTTP; for served copies and tests. */
export class FetchSource implements DataSource {
  constructor(private readonly url: string) {}

  async load(): Promise<RunView> {
    const response = await fetch(this.url);
    if (!response.ok) throw new Error(`GET ${this.url} failed: ${response.status}`);
    return (await response.json()) as RunView;
  }
}

/** The embedded source if `window.__RUN__` is set, else a fetch of `run.json`. */
export function pickSource(): DataSource {
  return window.__RUN__ ? new EmbeddedSource() : new FetchSource("run.json");
}
