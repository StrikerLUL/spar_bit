/* Ein Durchstich durch die ganze Anwendung - echtes Backend, echter Browser.
 *
 * Die Vitest-Tests prüfen Bauteile einzeln, und das ist das meiste wert.
 * Was sie nicht sehen können: ob Anmeldung, Cookie, Router und API
 * zusammen funktionieren. Genau dort sitzt der Fehler, der eine
 * Installation unbenutzbar macht und in keinem Unit-Test auftaucht.
 *
 * Darum bewusst wenige Tests, aber echte: SparBit startet wirklich, mit
 * einer Wegwerf-Datenbank im Temp-Verzeichnis.
 */
import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const WURZEL = path.resolve(__dirname, "..");
// Eine eigene Datenbank je Lauf. Ohne das liefe der Test gegen die
// echten Daten des Entwicklers - und der Setup-Schritt wäre beim
// zweiten Lauf schon vorbei.
const DATEN = path.join(__dirname, ".e2e-daten");

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,          // ein Backend, eine Datenbank
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["html", { open: "never" }], ["list"]] : "list",
  timeout: 30_000,
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    locale: "de-DE",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],

  webServer: [
    {
      command: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`,
      cwd: path.join(WURZEL, "backend"),
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: {
        SPARBIT_DATA_DIR: DATEN,
        SPARBIT_LOG_LEVEL: "WARNING",
        // Kein Long Polling im Test: es hielte den Prozess offen und
        // versuchte, api.telegram.org zu erreichen.
        SPARBIT_TELEGRAM_POLLING: "false",
      },
    },
    {
      command: "npm run dev",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
