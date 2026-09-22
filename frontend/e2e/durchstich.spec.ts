/* Der Weg, den jeder Benutzer einmal geht: einrichten, anmelden, sich
 * umsehen, eine Regel anlegen.
 *
 * Wenn hier etwas rot wird, ist SparBit für einen Neuling unbenutzbar -
 * egal wie grün die Unit-Tests sind.
 */
import { expect, test } from "@playwright/test";

const BENUTZER = "durchstich";
const PASSWORT = "einGutesPasswort1";

test.describe.configure({ mode: "serial" });

test("ein frisch installiertes SparBit führt durch die Einrichtung", async ({ page }) => {
  await page.goto("/");

  // Es gibt kein Standard-Passwort: der erste Start ist ein Setup.
  const bereitsEingerichtet = await page
    .getByLabel(/^Benutzername$/).isVisible()
    .then(() => page.getByLabel(/Passwort wiederholen/).isVisible().catch(() => false));

  if (bereitsEingerichtet) {
    await page.getByLabel(/^Benutzername$/).fill(BENUTZER);
    await page.getByLabel("Passwort", { exact: true }).fill(PASSWORT);
    await page.getByLabel(/Passwort wiederholen/).fill(PASSWORT);
    await page.getByRole("button", { name: /Konto anlegen/ }).click();
  } else {
    await page.getByLabel(/^Benutzername$/).fill(BENUTZER);
    await page.getByLabel("Passwort", { exact: true }).fill(PASSWORT);
    await page.getByRole("button", { name: /^Anmelden$/ }).click();
  }

  // Danach steht die Anwendung - erkennbar an der Navigation.
  await expect(page.getByRole("link", { name: "Feed" })).toBeVisible();
});

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

test("eine Regel lässt sich anlegen und wieder löschen", async ({ page }) => {
  await page.goto("/regeln");

  await page.getByRole("button", { name: /Neue Regel|Regel anlegen/ }).first().click();
  await page.getByLabel(/^Name/).fill("Durchstich-Regel");

  // Die Live-Vorschau ist der Kern des Editors: ohne sie baut man Regeln
  // blind. Dass sie überhaupt etwas sagt, gehört in den Durchstich.
  await expect(page.getByText(/der letzten|Treffer|getroffen/i).first())
    .toBeVisible({ timeout: 10_000 });

  await page.getByRole("button", { name: /^Speichern|Anlegen$/ }).first().click();
  await expect(page.getByText("Durchstich-Regel")).toBeVisible();
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
