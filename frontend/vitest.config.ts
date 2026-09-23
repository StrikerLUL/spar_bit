/// <reference types="vitest" />
//
// Tests fuer die Oberflaeche. Bewusst getrennt von vite.config.ts: die
// Test-Umgebung braucht jsdom und ein Setup, der Produktionsbau
// braucht beides nicht.
//
// Was hier NICHT geprueft wird: wie etwas aussieht. Snapshot-Tests ueber
// Tailwind-Klassen halten bis zur naechsten Anpassung und sagen dann
// "rot", ohne dass etwas kaputt ist. Geprueft wird, was der Benutzer
// tun kann - Text, Rollen, Beschriftungen.
import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  test: {
    // Nur die Bauteil-Tests. Ohne diese Zeile sammelt Vitest auch die
    // Playwright-Dateien in e2e/ ein und scheitert dort an
    // test.describe.configure() - mit einer Meldung, die auf alles
    // Moegliche zeigt, nur nicht auf die Ursache.
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/test/**", "src/**/*.test.{ts,tsx}", "src/lib/api-typen.ts"],
    },
  },
});
