import {
  AlertTriangle, BellOff, CheckCircle2, ExternalLink, RefreshCw, ShieldCheck,
  ShieldOff, Target,
} from "lucide-react";
import * as React from "react";
import {
  api, type AppSettings, type Deal, type PreisfehlerAuswertung,
  type PreisfehlerListe,
} from "@/lib/api";
import { useAsync } from "@/lib/useEvents";
import {
  bildQuelle, cn, eurHinweis, formatAmount, formatPrice, sourceLabel, timeAgo,
  zeigeStreichpreis,
} from "@/lib/utils";
import {
  Badge, Button, Card, EmptyState, Select, Skeleton, Slider, Switch,
} from "@/components/ui";
import { PageHeader } from "@/components/Layout";
import { FehlerBegruendung } from "@/components/Preisfehler";
import { useToast } from "@/components/Toast";
import { DealDetailDialog } from "@/components/DealDetail";

/** Die Preisfehler-Seite.
 *
 *  Anders sortiert als der Feed: nicht nach Datum, sondern nach
 *  Überzeugungskraft. Bei einem Preisfehler ist die Frage nicht "was ist
 *  neu", sondern "woran glaube ich genug, um es jetzt zu bestellen".
 */
export function Preisfehler() {
  const [tage, setTage] = React.useState(7);
  const [nurHeiss, setNurHeiss] = React.useState(false);
  const [offen, setOffen] = React.useState<number | null>(null);
  const [stand, setStand] = React.useState(0);
  const toast = useToast();

  const { data, loading } = useAsync<PreisfehlerListe>(
    () => api.preisfehler.list(tage, nurHeiss), [tage, nurHeiss, stand]);

  const neu = () => setStand((n) => n + 1);

  const alsEcht = async (deal: Deal) => {
    try {
      const raus = await api.preisfehler.rueckmeldung(deal.id, "echt");
      toast.push("success",
        raus.urteil_mensch ? "Als echter Fehler vermerkt" : "Rückmeldung zurückgenommen",
        deal.titel.slice(0, 60));
      neu();
    } catch (err) {
      toast.push("error", "Ging nicht", (err as Error).message);
    }
  };

  const verwerfen = async (deal: Deal) => {
    await api.preisfehler.verwerfen(deal.id);
    toast.push("info", "Als Fehlalarm abgehakt", deal.titel.slice(0, 60));
    neu();
  };

  const pruefen = async (deal: Deal) => {
    const urteil = await api.preisfehler.pruefen(deal.id);
    toast.push("info", `Neu bewertet: ${urteil.label}`,
              `${urteil.punkte} von 100 Punkten`);
    neu();
  };

  const funde = data?.items ?? [];
  const heiss = funde.filter((d) => d.fehler_stufe === "heiss");
  const verdacht = funde.filter((d) => d.fehler_stufe === "verdacht");

  return (
    <>
      <PageHeader
        title="Preisfehler"
        description="Preise, die kein Rabatt erklärt. Nach Überzeugungskraft sortiert, nicht nach Datum."
        action={
          <div className="flex items-center gap-2">
            <Select value={String(tage)}
                    onChange={(e) => setTage(Number(e.target.value))}
                    className="w-auto">
              <option value="1">24 Stunden</option>
              <option value="3">3 Tage</option>
              <option value="7">7 Tage</option>
              <option value="30">30 Tage</option>
            </Select>
            <Button variant="outline" size="sm" onClick={neu} title="Neu laden">
              <RefreshCw className="h-3.5 w-3.5" />
            </Button>
          </div>
        }
      />

      <Waechter aktiv={data?.waechter_aktiv} schwelle={data?.schwelle} />

      <div className="mb-4 mt-6 flex flex-wrap items-center gap-2">
        <Button variant={nurHeiss ? "default" : "outline"} size="sm"
                onClick={() => setNurHeiss(!nurHeiss)}>
          <AlertTriangle className="h-3.5 w-3.5" />
          Nur belegte Fälle
        </Button>
        <span className="tabular text-xs text-muted-foreground">
          {heiss.length} belegt · {verdacht.length} Verdacht
        </span>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => <Skeleton key={i} className="h-36 w-full" />)}
        </div>
      ) : funde.length === 0 ? (
        <Card>
          <EmptyState
            icon={<ShieldCheck className="h-8 w-8" strokeWidth={1.25} />}
            title="Nichts Auffälliges"
            description={
              "In diesem Zeitraum hat kein Preis einen Fehler nahegelegt. " +
              "Das ist der Normalfall — echte Preisfehler sind selten, und " +
              "ein Wächter, der täglich anschlägt, wäre falsch eingestellt."
            }
          />
        </Card>
      ) : (
        <div className="space-y-3">
          {funde.map((deal) => (
            <Fund key={deal.id} deal={deal}
                  onOeffnen={() => setOffen(deal.id)}
                  onVerwerfen={() => verwerfen(deal)}
                  onEcht={() => alsEcht(deal)}
                  onPruefen={() => pruefen(deal)} />
          ))}
        </div>
      )}

      {offen !== null && (
        <DealDetailDialog dealId={offen} onClose={() => setOffen(null)}
                          onChanged={neu} />
      )}
    </>
  );
}


