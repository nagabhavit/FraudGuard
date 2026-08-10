import "@testing-library/jest-dom/vitest";

// Milestone 28: this project's vitest config does not set `globals: true`
// (existing tests import `afterEach` explicitly from "vitest" rather than
// relying on it as a global), which is what Testing Library's automatic
// per-test cleanup normally detects to register itself. Without it,
// `render()`'s output -- and any of its running effects, e.g. App's
// polling `setInterval` -- accumulates across every test in a file
// instead of unmounting between them. Previously masked because each
// existing test's fixture text happened to be unique enough not to
// collide; two tests reusing the same fixture (Milestone 28) is what
// surfaces it as a real "multiple elements found" failure, not a new
// problem introduced by those tests.
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});
