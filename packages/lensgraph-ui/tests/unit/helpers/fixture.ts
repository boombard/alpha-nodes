import toyRun from "../../../fixtures/toy-run.json";
import type { RunView } from "@/types/run-view";

/** A fresh deep copy of the generated toy run, safe for tests to mutate. */
export function loadToyRun(): RunView {
  return structuredClone(toyRun) as unknown as RunView;
}