/** Kopfzeile: läuft der Wächter überhaupt, und wie empfindlich? */
function Waechter({ aktiv, schwelle }: { aktiv?: boolean; schwelle?: number }) {
  const [settings, setSettings] = React.useState<AppSettings | null>(null);
  const [offen, setOffen] = React.useState(false);
  const toast = useToast();

  React.useEffect(() => {
    api.settings.get().then(setSettings).catch(() => undefined);
  }, [aktiv, schwelle]);

  const speichern = async (patch: Partial<AppSettings>) => {
    if (!settings) return;
    const neu = { ...settings, ...patch };
    setSettings(neu);
    await api.settings.set(neu);
    toast.push("success", "Gespeichert");
  };

  if (!settings) return <Skeleton className="h-14 w-full" />;

  const an = settings.preisfehler_waechter;

  return (
    <Card className={cn("overflow-hidden", an ? "border-signal/35" : undefined)}>
      <div className="flex flex-wrap items-center gap-3 p-3.5">
        {an ? (
          <ShieldCheck className="h-4 w-4 shrink-0 text-signal" />
        ) : (
          <ShieldOff className="h-4 w-4 shrink-0 text-muted-foreground" />
        )}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">
            Wächter {an ? "aktiv" : "aus"}
          </p>
          <p className="text-xs text-muted-foreground">
            {an
              ? `Meldet ab ${settings.preisfehler_schwelle} von 100 Punkten sofort — ` +
                "an Regeln und Ruhezeiten vorbei."
              : "Preisfehler landen nur im Feed. Keine Sofortmeldung."}
          </p>
        </div>
        <button type="button" onClick={() => setOffen(!offen)}
                className="text-xs text-muted-foreground underline-offset-4 hover:underline">
          {offen ? "schließen" : "einstellen"}
        </button>
        <Switch checked={an} label="Preisfehler-Wächter"
                onChange={(v) => speichern({ preisfehler_waechter: v })} />
      </div>

      {offen && (
        <div className="border-t border-border bg-muted/20 p-3.5">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="label">Empfindlichkeit</p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Niedriger heisst mehr Meldungen, darunter mehr Fehlalarme.
              </p>
            </div>
            <span className="tabular text-lg font-semibold">
              {settings.preisfehler_schwelle}
            </span>
          </div>
          <Slider
            className="mt-3"
            min={30}
            max={100}
            step={5}
            value={settings.preisfehler_schwelle}
            onChange={(v) => setSettings({ ...settings, preisfehler_schwelle: v })}
          />
          <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
            <span>30 — kaum etwas entgeht dir</span>
            <span>100 — nur eindeutige Fälle</span>
          </div>
          <Button size="sm" className="mt-3"
                  onClick={() => speichern({
                    preisfehler_schwelle: settings.preisfehler_schwelle })}>
            Schwelle speichern
          </Button>

          <Eichung schwelleSetzen={(wert) =>
            speichern({ preisfehler_schwelle: wert })} />
        </div>
      )}
    </Card>
  );
}


