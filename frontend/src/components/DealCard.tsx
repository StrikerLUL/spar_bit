import { Bookmark, ExternalLink, Flame, LineChart, Store } from "lucide-react";
import type { Deal } from "@/lib/api";
import { useSprache } from "@/lib/i18n";
import {
  bildQuelle, cn, eurHinweis, formatAmount, formatPrice, sourceLabel, timeAgo,
  zeigeStreichpreis,
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
}: {
  deal: Deal;
  onBookmark?: (id: number) => void;
  onOpen?: (id: number) => void;
}) {
  const { t } = useSprache();
  const rabatt = deal.rabatt_prozent;
  const streichpreis = zeigeStreichpreis(deal);
  const eur = eurHinweis(deal.preis_eur, deal.waehrung);
  const bild = bildQuelle(deal);

  return (
    <Card hover className="group flex flex-col overflow-hidden">
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
            <Store className="h-8 w-8" strokeWidth={1.25} aria-hidden />
          </div>
        )}

        {/* pr-10 haelt die Abzeichen vom Merken-Knopf frei: ohne das laeuft
            eine vierstellige Temperatur darunter und wird abgeschnitten. */}
        <div className="absolute left-2 top-2 flex flex-wrap gap-1 pr-10">
          <FehlerBadge stufe={deal.fehler_stufe} score={deal.fehler_score}
                       gruende={deal.fehler_gruende} />
          {deal.ist_gratis ? (
            <Badge variant="success">{t("gratis")}</Badge>
          ) : rabatt ? (
            <Badge variant="warning" className="tabular">
              −{Math.round(rabatt)}%
            </Badge>
          ) : null}
          <PruefBadge deal={deal} />
          {deal.temperatur != null && deal.temperatur >= 200 && (
            <Badge variant="outline"
                   className="tabular border-border bg-card/90 text-foreground">
              <Flame className="h-3 w-3" aria-hidden />
              {Math.round(deal.temperatur)}°
            </Badge>
          )}
          <UrteilBadge stufe={deal.urteil} text={deal.urteil_text} />
        </div>

        {onBookmark && (
          <button
            onClick={() => onBookmark(deal.id)}
            aria-label={t("merken")}
            aria-pressed={deal.bookmarked}
            title={t("merken")}
            className={cn(
              "absolute right-2 top-2 rounded-sm border border-border p-1.5",
              "bg-card/90 transition-colors hover:bg-card",
              deal.bookmarked ? "text-primary" : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Bookmark className={cn("h-3.5 w-3.5", deal.bookmarked && "fill-current")} aria-hidden />
          </button>
        )}
      </div>

      <div className="flex flex-1 flex-col gap-3 p-3.5">
        {onOpen ? (
          <button
            type="button"
            onClick={() => onOpen(deal.id)}
            className="line-clamp-2 text-left text-[13px] font-medium leading-snug transition-colors hover:text-primary"
            title={t("Details")}
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
              {deal.ist_gratis ? t("gratis") : formatPrice(deal.preis, deal.waehrung)}
            </span>
            {streichpreis && (
              <span className="tabular text-xs text-muted-foreground line-through decoration-muted-foreground/60">
                {/* Der Streichpreis ist durchgestrichen - ein Screenreader
                    sieht das nicht, also steht es im Text davor. */}
                <span className="sr-only">{t("statt")} </span>
                {formatAmount(deal.originalpreis, deal.waehrung)}
              </span>
            )}
            {eur && (
              <span className="tabular text-[11px] text-muted-foreground"
                    title={t("Umgerechnet mit dem hinterlegten Kurs")}>
                {eur}
              </span>
            )}
          </div>

          <GratisHinweis deal={deal} />

          {/* Ohne den Code stimmt der Preis daneben nicht - er gehoert
              darum direkt darunter und nicht in die Beschreibung, die
              gekuerzt wird. */}
          {deal.gutschein_code && (
            <p className="text-[11px] leading-relaxed">
              <span className="text-muted-foreground">{t("Gutschein-Code")}: </span>
              <code className="rounded-sm border border-border bg-muted/60 px-1 py-0.5 font-mono text-[11px] tracking-wide">
                {deal.gutschein_code}
              </code>
            </p>
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
              onClick={() => window.open(deal.url, "_blank", "noopener,noreferrer")}
            >
              <ExternalLink className="h-3.5 w-3.5" aria-hidden />
              {t("Zum Angebot")}
            </Button>
            {onOpen && (
              <Button variant="ghost" size="sm" onClick={() => onOpen(deal.id)}
                      title={t("Preisalarm")} aria-label={t("Preisalarm")}>
                <LineChart className="h-3.5 w-3.5" aria-hidden />
              </Button>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}
