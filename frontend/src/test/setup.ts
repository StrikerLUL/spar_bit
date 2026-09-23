// Laeuft vor jedem Test.
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

beforeEach(() => {
  // jsdom kennt matchMedia nicht - die Themenumschaltung fragt danach.
  // Ohne diesen Ersatz stuerzt jeder Test ab, der Layout rendert.
  if (!window.matchMedia) {
    window.matchMedia = (query: string) =>
      ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }) as MediaQueryList;
  }
  // Ebenso wenig kennt es scrollIntoView - die Befehlspalette benutzt es.
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => {};
  }
});