/** Was die Rückmeldungen über die eigenen Gewichte sagen.
 *
 *  Die Gewichte des Wächters sind begründet, aber am Schreibtisch gewählt.
 *  Erst die Rückmeldungen zeigen, welche Indizien mit diesen Quellen
 *  tatsächlich taugen. Ein Vorschlag wird gemacht, nie etwas von selbst
 *  verstellt — dafür ist die Datenlage zu dünn und die Folge zu ärgerlich.
 */
function Eichung({ schwelleSetzen }: { schwelleSetzen: (wert: number) => void }) {
  const { data } = useAsync<PreisfehlerAuswertung>(
    () => api.preisfehler.auswertung(), []);
  const toast = useToast();

  /** Über den Server übernehmen statt lokal zu rechnen: so nennt die
   *  Meldung den alten Wert — und damit den Weg zurück. */
  const uebernehmen = async () => {
    try {
      const bericht = await api.preisfehler.schwelleUebernehmen();
      schwelleSetzen(bericht.jetzt);
      toast.push("success", `Schwelle ${bericht.vorher} → ${bericht.jetzt}`,
        `${bericht.grund} Zurück geht über das Feld darüber.`);
    } catch (err) {
      toast.push("error", "Übernehmen fehlgeschlagen", (err as Error).message);
    }
  };

  if (!data) return null;

  return (
    <div className="mt-4 border-t border-border pt-3.5">
      <p className="label flex items-center gap-1.5">
        <Target className="h-3.5 w-3.5 text-primary" />
        Eichung
      </p>

      {data.beurteilt === 0 ? (
        <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
          Noch keine Rückmeldungen. Klick bei einem Fund auf „Echter Fehler"
          oder „Fehlalarm" — daraus lernt der Wächter, welche Indizien bei
          deinen Quellen taugen.
        </p>
      ) : (
        <>
          <p className="mt-1.5 text-xs text-muted-foreground">
            {data.echt} echt · {data.fehlalarm} Fehlalarm
            {" "}({data.beurteilt} beurteilt)
          </p>

          {data.indizien.length > 0 && (
            <ul className="mt-2.5 space-y-1.5">
              {data.indizien.map((i) => (
                <li key={i.schluessel} className="text-xs">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="truncate">{i.name}</span>
                    <span className={cn(
                      "tabular shrink-0 font-medium",
                      i.treffsicherheit >= 70 ? "text-success"
                        : i.treffsicherheit >= 40 ? "text-warning"
                          : "text-destructive")}>
                      {i.treffsicherheit} %
                    </span>
                  </div>
                  <div className="mt-1 h-1 overflow-hidden rounded-full bg-muted">
                    <div className="h-full rounded-full bg-primary"
                         style={{ width: `${i.treffsicherheit}%` }} />
                  </div>
                  <span className="text-[10px] text-muted-foreground">
                    {i.echt} echt / {i.fehlalarm} Fehlalarm
                  </span>
                </li>
              ))}
            </ul>
          )}

          <div className="mt-3 rounded-md bg-muted/40 px-3 py-2">
            <p className="text-xs leading-relaxed text-muted-foreground">
              {data.vorschlag_grund}
            </p>
            {data.vorschlag !== null && (
              <Button size="sm" variant="outline" className="mt-2"
                      onClick={() => void uebernehmen()}>
                Schwelle auf {data.vorschlag} setzen
              </Button>
            )}
          </div>
        </>
      )}
    </div>
  );
}


