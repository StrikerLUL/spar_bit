import { BadgeCheck, CalendarX, CircleSlash } from "lucide-react";
import type { Deal } from "@/lib/api";
import { Badge } from "@/components/ui";

/** Abzeichen zur Gegenprobe auf der Zielseite.
 *
 *  Gezeigt wird nur, was etwas aussagt. `unklar` und `nicht erreichbar`
 *  bleiben unsichtbar: ein Abzeichen "wir wissen es nicht" an jeder zweiten
 *  Karte wäre Lärm, und aus dem Fehlen einer Aussage soll niemand eine
 *  ableiten.
 */
export function PruefBadge({ deal }: { deal: Deal }) {
  const status = deal.check_status;
  if (!status || status === "unklar" || status === "unerreichbar") return null;

  if (status === "widerlegt") {
    return (
      <Badge variant="destructive" title={deal.check_text ?? undefined}>
        <CircleSlash className="h-3 w-3" />
        stimmt nicht
      </Badge>
    );
  }
  if (status === "abgelaufen") {
    return (
      <Badge variant="outline"
             className="border-border bg-card/90 text-muted-foreground"
             title={deal.check_text ?? undefined}>
        <CalendarX className="h-3 w-3" />
        abgelaufen
      </Badge>
    );
  }
  return (
    <Badge variant="success" title={deal.check_text ?? "Auf der Zielseite geprüft"}>
      <BadgeCheck className="h-3 w-3" />
      geprüft
    </Badge>
  );
}

/** Erklärt in einer Zeile, warum hier kein Gratis-Schild hängt. */
export function GratisHinweis({ deal }: { deal: Deal }) {
  if (!deal.gratis_hinweis) return null;
  return (
    <p className="text-[11px] leading-relaxed text-muted-foreground"
       title="SparBit hat das Gratis-Wort im Text gefunden, aber es bezog sich
nicht auf den Artikel">
      „gratis“ im Text — {deal.gratis_hinweis}
    </p>
  );
}
