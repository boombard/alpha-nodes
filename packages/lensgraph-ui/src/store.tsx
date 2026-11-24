/**
 * The one store behind every page, fed by a `DataSource`. Live updates (TASK-23) apply events to
 * this same store via `setRun`. See documentation/design/core.md, Reporting: run view.
 */
import { createContext, useContext, useSyncExternalStore, type ReactNode } from "react";
import type { DataSource } from "./data/source";
import type { RunView } from "./types/run-view";

/** What the pages render from. */
export interface StoreState {
  run: RunView | null;
  error: string | null;
}

/** A minimal external store holding the current `RunView` (or the error that stopped loading). */
export class RunStore {
  private state: StoreState = { run: null, error: null };
  private listeners = new Set<() => void>();

  getState = (): StoreState => this.state;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  /** Replace the run (initial load, or a live source's folded state). */
  setRun(run: RunView): void {
    this.state = { run, error: null };
    this.listeners.forEach((l) => l());
  }

  /** Load from `source` once; a failure is kept in `error` for the UI to show. */
  async load(source: DataSource): Promise<void> {
    try {
      this.setRun(await source.load());
    } catch (e) {
      this.state = { run: null, error: e instanceof Error ? e.message : String(e) };
      this.listeners.forEach((l) => l());
    }
  }
}

const StoreContext = createContext<RunStore | null>(null);

/** Provides `store` to the pages below. */
export function StoreProvider({ store, children }: { store: RunStore; children: ReactNode }) {
  return <StoreContext.Provider value={store}>{children}</StoreContext.Provider>;
}

/** The current store state; re-renders on change. */
export function useStoreState(): StoreState {
  const store = useContext(StoreContext);
  if (!store) throw new Error("StoreProvider is missing");
  return useSyncExternalStore(store.subscribe, store.getState);
}

/** The loaded run; pages are only rendered once it exists (see `App`). */
export function useRun(): RunView {
  const { run } = useStoreState();
  if (!run) throw new Error("run not loaded");
  return run;
}
