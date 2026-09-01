import { Bell, BellOff, Bookmark, ExternalLink, TrendingDown } from "lucide-react";
import * as React from "react";
import { api, type DealDetail as Detail } from "@/lib/api";
import { useAsync } from "@/lib/useEvents";
import { cn, formatDateTime, formatPrice, sourceLabel, timeAgo } from "@/lib/utils";
import { Sparkline } from "@/components/charts";
import { Badge, Button, Dialog, Input, Label, Skeleton } from "@/components/ui";
import { useToast } from "@/components/Toast";

export function DealDetailDialog({
  dealId,
  onClose,
  onChanged,
}: {
  dealId: number;
  onClose: () => void;
  onChanged?: () => void;
}) {
  const toast = useToast();
  const { data, loading, reload } = useAsync<Detail>(() => api.detail(dealId), [dealId]);
  const [ziel, setZiel] = React.useState("");
  const [speichert, setSpeichert] = React.useState(false);

  React.useEffect(() => {
    if (data) setZiel(data.alarm_preis != null ? String(data.alarm_preis) : "");
  }, [data]);

  const setzeAlarm = async (entfernen = false) => {
    setSpeichert(true);
    try {
      const wert = entfernen || ziel === "" ? null : Number(ziel);
      await api.alarm(dealId, wert);
      toast.push("success", entfernen ? "Preisalarm entfernt"
        : `Alarm bei ${formatPrice(wert)} gesetzt`);
      reload();
      onChanged?.();
    } catch (err) {
      toast.push("error", "Alarm fehlgeschlagen", (err as Error).message);
    } finally {
      setSpeichert(false);
    }
  };

  const merken = async () => {
    await api.deals.bookmark(dealId);
    reload();
    onChanged?.();
  };

  const preise = (data?.verlauf ?? []).map((p) => p.preis);
  const gefallen = preise.length > 1 && preise[preise.length - 1] < preise[0];

  return (
    <Dialog open onClose={onClose} wide
            title={data?.titel ?? "Deal"}
            description={data ? `${sourceLabel(data.quelle)}${data.haendler ? ` · ${data.haendler}` : ""}` : undefined}
            footer={
              <>
                <Button variant="ghost" onClick={onClose}>Schließen</Button>
                {data && (
                  <Button onClick={() => window.open(data.url, "_blank", "noopener,noreferrer")}>
                    <ExternalLink className="h-4 w-4" />
                    Zum Deal
                  </Button>
                )}
              </>
            }>
      {loading || !data ? (
        <Skeleton className="h-72" />
      ) : (
        <div className="grid gap-6 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="space-y-4">
            {data.bild && (
              <img src={data.bild} alt="" loading="lazy"
                   className="max-h-52 w-full rounded-md object-cover"
                   onError={(e) => { e.currentTarget.style.display = "none"; }} />
            )}
            <div className="flex flex-wrap items-baseline gap-2">
              <span className={cn("tabular text-2xl font-semibold",
                                  data.ist_gratis && "text-primary")}>
                {data.ist_gratis ? "gratis" : formatPrice(data.preis, data.waehrung)}
              </span>
              {data.originalpreis != null && data.preis != null
                && data.originalpreis > data.preis && (
                <span className="tabular text-sm text-muted-foreground line-through">
                  {formatPrice(data.originalpreis, data.waehrung)}
                </span>
              )}
              {data.rabatt_prozent != null && (
                <Badge variant="warning">−{Math.round(data.rabatt_prozent)}%</Badge>
              )}
            </div>
            {data.waehrung !== "EUR" && data.preis_eur != null && (
              <p className="text-xs text-muted-foreground">
                entspricht {formatPrice(data.preis_eur)} — Regeln rechnen mit
                diesem Wert.
              </p>
            )}
            {data.beschreibung && (
              <p className="text-sm leading-relaxed text-muted-foreground">
                {data.beschreibung.slice(0, 500)}
              </p>
            )}
            <div className="flex flex-wrap gap-1.5">
              <Badge variant="outline">{sourceLabel(data.quelle)}</Badge>
              {data.also_from.map((q) => (
                <Badge key={q} variant="secondary">auch: {sourceLabel(q)}</Badge>
              ))}
              {(data.tags ?? []).slice(0, 6).map((t) => (
                <Badge key={t} variant="outline">{t}</Badge>
              ))}
            </div>
            <Button variant={data.bookmarked ? "default" : "outline"} size="sm"
                    onClick={merken}>
              <Bookmark className={cn("h-3.5 w-3.5", data.bookmarked && "fill-current")} />
              {data.bookmarked ? "Gemerkt" : "Merken"}
            </Button>
          </div>

          <div className="space-y-5">
            <section className="space-y-2">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium">Preisverlauf</h3>
                {gefallen && (
                  <span className="flex items-center gap-1 text-xs text-primary">
                    <TrendingDown className="h-3.5 w-3.5" />
                    gefallen
                  </span>
                )}
              </div>
              <Sparkline values={preise} />
              {preise.length > 1 && (
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>Tiefst: <span className="tabular text-foreground">
                    {formatPrice(data.tiefstpreis, data.waehrung)}</span></span>
                  <span>Höchst: <span className="tabular text-foreground">
                    {formatPrice(data.hoechstpreis, data.waehrung)}</span></span>
                  <span>{preise.length} Messungen</span>
                </div>
              )}
            </section>

            <section className="space-y-2 rounded-md border border-border p-3">
              <div className="flex items-center gap-2">
                <Bell className="h-4 w-4 text-primary" />
                <h3 className="text-sm font-medium">Preisalarm</h3>
              </div>
              <p className="text-xs leading-relaxed text-muted-foreground">
                Melden, sobald der Preis auf oder unter diesen Wert fällt.
                Löst genau einmal aus.
              </p>
              <div className="flex gap-2">
                <div className="flex-1">
                  <Label className="sr-only">Zielpreis</Label>
                  <Input type="number" min={0} step="0.01" value={ziel}
                         placeholder="z. B. 19,99"
                         onChange={(e) => setZiel(e.target.value)} />
                </div>
                <Button size="sm" onClick={() => setzeAlarm()} loading={speichert}>
                  Setzen
                </Button>
                {data.alarm_preis != null && (
                  <Button size="sm" variant="ghost" onClick={() => setzeAlarm(true)}
                          aria-label="Alarm entfernen">
                    <BellOff className="h-3.5 w-3.5" />
                  </Button>
                )}
              </div>
              {data.alarm_preis != null && (
                <p className="text-xs text-primary">
                  Aktiv bei {formatPrice(data.alarm_preis)}
                  {data.alarm_ausgeloest &&
                    ` · ausgelöst ${timeAgo(data.alarm_ausgeloest)}`}
                </p>
              )}
            </section>

            <dl className="space-y-1.5 text-xs">
              <Zeile label="Zuerst gesehen" wert={formatDateTime(data.first_seen)} />
              <Zeile label="Zuletzt gesehen" wert={timeAgo(data.last_seen)} />
              <Zeile label="Gemeldet" wert={`${data.seen_count}×`} />
              {data.temperatur != null && (
                <Zeile label="Temperatur" wert={`${Math.round(data.temperatur)}°`} />
              )}
              {data.regeltreffer.length > 0 && (
                <Zeile label="Regeln"
                       wert={data.regeltreffer.map((r) => r.regel).join(", ")} />
              )}
            </dl>
          </div>
        </div>
      )}
    </Dialog>
  );
}

const Zeile = ({ label, wert }: { label: string; wert: string }) => (
  <div className="flex justify-between gap-3">
    <dt className="text-muted-foreground">{label}</dt>
    <dd className="truncate text-right">{wert}</dd>
  </div>
);
