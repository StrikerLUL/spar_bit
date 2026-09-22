/* Einmal anmelden, für alle Tests.
 *
 * Playwright gibt jedem Test einen frischen Browser-Kontext — also auch
 * ein frisches Cookie-Glas. Ohne diesen Schritt wäre jeder Test nach dem
 * ersten wieder ausgeloggt, und man sähe als Fehler „Link 'Feed' nicht
 * gefunden" statt „nicht angemeldet".
 *
 * Läuft als eigenes Projekt vor den anderen und legt den angemeldeten
 * Zustand in einer Datei ab. Die Tests starten damit.
 */
import { expect, test as setup } from "@playwright/test";

export const BENUTZER = "durchstich";
export const PASSWORT = "einGutesPasswort1";
const ZUSTAND = "e2e/.auth/zustand.json";

setup("anmelden (oder einrichten)", async ({ page }) => {
  await page.goto("/");

  // Es gibt kein Standard-Passwort: beim allerersten Start ist das hier
  // ein Setup-Formular, danach ein Anmeldeformular. Der Unterschied ist
  // das Feld für die Wiederholung.
  const wiederholung = page.getByLabel(/Passwort wiederholen/);
  const istSetup = await wiederholung.isVisible().catch(() => false);

  await page.getByLabel(/^Benutzername$/).fill(BENUTZER);
  await page.getByLabel("Passwort", { exact: true }).fill(PASSWORT);

  if (istSetup) {
    await wiederholung.fill(PASSWORT);
    await page.getByRole("button", { name: /Konto anlegen/ }).click();
  } else {
    await page.getByRole("button", { name: /^Anmelden$/ }).click();
  }

  // Die Navigation ist das Zeichen, dass die Anwendung steht.
  await expect(page.getByRole("link", { name: "Feed", exact: true }))
    .toBeVisible();

  await page.context().storageState({ path: ZUSTAND });
});
