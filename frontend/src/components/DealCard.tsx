import { Bookmark, ExternalLink, Flame, Store } from "lucide-react";
import type { Deal } from "@/lib/api";
import { cn, formatPrice, sourceLabel, timeAgo } from "@/lib/utils";
import { Badge, Button, Card } from "@/components/ui";

export function DealCard({
  deal,
  onBookmark,
}: {
  deal: Deal;
  onBookmark?: (id: number) => void;
}) {
  const discount = deal.rabatt_prozent;
  return (
    <Card hover className="group flex flex-col overflow-hidden">
      <div className="relative aspect-[16/9] overflow-hidden bg-muted/40">
        {deal.bild ? (
          <img
            src={deal.bild}
            alt=""
            loading="lazy"
            className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.04]"
            onError={(e) => {
              // Kaputte Bild-URLs sind bei Feeds normal - Platzhalter statt Bruch.
              (e.currentTarget as HTMLImageElement).style.display = "none";
            }}
          />
        ) : (
          <div className="flex h-full items-center justify-center text-muted-foreground/30">
            <Store className="h-10 w-10" />
          </div>
        )}

        <div className="absolute left-2.5 top-2.5 flex flex-wrap gap-1.5">
          {deal.ist_gratis ? (
            <Badge variant="success" className="shadow-lg">GRATIS</Badge>
          ) : discount ? (
            <Badge variant="warning" className="shadow-lg">−{Math.round(discount)}%</Badge>
          ) : null}
          {deal.temperatur != null && deal.temperatur >= 200 && (
            <Badge variant="destructive" className="shadow-lg">
              <Flame className="h-3 w-3" />
              {Math.round(deal.temperatur)}°
            </Badge>
          )}
        </div>

        {onBookmark && (
          <button
            onClick={() => onBookmark(deal.id)}
            aria-label={deal.bookmarked ? "Merkung entfernen" : "Merken"}
            className={cn(
              "absolute right-2.5 top-2.5 rounded-full p-2 backdrop-blur-md transition-all",
              "bg-black/40 hover:bg-black/60",
              deal.bookmarked ? "text-primary" : "text-white/70 hover:text-white",
            )}
          >
            <Bookmark className={cn("h-4 w-4", deal.bookmarked && "fill-current")} />
          </button>
        )}
      </div>

      <div className="flex flex-1 flex-col gap-3 p-4">
        <a
          href={deal.url}
          target="_blank"
          rel="noopener noreferrer"
          className="line-clamp-2 text-sm font-medium leading-snug transition-colors hover:text-primary"
          title={deal.titel}
        >
          {deal.titel}
        </a>

        <div className="mt-auto space-y-3">
          <div className="flex items-baseline gap-2">
            <span
              className={cn(
                "tabular text-lg font-semibold",
                deal.ist_gratis && "text-primary",
              )}
            >
              {deal.ist_gratis ? "gratis" : formatPrice(deal.preis, deal.waehrung)}
            </span>
            {deal.originalpreis != null &&
              deal.preis != null &&
              deal.originalpreis > deal.preis && (
                <span className="tabular text-xs text-muted-foreground line-through">
                  {formatPrice(deal.originalpreis, deal.waehrung)}
                </span>
              )}
          </div>

          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
            <Badge variant="outline">{sourceLabel(deal.quelle)}</Badge>
            {deal.also_from.length > 0 && (
              <span title={`Auch gemeldet von: ${deal.also_from.join(", ")}`}>
                +{deal.also_from.length}
              </span>
            )}
            {deal.haendler && <span className="truncate">{deal.haendler}</span>}
            <span className="ml-auto shrink-0">{timeAgo(deal.first_seen)}</span>
          </div>

          <Button
            variant="outline"
            size="sm"
            className="w-full"
            onClick={() => window.open(deal.url, "_blank", "noopener,noreferrer")}
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Zum Deal
          </Button>
        </div>
      </div>
    </Card>
  );
}