/** Ein Fund als breite Zeile — Bild klein, Begründung gross. */
function Fund({
  deal, onOeffnen, onVerwerfen, onPruefen, onEcht,
}: {
  deal: Deal;
  onOeffnen: () => void;
  onVerwerfen: () => void;
  onEcht: () => void;
  onPruefen: () => void;
}) {
  const heiss = deal.fehler_stufe === "heiss";
  const bild = bildQuelle(deal);
  const eur = eurHinweis(deal.preis_eur, deal.waehrung);
  const erwartet = deal.fehler_erwartet_eur;

  return (
    <Card className={cn("overflow-hidden", heiss && "border-signal/45")}>
      {heiss && <div className="streifen h-1 w-full border-b border-signal/40" aria-hidden />}

      <div className="flex flex-col gap-4 p-4 sm:flex-row">
        <div className="flex gap-4 sm:w-64 sm:shrink-0 sm:flex-col">
          {bild && (
            <img src={bild} alt="" loading="lazy"
                 className="h-20 w-28 shrink-0 rounded-sm border border-border object-cover sm:h-32 sm:w-full"
                 onError={(e) => {
                   (e.currentTarget as HTMLImageElement).style.display = "none";
                 }} />
          )}
          <div className="min-w-0">
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span className="tabular text-2xl font-semibold leading-none tracking-tight">
                {formatPrice(deal.preis, deal.waehrung)}
              </span>
              {zeigeStreichpreis(deal) && (
                <span className="tabular text-xs text-muted-foreground line-through">
                  {formatAmount(deal.originalpreis, deal.waehrung)}
                </span>
              )}
            </div>
            {eur && (
              <p className="tabular mt-0.5 text-[11px] text-muted-foreground">{eur}</p>
            )}
            {erwartet != null && (
              <p className="tabular mt-1.5 text-xs text-muted-foreground">
                erwartet:{" "}
                <span className="font-medium text-foreground/80">
                  {formatAmount(erwartet, "EUR")}
                </span>
              </p>
            )}
          </div>
        </div>

        <div className="min-w-0 flex-1 space-y-3">
          <div>
            <button type="button" onClick={onOeffnen}
                    className="text-left text-sm font-medium leading-snug hover:text-primary">
              {deal.titel}
            </button>
            <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
              <Badge variant="outline">{sourceLabel(deal.quelle)}</Badge>
              {deal.haendler && <span className="truncate">{deal.haendler}</span>}
              <span aria-hidden className="text-border">·</span>
              <span className="tabular">{timeAgo(deal.first_seen)}</span>
              {deal.fehler_gemeldet_am && (
                <>
                  <span aria-hidden className="text-border">·</span>
                  <span className="text-muted-foreground/80">gemeldet</span>
                </>
              )}
            </div>
          </div>

          <FehlerBegruendung stufe={deal.fehler_stufe} score={deal.fehler_score}
                             gruende={deal.fehler_gruende} />

          <div className="flex flex-wrap gap-1.5">
            <Button variant={heiss ? "signal" : "default"} size="sm"
                    onClick={() => window.open(deal.url, "_blank", "noopener,noreferrer")}>
              <ExternalLink className="h-3.5 w-3.5" />
              Zum Händler
            </Button>
            <Button variant="outline" size="sm" onClick={onOeffnen}>
              Verlauf
            </Button>
            <Button variant="ghost" size="sm" onClick={onPruefen}
                    title="Mit dem aktuellen Wissensstand neu bewerten">
              <RefreshCw className="h-3.5 w-3.5" />
              Neu prüfen
            </Button>
            <Button
              variant={deal.urteil_mensch === "echt" ? "signal" : "ghost"}
              size="sm" onClick={onEcht}
              title="War wirklich ein Preisfehler — daraus lernt der Wächter">
              <CheckCircle2 className="h-3.5 w-3.5" />
              Echter Fehler
            </Button>
            <Button variant="ghost" size="sm" onClick={onVerwerfen}
                    title="Kein Preisfehler — nicht mehr melden">
              <BellOff className="h-3.5 w-3.5" />
              Fehlalarm
            </Button>
          </div>
        </div>
      </div>
    </Card>
  );
}
