/** Desktop-Benachrichtigungen des Browsers.
 *
 *  Laeuft SparBit auf dem eigenen Rechner, ist das der direkteste Weg: kein
 *  Bot, kein Token, die Meldung erscheint einfach. Telegram bleibt fuer
 *  unterwegs.
 */
const KEY = "sparbit-desktop-notify";

export const desktopSupported = (): boolean =>
  typeof window !== "undefined" && "Notification" in window;

export const desktopEnabled = (): boolean => {
  try {
    return localStorage.getItem(KEY) === "1"
      && desktopSupported() && Notification.permission === "granted";
  } catch {
    return false;
  }
};

export function setDesktopEnabled(on: boolean): void {
  try {
    localStorage.setItem(KEY, on ? "1" : "0");
  } catch {
    /* ignorieren */
  }
}

export async function requestDesktopPermission(): Promise<boolean> {
  if (!desktopSupported()) return false;
  if (Notification.permission === "granted") return true;
  if (Notification.permission === "denied") return false;
  return (await Notification.requestPermission()) === "granted";
}

export function showDesktop(titel: string, body: string, url?: string): void {
  if (!desktopEnabled()) return;
  try {
    const note = new Notification(titel, {
      body,
      icon: "/icon.svg",
      tag: url ?? titel,      // gleiche URL ersetzt statt zu stapeln
    });
    if (url) {
      note.onclick = () => {
        window.open(url, "_blank", "noopener,noreferrer");
        note.close();
      };
    }
  } catch {
    /* Browser kann ablehnen - das ist kein Grund, die App zu stoeren */
  }
}
