/** Web Push im Browser an- und abmelden.
 *
 *  Der Teil, der im Browser laufen muss: Berechtigung erfragen, Service
 *  Worker registrieren, das Abo beim Backend hinterlegen. Die
 *  Verschluesselung passiert serverseitig (backend/app/webpush.py) -
 *  hier geht es nur um die Schluessel, die der Browser dafuer hergibt.
 */
import { api } from "@/lib/api";

/** Läuft dieser Browser überhaupt mit Push? */
export function pushMoeglich(): boolean {
  return (
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

/** base64url aus der API in das Format, das PushManager verlangt.
 *
 *  Der Puffer wird ausdrücklich als ArrayBuffer angelegt: seit
 *  TypeScript 5.7 ist ein Uint8Array sonst über ArrayBufferLike
 *  generisch, und das schließt SharedArrayBuffer ein — den die
 *  Push-API nicht annimmt.
 */
function schluesselBytes(base64: string): Uint8Array<ArrayBuffer> {
  const polster = "=".repeat((4 - (base64.length % 4)) % 4);
  const roh = atob((base64 + polster).replace(/-/g, "+").replace(/_/g, "/"));
  const bytes = new Uint8Array(new ArrayBuffer(roh.length));
  for (let i = 0; i < roh.length; i += 1) bytes[i] = roh.charCodeAt(i);
  return bytes;
}

/** Ein kurzer Name, damit man das Gerät in der Liste wiedererkennt. */
function geraetName(): string {
  const ua = navigator.userAgent;
  const system = /Android/i.test(ua) ? "Android"
    : /iPhone|iPad|iPod/i.test(ua) ? "iOS"
    : /Mac/i.test(ua) ? "Mac"
    : /Windows/i.test(ua) ? "Windows"
    : /Linux/i.test(ua) ? "Linux" : "Gerät";
  const browser = /Edg\//.test(ua) ? "Edge"
    : /Chrome\//.test(ua) ? "Chrome"
    : /Firefox\//.test(ua) ? "Firefox"
    : /Safari\//.test(ua) ? "Safari" : "Browser";
  return `${browser} auf ${system}`;
}

export async function registriereWorker(): Promise<ServiceWorkerRegistration> {
  return navigator.serviceWorker.register("/sw.js", { scope: "/" });
}

/** Anmelden. Wirft mit einem Satz, der sagt, woran es lag. */
export async function pushAnmelden(): Promise<{ neu: boolean }> {
  if (!pushMoeglich()) {
    throw new Error("Dieser Browser kann keine Push-Meldungen. Auf dem iPhone "
      + "muss SparBit dafür zum Home-Bildschirm hinzugefügt sein.");
  }

  const erlaubnis = await Notification.requestPermission();
  if (erlaubnis !== "granted") {
    throw new Error("Ohne die Erlaubnis des Browsers geht es nicht — sie lässt "
      + "sich im Schloss-Symbol neben der Adresse wieder ändern.");
  }

  const schluessel = await api.push.schluessel();
  if (!schluessel.verfuegbar || !schluessel.schluessel) {
    throw new Error(schluessel.grund || "Web Push ist auf dem Server nicht verfügbar.");
  }

  const registrierung = await registriereWorker();
  await navigator.serviceWorker.ready;

  const abo = await registrierung.pushManager.subscribe({
    // Ohne dieses Flag lehnen Chrome und Edge ab: eine Push-Nachricht,
    // die keine Meldung zeigt, ist dort nicht erlaubt.
    userVisibleOnly: true,
    applicationServerKey: schluesselBytes(schluessel.schluessel),
  });

  const roh = abo.toJSON() as { endpoint?: string; keys?: Record<string, string> };
  if (!roh.endpoint || !roh.keys?.p256dh || !roh.keys?.auth) {
    throw new Error("Der Browser hat kein vollständiges Abo geliefert.");
  }

  const antwort = await api.push.anmelden({
    endpunkt: roh.endpoint,
    p256dh: roh.keys.p256dh,
    auth: roh.keys.auth,
    geraet: geraetName(),
  });
  return { neu: antwort.neu };
}

/** Auf diesem Gerät abmelden - im Browser und im Backend. */
export async function pushAbmelden(): Promise<void> {
  if (!pushMoeglich()) return;
  const registrierung = await navigator.serviceWorker.getRegistration("/");
  const abo = await registrierung?.pushManager.getSubscription();
  if (abo) await abo.unsubscribe();
}
