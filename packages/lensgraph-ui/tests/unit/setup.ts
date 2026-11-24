import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// jsdom lacks the browser APIs React Flow measures with.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;
globalThis.DOMMatrixReadOnly ??= class {
  m22 = 1;
  constructor(_transform?: string) {}
} as unknown as typeof DOMMatrixReadOnly;

afterEach(() => {
  cleanup();
  window.location.hash = "";
  delete (window as { __RUN__?: unknown }).__RUN__;
});
