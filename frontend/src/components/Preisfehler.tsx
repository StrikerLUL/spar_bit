import { AlertTriangle, Search } from "lucide-react";
import { Badge } from "@/components/ui";
import { cn } from "@/lib/utils";

/** Anzeige-Bausteine für den Preisfehler-Verdacht.
 *
 *  Zwei Stufen, zwei sehr verschiedene Behauptungen — und die Oberfläche
 *  muss den Unterschied sichtbar machen, sonst gewöhnt man sich an das
 *  Zeichen und übersieht den Ernstfall:
 *
 *    heiss    — belegt. Zinnober, Streifenbalken, sticht heraus.
 *    verdacht — auffällig, aber erklärbar. Nur eine ruhige Umrandung.
 *
 *  Nie nur Farbe: jede Stufe trägt Wort und Symbol, damit sie auch bei
 *  Farbfehlsichtigkeit und auf einem schlechten Monitor ankommt.
 */

export const FEHLER_LABEL: Record<string, string> = {
  heiss: "Preisfehler",
  verdacht: "Verdacht",
};

export function FehlerBalken({ stufe }: { stufe?: string | null }) {
  if (stufe !== "heiss") return null;
  return (
    <div className="streifen h-1 w-full border-b border-signal/40"
         aria-hidden />
  );
}

export function FehlerBadge({
  stufe,
  score,
  gruende,
  className,
}: {
  stufe?: string | null;
  score?: number | null;
  gruende?: string[] | null;
  className?: string;
}) {
  if (stufe !== "heiss" && stufe !== "verdacht") return null;

  const titel = gruende?.length
    ? `${gruende.join(" ")}\n\n${score ?? 0} von 100 Punkten`
    : `${score ?? 0} von 100 Punkten`;

  if (stufe === "heiss") {
    return (
      <Badge variant="signal" className={className} title={titel}>
        <AlertTriangle className="h-3 w-3" />
        Preisfehler
      </Badge>
    );
  }
  return (
    <Badge variant="outline"
           className={cn("border-signal/50 bg-card/90 text-signal", className)}
           title={titel}>
      <Search className="h-3 w-3" />
      Verdacht
    </Badge>
  );
}

/** Die ausführliche Begründung — für Detailansicht und Preisfehler-Seite.
 *
 *  Die einzelnen Indizien stehen als Liste da statt als ein Fliesstext:
 *  man soll in zwei Sekunden entscheiden können, ob man dem Fund glaubt,
 *  und dafür muss man die Gründe einzeln sehen.
 */
export function FehlerBegruendung({
  stufe,
  score,
  gruende,
  className,
}: {
  stufe?: string | null;
  score?: number | null;
  gruende?: string[] | null;
  className?: string;
}) {
  if ((stufe !== "heiss" && stufe !== "verdacht") || !gruende?.length) return null;
  const heiss = stufe === "heiss";

  return (
    <div
      className={cn(
        "rounded-md border p-3",
        heiss ? "border-signal/45 bg-signal/[0.07]" : "border-border bg-muted/30",
        className,
      )}
    >
      <div className="mb-2 flex items-center gap-2">
        {heiss ? (
          <AlertTriangle className="h-4 w-4 shrink-0 text-signal" />
        ) : (
          <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
        )}
        <span className={cn("text-xs font-semibold uppercase tracking-[0.07em]",
                            heiss ? "text-signal" : "text-muted-foreground")}>
          {heiss ? "Preisfehler" : "Preisfehler-Verdacht"}
        </span>
        <span className="tabular ml-auto text-[11px] text-muted-foreground"
              title="Je mehr Indizien zusammenkommen, desto höher">
          {score ?? 0}/100
        </span>
      </div>
      <ul className="space-y-1">
        {gruende.map((grund, i) => (
          <li key={i} className="flex gap-2 text-xs leading-relaxed text-foreground/85">
            <span aria-hidden className="select-none text-muted-foreground">–</span>
            <span>{grund}</span>
          </li>
        ))}
      </ul>
      {heiss && (
        <p className="mt-2 border-t border-signal/20 pt-2 text-[11px] text-muted-foreground">
          Preisfehler werden oft innerhalb von Minuten korrigiert. Eine
          Bestellung kann der Händler stornieren — ein Anspruch besteht nicht.
        </p>
      )}
    </div>
  );
}
