import { Bookmark, ExternalLink, Flame, LineChart, Store } from "lucide-react";
import type { Deal } from "@/lib/api";
import {
  bildQuelle, cn, eurHinweis, formatAmount, formatPrice, sourceLabel, timeAgo,
  zeigeStreichpreis, zeitraumKuerzel,
} from "@/lib/utils";
import { Badge, Button, Card } from "@/components/ui";
import { UrteilBadge } from "@/components/Urteil";
import { FehlerBalken, FehlerBadge } from "@/components/Preisfehler";
import { GratisHinweis, PruefBadge } from "@/components/Gratischeck";

/** Eine Deal-Karte.
 *
 *  Aufgebaut um den Preis, nicht um das Bild: das Bild ist bei Feeds oft
 *  falsch verknüpft oder fehlt ganz, der Preis ist der Grund, warum man
 *  hinschaut. Darum steht er gross, tabellarisch und mit allem daneben,
 *  was man braucht, um ihn einzuordnen — Streichpreis, EUR-Gegenwert bei
 *  Fremdwährung, Preisurteil.
 */
export function DealCard({
  deal,
  onBookmark,
  onOpen,
  onPrueft,
}: {
  deal: Deal;
  onBookmark?: (id: number) => void;
  onOpen?: (id: number) => void;
  /** Wird beim Öffnen des Deals gerufen — für die Gegenprobe der Zielseite. */
  onPrueft?: (id: number) => void;
}) {
  const rabatt = deal.rabatt_prozent;
  const streichpreis = zeigeStreichpreis(deal);
  const eur = eurHinweis(deal.preis_eur, deal.waehrung);
  const bild = bildQuelle(deal);
  const kuerzel = zeitraumKuerzel(deal.preis_zeitraum);
  // Abgelaufen heisst: die Zielseite hat es selbst gesagt. Die Karte
  // bleibt stehen (sie erklärt, warum da nichts mehr kommt), tritt aber
  // zurück — sonst klickt man wieder darauf. „stimmt nicht" gehört
  // ausdrücklich nicht dazu: da wurde nur der Preis korrigiert, das
  // Angebot gibt es noch.
  const vorbei = deal.check_status === "abgelaufen";

  return (
    <Card hover className={cn("group flex flex-col overflow-hidden",
                              vorbei && "opacity-60 saturate-50")}>
      <FehlerBalken stufe={deal.fehler_stufe} />

      <div className="relative aspect-[16/9] overflow-hidden border-b border-border bg-muted/50">
        {bild ? (
          <img
            src={bild}
            alt=""
            loading="lazy"
            className="h-full w-full object-cover"
            onError={(e) => {
              // Kaputte Bild-URLs sind bei Feeds normal - Platzhalter statt Bruch.
              (e.currentTarget as HTMLImageElement).style.display = "none";
            }}
          />
        ) : (
          <div className="flex h-full items-center justify-center text-muted-foreground/25">
            <Store className="h-8 w-8" strokeWidth={1.25} />
          </div>
        )}

        {/* pr-10 haelt die Abzeichen vom Merken-Knopf frei: ohne das laeuft
            eine vierstellige Temperatur darunter und wird abgeschnitten. */}
        <div className="absolute left-2 top-2 flex flex-wrap gap-1 pr-10">
          <FehlerBadge stufe={deal.fehler_stufe} score={deal.fehler_score}
                       gruende={deal.fehler_gruende} />
          {deal.ist_gratis ? (
            <Badge variant="success">Gratis</Badge>
          ) : rabatt ? (
            <Badge variant="warning" className="tabular">
              −{Math.round(rabatt)}%
            </Badge>
          ) : null}
          <PruefBadge deal={deal} />
          {deal.temperatur != null && deal.temperatur >= 200 && (
            <Badge variant="outline"
                   className="tabular border-border bg-card/90 text-foreground">
              <Flame className="h-3 w-3" />
              {Math.round(deal.temperatur)}°
            </Badge>
          )}
          <UrteilBadge stufe={deal.urteil} text={deal.urteil_text} />
        </div>

        {onBookmark && (
          <button
            onClick={() => onBookmark(deal.id)}
            aria-label={deal.bookmarked ? "Merkung entfernen" : "Merken"}
            className={cn(
              "absolute right-2 top-2 rounded-sm border border-border p-1.5",
              "bg-card/90 transition-colors hover:bg-card",
              deal.bookmarked ? "text-primary" : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Bookmark className={cn("h-3.5 w-3.5", deal.bookmarked && "fill-current")} />
          </button>
        )}
      </div>

      <div className="flex flex-1 flex-col gap-3 p-3.5">
        {onOpen ? (
          <button
            type="button"
            onClick={() => onOpen(deal.id)}
            className="line-clamp-2 text-left text-[13px] font-medium leading-snug transition-colors hover:text-primary"
            title="Details, Preisverlauf und Preisalarm"
          >
            {deal.titel}
          </button>
        ) : (
          <a
            href={deal.url}
            target="_blank"
            rel="noopener noreferrer"
            className="line-clamp-2 text-[13px] font-medium leading-snug transition-colors hover:text-primary"
            title={deal.titel}
          >
            {deal.titel}
          </a>
        )}

        <div className="mt-auto space-y-2.5">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <span
              className={cn(
                "tabular text-[19px] font-semibold leading-none tracking-tight",
                deal.ist_gratis && "text-success",
              )}
            >
              {deal.ist_gratis ? "gratis" : formatPrice(deal.preis, deal.waehrung)}
              {kuerzel && !deal.ist_gratis && (
                <span className="text-[13px] font-medium text-muted-foreground">
                  {kuerzel}
                </span>
              )}
            </span>
            {streichpreis && (
              <span className="tabular text-xs text-muted-foreground line-through decoration-muted-foreground/60">
                {formatAmount(deal.originalpreis, deal.waehrung)}
                {/* Der Streichpreis eines Abos ist auch einer pro Monat —
                    ohne das Kürzel steht daneben scheinbar ein Einmalpreis. */}
                {kuerzel}
              </span>
            )}
            {eur && (
              <span className="tabular text-[11px] text-muted-foreground"
                    title="Umgerechnet mit dem hinterlegten Kurs">
                {eur}
              </span>
            )}
          </div>

          {/* "für 3 Monate" bzw. "Stückpreis": ohne diese Zeile steht eine
              Zahl da, die ohne ihren Bezug nichts aussagt. */}
          {deal.preis_hinweis && !kuerzel && (
            <p className="text-[11px] leading-relaxed text-muted-foreground">
              {deal.preis_hinweis}
              {deal.preis_monat_eur != null && (
                <> — {formatAmount(deal.preis_monat_eur, "EUR")} im Monat</>
              )}
            </p>
          )}

          <GratisHinweis deal={deal} />

          {deal.kategorien_labels && deal.kategorien_labels.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {deal.kategorien_labels.map((name) => (
                <span key={name}
                      className="rounded-sm bg-muted/60 px-1.5 py-0.5 text-[10px]
                                 font-medium text-muted-foreground">
                  {name}
                </span>
              ))}
            </div>
          )}

          {deal.passt_weil && deal.passt_weil.length > 0 && (
            <p className="text-[11px] leading-relaxed text-primary/90"
               title="So kommt SparBit auf diesen Vorschlag">
              passt zu dir: {deal.passt_weil.join(", ")}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
            <span className="font-medium text-foreground/70">
              {sourceLabel(deal.quelle)}
            </span>
            {deal.also_from.length > 0 && (
              <button
                type="button"
                onClick={() => onOpen?.(deal.id)}
                title={`${deal.anzahl_angebote} Angebote — auch bei ${
                  deal.also_from.map(sourceLabel).join(", ")}`}
                className="text-primary transition-colors hover:underline"
              >
                +{deal.also_from.length}
              </button>
            )}
            {deal.haendler && (
              <>
                <span aria-hidden className="text-border">·</span>
                <span className="truncate">{deal.haendler}</span>
              </>
            )}
            <span className="ml-auto shrink-0 tabular">{timeAgo(deal.first_seen)}</span>
          </div>

          <div className="flex gap-1.5">
            <Button
              variant="outline"
              size="sm"
              className="flex-1"
              onClick={() => {
                window.open(deal.url, "_blank", "noopener,noreferrer");
                // Beim Öffnen gleich nachsehen, ob es den Deal noch gibt.
                // Für diesen Klick kommt die Antwort zu spät — für den
                // nächsten Blick auf den Feed nicht, und niemand sonst
                // läuft danach in dieselbe tote Seite.
                onPrueft?.(deal.id);
              }}
            >
              <ExternalLink className="h-3.5 w-3.5" />
              Zum Deal
            </Button>
            {onOpen && (
              <Button variant="ghost" size="sm" onClick={() => onOpen(deal.id)}
                      title="Preisverlauf und Alarm">
                <LineChart className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}
