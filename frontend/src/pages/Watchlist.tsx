import {
  AlertTriangle, CheckCircle2, ExternalLink, Eye, Plus, RefreshCw, Target,
  Trash2, XCircle,
} from "lucide-react";
import * as React from "react";
import { api, type WatchItem, type WatchTest } from "@/lib/api";
import { useAsync } from "@/lib/useEvents";
import { cn, formatPrice, timeAgo } from "@/lib/utils";
import { Sparkline } from "@/components/charts";
import {
  Badge, Button, Card, Dialog, EmptyState, Input, Label, Skeleton, Switch,
} from "@/components/ui";
import { PageHeader } from "@/components/Layout";
import { useToast } from "@/components/Toast";

export function Watchlist() {
  const toast = useToast();
  const { data, loading, reload } = useAsync<WatchItem[]>(() => api.watch.list(), []);
  const [anlegen, setAnlegen] = React.useState(false);
  const [detail, setDetail] = React.useState<number | null>(null);

  return (
    <>
      <PageHeader
        title="Wunschliste"
        description="Artikel, die SparBit selbst beobachtet — unabhängig davon, ob sie jemand als Deal postet."
        action={
          <Button onClick={() => setAnlegen(true)}>
            <Plus className="h-4 w-4" />
            Artikel beobachten
          </Button>
        }
      />

      {loading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-52" />)}
        </div>
      ) : !data?.length ? (
        <Card>
          <EmptyState
            icon={<Eye className="h-9 w-9" />}
            title="Noch nichts auf der Wunschliste"
            description="Trag einen Artikel mit seiner Shop-URL ein. SparBit liest den Preis aus den strukturierten Daten der Seite und meldet sich, wenn er fällt."
            action={
              <Button onClick={() => setAnlegen(true)}>
                <Plus className="h-4 w-4" />
                Ersten Artikel beobachten
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.map((eintrag) => (
            <WatchCard key={eintrag.id} eintrag={eintrag} onChanged={reload}
                       onOpen={() => setDetail(eintrag.id)} />
          ))}
        </div>
      )}

      {anlegen && (
        <AnlegenDialog
          onClose={() => setAnlegen(false)}
          onSaved={() => { setAnlegen(false); reload(); toast.push("success", "Aufgenommen"); }}
        />
      )}
      {detail !== null && (
        <DetailDialog id={detail} onClose={() => setDetail(null)} onChanged={reload} />
      )}
    </>
  );
}

