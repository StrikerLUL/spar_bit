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
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

// package.json sagt "type": "module" - hier gibt es also kein __dirname.
// Der Fehler dafür ("__dirname is not defined in ES module scope") kommt
// beim Laden der Konfiguration und zeigt auf keine einzige Testdatei.
const HIER = path.dirname(fileURLToPath(import.meta.url));
const WURZEL = path.resolve(HIER, "..");
// Eine eigene Datenbank je Lauf. Ohne das liefe der Test gegen die
// echten Daten des Entwicklers - und der Setup-Schritt wäre beim
// zweiten Lauf schon vorbei.
const DATEN = path.join(HIER, ".e2e-daten");

// Welches Python das Backend startet. Lokal legt run.py eine .venv an und
// dort steckt uvicorn - "python" allein ist dann das System-Python und
// scheitert mit "No module named uvicorn", einer Meldung, die auf alles
// Mögliche zeigt außer auf die Ursache. In der CI gibt es keine .venv,
// dort ist "python" richtig.
const VENV = path.join(WURZEL, ".venv", "bin", "python");
const PYTHON = process.env.SPARBIT_PYTHON
  ?? (existsSync(VENV) ? VENV : "python");

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
  projects: [
  {
    // Meldet sich einmal an und legt den Zustand ab. Ohne diesen Schritt
    // startet jeder Test ausgeloggt - und scheitert dann mit "Link nicht
    // gefunden" statt "nicht angemeldet".
    name: "anmeldung",
    testMatch: /.*\.setup\.ts/,
    use: {
      ...devices["Desktop Chrome"],
      ...(process.env.SPARBIT_CHROMIUM
        ? { launchOptions: { executablePath: process.env.SPARBIT_CHROMIUM } }
        : {}),
    },
  },
  {
    name: "chromium",
    dependencies: ["anmeldung"],
    use: {
      ...devices["Desktop Chrome"],
      storageState: "e2e/.auth/zustand.json",
      // Wer schon einen Chromium hat (Distributionspaket, vorbereitetes
      // Image), muss keine zweiten 150 MB holen: SPARBIT_CHROMIUM auf die
      // ausführbare Datei zeigen lassen. Ohne die Variable nimmt Playwright
      // seinen eigenen - so wie in der CI.
      ...(process.env.SPARBIT_CHROMIUM
        ? { launchOptions: { executablePath: process.env.SPARBIT_CHROMIUM } }
        : {}),
    },
  },
  ],

  webServer: [
    {
      command: `${PYTHON} -m uvicorn app.main:app --host 127.0.0.1 --port 8000`,
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
      // Die Adresse ausdrücklich: Vite lauscht sonst auf "localhost", und
      // das ist auf den GitHub-Runnern zuerst ::1. Der Test wartet dann
      // auf 127.0.0.1, findet nichts und meldet nach einer Minute nur
      // "Timed out waiting from config.webServer" - lokal, ohne IPv6,
      // fällt das nie auf. strictPort, damit ein belegter Port als Fehler
      // kommt und nicht als stiller Wechsel auf 5174.
      command: "npm run dev -- --host 127.0.0.1 --port 5173 --strictPort",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
