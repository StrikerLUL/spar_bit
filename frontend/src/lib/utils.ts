import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const CURRENCY_SYMBOL: Record<string, string> = { EUR: "€", USD: "$", GBP: "£" };

export function formatPrice(
  value: number | null | undefined,
  currency = "EUR",
): string {
  if (value === null || value === undefined) return "—";
  if (value <= 0.009) return "gratis";
  const symbol = CURRENCY_SYMBOL[currency] ?? currency;
  return `${value.toFixed(2).replace(".", ",")} ${symbol}`;
}

/** Geldbetrag ohne die "gratis"-Sonderbehandlung.
 *  Fuer Summen wie "gespart": 0 EUR heisst null Ersparnis, nicht "gratis". */
export function formatAmount(
  value: number | null | undefined,
  currency = "EUR",
): string {
  if (value === null || value === undefined) return "—";
  const symbol = CURRENCY_SYMBOL[currency] ?? currency;
  return `${value.toFixed(2).replace(".", ",")} ${symbol}`;
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("de-DE").format(value);
}

/** "vor 3 Min." statt Zeitstempel - im Ticker deutlich besser lesbar. */
export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const seconds = Math.floor((Date.now() - then) / 1000);
  if (seconds < 0) return "gleich";
  if (seconds < 60) return "gerade eben";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `vor ${minutes} Min.`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `vor ${hours} Std.`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `vor ${days} ${days === 1 ? "Tag" : "Tagen"}`;
  return new Date(iso).toLocaleDateString("de-DE", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds} Sek.`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} Min.`;
  if (seconds < 86400) {
    const h = Math.floor(seconds / 3600);
    const m = Math.round((seconds % 3600) / 60);
    return m ? `${h} Std. ${m} Min.` : `${h} Std.`;
  }
  return `${Math.floor(seconds / 86400)} Tage`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

/** Textliste <-> Zeilen, fuer die Listen-Felder im UI. */
export const linesToList = (text: string): string[] =>
  text.split("\n").map((l) => l.trim()).filter(Boolean);

export const listToLines = (list: string[] | undefined): string =>
  (list ?? []).join("\n");

export const SOURCE_LABELS: Record<string, string> = {
  mydealz: "mydealz",
  preisjaeger: "Preisjäger",
  hotukdeals: "HotUKDeals",
  dealabs: "Dealabs",
  sparhamster: "Sparhamster",
  schnaeppchenfuchs: "Schnäppchenfuchs",
  reddit: "Reddit",
  epic: "Epic",
  gog: "GOG",
  steam: "Steam",
  cheapshark: "CheapShark",
  itad: "IsThereAnyDeal",
  ggdeals: "GG.deals",
  custom_feed: "Eigene Feeds",
};

export const sourceLabel = (id: string): string => SOURCE_LABELS[id] ?? id;


/** Woher ein Deal-Bild geladen wird.
 *
 *  Lokal zwischengespeicherte Bilder gewinnen: sonst erfaehrt der Haendler
 *  bei jedem Oeffnen des Feeds, dass du dir seine Deals ansiehst. Nur wenn
 *  SparBit das Bild nicht holen konnte, wird auf das Original ausgewichen.
 */
export function bildQuelle(deal: {
  bild_lokal?: string | null;
  bild?: string | null;
}): string | null {
  if (deal.bild_lokal) return `/api/bilder/${deal.bild_lokal}`;
  return deal.bild ?? null;
}