function WatchCard({
  eintrag, onChanged, onOpen,
}: {
  eintrag: WatchItem;
  onChanged: () => void;
  onOpen: () => void;
}) {
  const toast = useToast();
  const [prueft, setPrueft] = React.useState(false);

  const jetztPruefen = async () => {
    setPrueft(true);
    try {
      const ergebnis = await api.watch.pruefen(eintrag.id);
      toast.push(ergebnis.ok ? "success" : "error",
        ergebnis.ok
          ? `${formatPrice(ergebnis.preis ?? null, ergebnis.waehrung)} (${ergebnis.verfahren})`
          : "Konnte nicht gelesen werden",
        ergebnis.fehler);
      onChanged();
    } finally {
      setPrueft(false);
    }
  };

  const gefallen = eintrag.bester_preis != null && eintrag.letzter_preis != null
    && eintrag.letzter_preis <= eintrag.bester_preis;

  return (
    <Card hover className="flex flex-col p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <button type="button" onClick={onOpen}
                  className="line-clamp-2 text-left text-sm font-medium hover:text-primary">
            {eintrag.name}
          </button>
          <p className="mt-0.5 text-xs text-muted-foreground">{eintrag.haendler}</p>
        </div>
        <Switch
          checked={eintrag.aktiv}
          label={`${eintrag.name} beobachten`}
          onChange={async (aktiv) => {
            await api.watch.update(eintrag.id, { ...eintrag, aktiv });
            onChanged();
          }}
        />
      </div>

      <div className="mt-3 flex flex-wrap items-baseline gap-2">
        <span className={cn("tabular text-xl font-semibold",
                            eintrag.ziel_erreicht && "text-primary")}>
          {formatPrice(eintrag.letzter_preis, eintrag.waehrung)}
        </span>
        {eintrag.ziel_preis != null && (
          <Badge variant={eintrag.ziel_erreicht ? "success" : "outline"}>
            <Target className="h-3 w-3" />
            Ziel {formatPrice(eintrag.ziel_preis)}
          </Badge>
        )}
        {/* Die Listenansicht liefert keinen Verlauf - der Vergleich laeuft
            ueber bester_preis, den sie mitgibt. */}
        {gefallen && eintrag.bester_preis != null && (
          <Badge variant="success">Tiefstand</Badge>
        )}
      </div>

      {eintrag.bester_preis != null && eintrag.letzter_preis != null
        && eintrag.bester_preis < eintrag.letzter_preis && (
        <p className="mt-1 text-xs text-muted-foreground">
          bisher günstigster beobachteter Preis: {formatPrice(eintrag.bester_preis,
                                                             eintrag.waehrung)}
        </p>
      )}

      {eintrag.letzter_fehler && (
        <p className="mt-3 break-words rounded-md bg-destructive/10 px-2.5 py-2 text-[11px] leading-relaxed text-destructive">
          <AlertTriangle className="mr-1 inline h-3 w-3" />
          {eintrag.letzter_fehler}
          {eintrag.fehler_in_folge >= 5 && " — pausiert."}
        </p>
      )}

      <div className="mt-auto flex flex-wrap gap-2 pt-4">
        <Button variant="outline" size="sm" loading={prueft} onClick={jetztPruefen}>
          <RefreshCw className="h-3.5 w-3.5" />
          Jetzt prüfen
        </Button>
        <Button variant="ghost" size="sm"
                onClick={() => window.open(eintrag.url, "_blank", "noopener,noreferrer")}
                title="Im Shop öffnen">
          <ExternalLink className="h-3.5 w-3.5" />
        </Button>
        <Button variant="ghost" size="sm" title="Entfernen"
                onClick={async () => {
                  if (!window.confirm(`„${eintrag.name}“ nicht mehr beobachten?`)) return;
                  await api.watch.remove(eintrag.id);
                  onChanged();
                }}>
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
        <span className="ml-auto self-center text-[11px] text-muted-foreground">
          {timeAgo(eintrag.letzter_erfolg ?? eintrag.letzter_lauf)}
        </span>
      </div>
    </Card>
  );
}

