/* Der Weg, den jeder Benutzer einmal geht: einrichten, anmelden, sich
 * umsehen, eine Regel anlegen.
 *
 * Wenn hier etwas rot wird, ist SparBit für einen Neuling unbenutzbar -
 * egal wie grün die Unit-Tests sind.
 */
import { expect, test } from "@playwright/test";

/* Angemeldet wird in anmeldung.setup.ts - siehe playwright.config.ts. */

test("die Navigation führt auf jede Seite", async ({ page }) => {
  await page.goto("/");

  for (const [name, ueberschrift] of [
    ["Feed", /Feed/],
    ["Preisfehler", /Preisfehler/],
    ["Wunschliste", /Wunschliste/],
    ["Regeln", /Regeln/],
    ["Quellen", /Quellen/],
    ["Statistiken", /Statistik/],
  ] as const) {
    await page.getByRole("link", { name, exact: true }).click();
    await expect(page.getByRole("heading", { name: ueberschrift }).first())
      .toBeVisible();
  }
});

test("eine Regel lässt sich anlegen", async ({ page }) => {
  await page.goto("/regeln");

  await page.getByRole("button", { name: /Neue Regel|Regel anlegen/ }).first().click();

  /* Ab hier alles im Dialog suchen. „Regel anlegen" steht auch auf dem
   * Knopf der leeren Seite dahinter — der liegt im DOM vorn, ist aber
   * vom Dialog verdeckt, und ein Klick darauf läuft in einen Timeout
   * mit der Meldung „intercepts pointer events". Die zeigt dann auf den
   * Dialog und nicht auf die Ursache. */
  const dialog = page.getByRole("dialog");

  await dialog.getByLabel(/^Name/).fill("Durchstich-Regel");

  // Die Live-Vorschau ist der Kern des Editors: ohne sie baut man Regeln
  // blind. Dass sie überhaupt etwas sagt, gehört in den Durchstich.
  await expect(dialog.getByText(/Treffer|getroffen|der letzten/i).first())
    .toBeVisible({ timeout: 10_000 });

  await dialog.getByRole("button", { name: /Regel anlegen|Speichern/ }).click();

  // Der Dialog geht zu, die Regel steht in der Liste. Die Überschrift
  // und nicht irgendein Text: der Name steht auch in der Begründung
  // darunter, und getByText fände dann zwei Stellen.
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("heading", { name: "Durchstich-Regel" }))
    .toBeVisible();
});

test("die Oberfläche lässt sich auf Englisch stellen", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "English" }).click();

  // Die Navigation übersetzt sich, ohne dass die Seite neu lädt.
  await expect(page.getByRole("link", { name: "Watchlist" })).toBeVisible();
  // Und das lang-Attribut zieht mit - sonst liest ein Screenreader
  // englische Wörter mit deutscher Aussprache vor.
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
});

test("gibt es keinen Konsolenfehler beim Durchklicken?", async ({ page }) => {
  const fehler: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") fehler.push(m.text());
  });
  page.on("pageerror", (e) => fehler.push(e.message));

  await page.goto("/");
  for (const ziel of ["/feed", "/preisfehler", "/regeln", "/statistiken", "/"]) {
    await page.goto(ziel);
    await page.waitForLoadState("networkidle");
  }

  // Fehlende Bilder sind bei Deal-Feeds der Normalfall, kein Defekt.
  const echte = fehler.filter((f) => !/favicon|ERR_|Failed to load resource/i.test(f));
  expect(echte, `Konsolenfehler:\n${echte.join("\n")}`).toEqual([]);
});
