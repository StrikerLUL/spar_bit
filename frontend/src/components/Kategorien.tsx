import { ChevronDown, ChevronUp, X } from "lucide-react";
import * as React from "react";
import { api, type Kategorie } from "@/lib/api";
import { useAsync } from "@/lib/useEvents";
import { cn } from "@/lib/utils";

/** Die Kategorie-Leiste über dem Feed.
 *
 *  Gedacht als der schnelle Weg zu „zeig mir nur SSDs“ — ein Klick statt
 *  eines Suchbegriffs, den man erst richtig schreiben muss. Zwei
 *  Entscheidungen dahinter:
 *
 *  **Leere Kategorien stehen hinten.** Ein Knopf, der zu null Treffern
 *  führt, ist ein kaputter Knopf. Was gerade nichts enthält, ist deshalb
 *  eingeklappt und trägt seine Null sichtbar — verschwinden soll es nicht,
 *  sonst wirkt die Auswahl je nach Tageszeit anders.
 *
 *  **Mehrfachauswahl ist ODER.** Wer „Speicher“ und „Computer“ anklickt,
 *  will beides sehen. Ein UND wäre bei Kategorien fast immer leer.
 */
export function KategorieLeiste({
  bereich = "normal",
  ausgewaehlt,
  onChange,
  nurGueltig = false,
}: {
  bereich?: "normal" | "erwachsen";
  ausgewaehlt: string[];
  onChange: (keys: string[]) => void;
  /** Muss zum Feed-Filter passen — sonst verspricht die Leiste 214 Treffer
   *  und die gefilterte Liste zeigt 180. */
  nurGueltig?: boolean;
}) {
  const { data } = useAsync<Kategorie[]>(
    () => api.kategorien.list(bereich, 30, nurGueltig), [bereich, nurGueltig]);
  const [alleZeigen, setAlleZeigen] = React.useState(false);

  if (!data || data.length === 0) return null;

  const gefuellt = data.filter((k) => k.anzahl > 0 || ausgewaehlt.includes(k.key));
  const leer = data.filter((k) => k.anzahl === 0 && !ausgewaehlt.includes(k.key));
  const sichtbar = alleZeigen ? [...gefuellt, ...leer] : gefuellt;

  const umschalten = (key: string) =>
    onChange(ausgewaehlt.includes(key)
      ? ausgewaehlt.filter((k) => k !== key)
      : [...ausgewaehlt, key]);

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {sichtbar.map((kategorie) => {
        const aktiv = ausgewaehlt.includes(kategorie.key);
        return (
          <button
            key={kategorie.key}
            type="button"
            onClick={() => umschalten(kategorie.key)}
            title={kategorie.hinweis}
            className={cn(
              "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
              aktiv
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border text-muted-foreground hover:text-foreground",
              !aktiv && kategorie.anzahl === 0 && "opacity-50",
            )}
          >
            {kategorie.label}
            <span className={cn("ml-1.5 tabular",
                                aktiv ? "opacity-80" : "text-muted-foreground/70")}>
              {kategorie.anzahl}
            </span>
          </button>
        );
      })}

      {leer.length > 0 && (
        <button
          type="button"
          onClick={() => setAlleZeigen((offen) => !offen)}
          className="flex items-center gap-1 px-1.5 py-1 text-xs text-muted-foreground
                     transition-colors hover:text-foreground"
        >
          {alleZeigen ? (
            <><ChevronUp className="h-3 w-3" />weniger</>
          ) : (
            <><ChevronDown className="h-3 w-3" />{leer.length} leere</>
          )}
        </button>
      )}

      {ausgewaehlt.length > 0 && (
        <button
          type="button"
          onClick={() => onChange([])}
          className="flex items-center gap-1 px-1.5 py-1 text-xs text-muted-foreground
                     transition-colors hover:text-destructive"
        >
          <X className="h-3 w-3" />
          Kategorien zurücksetzen
        </button>
      )}
    </div>
  );
}