function AnlegenDialog({
  onClose, onSaved,
}: {
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [url, setUrl] = React.useState("");
  const [name, setName] = React.useState("");
  const [ziel, setZiel] = React.useState("");
  const [test, setTest] = React.useState<WatchTest | null>(null);
  const [prueft, setPrueft] = React.useState(false);
  const [speichert, setSpeichert] = React.useState(false);

  const testen = async () => {
    if (!url.trim()) return;
    setPrueft(true);
    setTest(null);
    try {
      const ergebnis = await api.watch.testen(url.trim());
      setTest(ergebnis);
      if (ergebnis.ok && ergebnis.name && !name) setName(ergebnis.name);
    } catch (err) {
      setTest({ ok: false, fehler: (err as Error).message });
    } finally {
      setPrueft(false);
    }
  };

  const speichern = async () => {
    setSpeichert(true);
    try {
      const rohZiel = ziel.trim().replace(",", ".");
      await api.watch.create({
        name: name.trim() || url,
        url: url.trim(),
        ziel_preis: rohZiel ? Number(rohZiel) : null,
        intervall_minuten: 180,
        aktiv: true,
      });
      onSaved();
    } catch (err) {
      toast.push("error", "Anlegen fehlgeschlagen", (err as Error).message);
    } finally {
      setSpeichert(false);
    }
  };

  return (
    <Dialog
      open onClose={onClose}
      title="Artikel beobachten"
      description="SparBit liest den Preis aus den strukturierten Daten der Seite — denselben, die Shops für Suchmaschinen ausliefern."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Abbrechen</Button>
          <Button onClick={speichern} loading={speichert}
                  disabled={!url.trim() || test?.ok === false}>
            Aufnehmen
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="space-y-1.5">
          <Label>Adresse der Produktseite</Label>
          <div className="flex gap-2">
            <Input value={url} autoFocus placeholder="https://shop.de/artikel/…"
                   onChange={(e) => setUrl(e.target.value)}
                   onBlur={testen} className="font-mono text-xs" />
            <Button variant="outline" onClick={testen} loading={prueft}>
              Prüfen
            </Button>
          </div>
        </div>

        {test && (
          <div className={cn("rounded-md px-3 py-2.5 text-xs leading-relaxed",
                             test.ok ? "bg-success/10 text-success"
                                     : "bg-destructive/10 text-destructive")}>
            {test.ok ? (
              <>
                <p className="flex items-center gap-1.5 font-medium">
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  {formatPrice(test.preis ?? null, test.waehrung)} gelesen
                  aus {test.verfahren}
                </p>
                {test.name && <p className="mt-1 text-muted-foreground">{test.name}</p>}
              </>
            ) : (
              <>
                <p className="flex items-center gap-1.5 font-medium">
                  <XCircle className="h-3.5 w-3.5" />
                  Nicht lesbar
                </p>
                <p className="mt-1">{test.fehler}</p>
              </>
            )}
          </div>
        )}

        <div className="space-y-1.5">
          <Label>Name</Label>
          <Input value={name} placeholder="wird beim Prüfen übernommen"
                 onChange={(e) => setName(e.target.value)} />
        </div>

        <div className="space-y-1.5">
          <Label>Zielpreis (optional)</Label>
          <Input type="number" step="0.01" min={0} value={ziel}
                 placeholder="z. B. 199,00"
                 onChange={(e) => setZiel(e.target.value)} />
          <p className="text-xs leading-relaxed text-muted-foreground">
            Ohne Ziel meldet SparBit, wenn der Preis deutlich unter das bisher
            beobachtete Minimum fällt.
          </p>
        </div>
      </div>
    </Dialog>
  );
}

function DetailDialog({
  id, onClose, onChanged,
}: {
  id: number;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { data, loading } = useAsync<WatchItem>(() => api.watch.einzeln(id), [id]);
  const preise = (data?.verlauf ?? []).map((p) => p.preis);

  return (
    <Dialog open onClose={onClose} title={data?.name ?? "Artikel"}
            description={data?.haendler ?? undefined}
            footer={
              <>
                <Button variant="ghost" onClick={onClose}>Schließen</Button>
                {data && (
                  <Button onClick={() => window.open(data.url, "_blank", "noopener,noreferrer")}>
                    <ExternalLink className="h-4 w-4" />
                    Im Shop öffnen
                  </Button>
                )}
              </>
            }>
      {loading || !data ? (
        <Skeleton className="h-48" />
      ) : (
        <div className="space-y-5">
          <div className="flex items-baseline gap-3">
            <span className="tabular text-2xl font-semibold">
              {formatPrice(data.letzter_preis, data.waehrung)}
            </span>
            {data.ziel_preis != null && (
              <Badge variant={data.ziel_erreicht ? "success" : "outline"}>
                Ziel {formatPrice(data.ziel_preis)}
              </Badge>
            )}
          </div>

          <section className="space-y-2">
            <h3 className="text-sm font-medium">Preisverlauf</h3>
            <Sparkline values={preise} />
            {preise.length > 1 && (
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>Tiefst: <span className="tabular text-foreground">
                  {formatPrice(Math.min(...preise), data.waehrung)}</span></span>
                <span>Höchst: <span className="tabular text-foreground">
                  {formatPrice(Math.max(...preise), data.waehrung)}</span></span>
                <span>{preise.length} Messungen</span>
              </div>
            )}
          </section>

          <dl className="space-y-1.5 text-xs">
            <Zeile label="Intervall" wert={`alle ${Math.round(data.intervall_minuten / 60)} Std.`} />
            <Zeile label="Zuletzt geprüft" wert={timeAgo(data.letzter_lauf)} />
            <Zeile label="Zuletzt erfolgreich" wert={timeAgo(data.letzter_erfolg)} />
            <Zeile label="Beobachtet seit" wert={timeAgo(data.erstellt_am)} />
          </dl>

          <Button variant="outline" size="sm" className="w-full"
                  onClick={async () => {
                    await api.watch.pruefen(data.id);
                    onChanged();
                  }}>
            <RefreshCw className="h-3.5 w-3.5" />
            Jetzt prüfen
          </Button>
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
