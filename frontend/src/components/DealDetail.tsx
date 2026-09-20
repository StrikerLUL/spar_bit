import {
  Bell, BellOff, Bookmark, Check, ExternalLink, SearchCheck, TrendingDown,
} from "lucide-react";
import * as React from "react";
import { api, type Angebot, type DealDetail as Detail } from "@/lib/api";
import { useAsync } from "@/lib/useEvents";
import {
  bildQuelle, cn, formatAmount, formatDateTime, formatPrice, sourceLabel,
  timeAgo, zeigeStreichpreis,
} from "@/lib/utils";
import { Sparkline } from "@/components/charts";
import { Badge, Button, Dialog, Input, Label, Skeleton } from "@/components/ui";
import { useToast } from "@/components/Toast";
import { FehlerBegruendung } from "@/components/Preisfehler";
import { PruefBadge } from "@/components/Gratischeck";

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

  const [prueft, setPrueft] = React.useState(false);

  /** Die Zielseite jetzt aufrufen - wenn man es selbst wissen will. */
  const nachsehen = async () => {
    setPrueft(true);
    try {
      const { befund, korrigiert } = await api.deals.pruefen(dealId);
      toast.push(
        befund.status === "widerlegt" || befund.status === "abgelaufen"
          ? "error" : "success",
        befund.label,
        korrigiert ? `${befund.text} Preis korrigiert.` : befund.text,
      );
      reload();
      onChanged?.();
    } catch (err) {
      toast.push("error", "Nachsehen fehlgeschlagen", (err as Error).message);
    } finally {
      setPrueft(false);
    }
  };

  // Der Verlauf wird in Euro gezeichnet: sonst entsteht beim Wechsel der
  // guenstigsten Quelle (EUR -> USD) ein Sprung, den es nie gegeben hat.
  const preise = (data?.verlauf ?? [])
    .map((p) => p.preis_eur ?? p.preis)
    .filter((v): v is number => v != null);
  const gefallen = preise.length > 1 && preise[preise.length - 1] < preise[0];

  return (
    <Dialog open onClose={onClose} wide
            title={data?.titel ?? "Deal"}
            description={data ? `${sourceLabel(data.quelle)}${data.haendler ? ` · ${data.haendler}` : ""}` : undefined}
            footer={
              <>
                <Button variant="ghost" onClick={onClose}>Schließen</Button>
                {data && (
                  <Button onClick={() => window.open(
                    data.beste_url || data.url, "_blank", "noopener,noreferrer")}>
                    <ExternalLink className="h-4 w-4" />
                    {data.angebote.length > 1 ? "Zum besten Angebot" : "Zum Deal"}
                  </Button>
                )}
              </>
            }>
      {loading || !data ? (
        <Skeleton className="h-72" />
      ) : (
        <div className="grid gap-6 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="space-y-4">
            {bildQuelle(data) && (
              <img src={bildQuelle(data)!} alt="" loading="lazy"
                   className="max-h-52 w-full rounded-md object-cover"
                   onError={(e) => { e.currentTarget.style.display = "none"; }} />
            )}
            <div className="flex flex-wrap items-baseline gap-2">
              <span className={cn("tabular text-2xl font-semibold tracking-tight",
                                  data.ist_gratis && "text-success")}>
                {data.ist_gratis ? "gratis" : formatPrice(data.preis, data.waehrung)}
              </span>
              {/* formatAmount statt formatPrice: ein Streichpreis von 0,00
                  wäre sonst als "gratis" durchgestrichen zu lesen. */}
              {zeigeStreichpreis(data) && (
                <span className="tabular text-sm text-muted-foreground line-through">
                  {formatAmount(data.originalpreis, data.waehrung)}
                </span>
              )}
              {data.rabatt_prozent != null && !data.ist_gratis && (
                <Badge variant="warning" className="tabular">
                  −{Math.round(data.rabatt_prozent)}%
                </Badge>
              )}
            </div>

            <FehlerBegruendung stufe={data.fehler_stufe} score={data.fehler_score}
                               gruende={data.fehler_gruende} />
            {/* Der grosse Preis ist der beste ueber alle Quellen - ohne
                diesen Hinweis wirkt er wie der Preis der Kopfzeilen-Quelle. */}
            {data.angebote.length > 1 && (
              <p className="-mt-2 text-xs text-muted-foreground">
                bester Preis bei{" "}
                <a href={data.beste_url} target="_blank" rel="noopener noreferrer"
                   className="text-primary hover:underline">
                  {sourceLabel(data.beste_quelle)}
                </a>
              </p>
            )}
            {data.waehrung !== "EUR" && data.preis_eur != null && (
              <p className="text-xs text-muted-foreground">
                entspricht {formatAmount(data.preis_eur)} — Regeln, Urteil und
                Preisfehler-Prüfung rechnen mit diesem Wert.
              </p>
            )}
            {data.beschreibung && (
              <p className="text-sm leading-relaxed text-muted-foreground">
                {data.beschreibung.slice(0, 500)}
              </p>
            )}
            <div className="flex flex-wrap gap-1.5">
              {(data.tags ?? []).slice(0, 6).map((t) => (
                <Badge key={t} variant="outline">{t}</Badge>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button variant={data.bookmarked ? "default" : "outline"} size="sm"
                      onClick={merken}>
                <Bookmark className={cn("h-3.5 w-3.5", data.bookmarked && "fill-current")} />
                {data.bookmarked ? "Gemerkt" : "Merken"}
              </Button>
              <Button variant="outline" size="sm" onClick={nachsehen}
                      loading={prueft}
                      title="Die Zielseite jetzt aufrufen und den Preis gegenprüfen">
                <SearchCheck className="h-3.5 w-3.5" />
                Nachsehen
              </Button>
              <PruefBadge deal={data} />
            </div>
            {data.check_text && (
              <p className="text-xs leading-relaxed text-muted-foreground">
                {data.check_text}
                {data.check_am && (
                  <span className="ml-1 text-muted-foreground/70">
                    ({timeAgo(data.check_am)})
                  </span>
                )}
              </p>
            )}
          </div>

          <div className="space-y-5">
            <Angebote angebote={data.angebote} />

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
                    {formatPrice(data.tiefstpreis, "EUR")}</span></span>
                  <span>Höchst: <span className="tabular text-foreground">
                    {formatPrice(data.hoechstpreis, "EUR")}</span></span>
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


/** Preisvergleich: dieselbe Sache, verschiedene Quellen, verschiedene Preise.
 *  Sortiert nach dem Euro-Betrag, damit USD-Angebote fair einsortiert sind. */
function Angebote({ angebote }: { angebote: Angebot[] }) {
  if (angebote.length <= 1) return null;

  const guenstigster = angebote[0];   // Backend liefert bereits sortiert

  return (
    <section className="space-y-2">
      <h3 className="text-sm font-medium">
        Preisvergleich{" "}
        <span className="font-normal text-muted-foreground">
          ({angebote.length} Quellen)
        </span>
      </h3>
      <div className="overflow-hidden rounded-md border border-border">
        <table className="w-full text-xs">
          <tbody className="divide-y divide-border">
            {angebote.map((angebot) => {
              const bester = angebot === guenstigster;
              return (
                <tr key={angebot.quelle}
                    className={cn(bester && "bg-primary/5")}>
                  <td className="px-2.5 py-2">
                    <div className="flex items-center gap-1.5">
                      {bester && <Check className="h-3 w-3 shrink-0 text-primary" />}
                      <span className={cn("truncate", bester && "font-medium")}>
                        {sourceLabel(angebot.quelle)}
                      </span>
                    </div>
                    {angebot.haendler && (
                      <span className="text-[10px] text-muted-foreground">
                        {angebot.haendler}
                      </span>
                    )}
                  </td>
                  <td className="px-2.5 py-2 text-right">
                    <span className={cn("tabular font-medium",
                                        bester && "text-primary")}>
                      {angebot.ist_gratis
                        ? "gratis"
                        : formatPrice(angebot.preis, angebot.waehrung)}
                    </span>
                    {/* Fremdwaehrung: den Euro-Wert dazuschreiben, sonst kann
                        man die Zeilen nicht vergleichen. */}
                    {angebot.waehrung !== "EUR" && angebot.preis_eur != null && (
                      <span className="block text-[10px] text-muted-foreground">
                        ≈ {formatPrice(angebot.preis_eur)}
                      </span>
                    )}
                  </td>
                  <td className="w-8 px-1.5 py-2 text-right">
                    <a href={angebot.url} target="_blank" rel="noopener noreferrer"
                       title={`Bei ${sourceLabel(angebot.quelle)} öffnen`}
                       className="inline-flex text-muted-foreground hover:text-primary">
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {guenstigster.waehrung !== "EUR" && (
        <p className="text-[11px] text-muted-foreground">
          Vergleich rechnet in Euro — Kurse unter Benachrichtigungen anpassbar.
        </p>
      )}
    </section>
  );
}
