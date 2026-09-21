import { Eye, EyeOff, Lock, Search, ShieldAlert } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { api, type Deal, type ErwachsenStatus, type Source } from "@/lib/api";
import { useAsync } from "@/lib/useEvents";
import { cn } from "@/lib/utils";
import {
  Button, Card, EmptyState, Input, Label, Select, Skeleton, Switch,
} from "@/components/ui";
import { DealCard } from "@/components/DealCard";
import { KategorieLeiste } from "@/components/Kategorien";
import { DealDetailDialog } from "@/components/DealDetail";
import { PageHeader } from "@/components/Layout";
import { useToast } from "@/components/Toast";

const PAGE_SIZE = 60;

/** Der 18+-Bereich.
 *
 *  Eine eigene Seite und kein Filter im Feed — das ist der ganze Punkt.
 *  Was hier steht, steht nirgendwo sonst: nicht in der Übersicht, nicht in
 *  der Suche, nicht in den Statistiken, nicht in der Empfehlung. Und ohne
 *  Freischaltung unter *Logs & System* gibt es die Seite gar nicht, auch
 *  nicht für jemanden, der die Adresse kennt — die API antwortet dann 403.
 */
export function Erwachsen() {
  const toast = useToast();
  const { data: status, loading: statusLaedt, reload: statusNeu } =
    useAsync<ErwachsenStatus>(() => api.system.erwachsen(), []);

  if (statusLaedt) {
    return <Skeleton className="h-40 w-full" />;
  }
  if (!status?.an) {
    return <Gesperrt onFrei={statusNeu} />;
  }
  return <Liste status={status} onStatus={statusNeu} toast={toast} />;
}

function Gesperrt({ onFrei }: { onFrei: () => void }) {
  return (
    <>
      <PageHeader
        title="18+"
        description="Ein getrennter Bereich für Angebote ab 18. Standardmäßig aus."
      />
      <Card className="mx-auto max-w-xl p-8 text-center">
        <Lock className="mx-auto h-8 w-8 text-muted-foreground/40" strokeWidth={1.5} />
        <p className="mt-4 font-medium">Dieser Bereich ist nicht freigeschaltet.</p>
        <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted-foreground">
          Solange er aus ist, gibt es die zugehörigen Quellen nicht, es wird
          nichts eingesammelt und nichts gemeldet. Freischalten kannst du ihn
          unter <span className="font-medium text-foreground">Logs &amp; System</span>;
          dort steht auch die Altersbestätigung.
        </p>
        <Link to="/system" onClick={onFrei}
              className="mt-5 inline-flex h-9 items-center justify-center rounded-md
                         border border-border px-4 text-sm font-medium
                         transition-colors hover:bg-accent">
          Zu Logs &amp; System
        </Link>
      </Card>
    </>
  );
}

function Liste({
  status, onStatus, toast,
}: {
  status: ErwachsenStatus;
  onStatus: () => void;
  toast: ReturnType<typeof useToast>;
}) {
  const [query, setQuery] = React.useState("");
  const [debounced, setDebounced] = React.useState("");
  const [quelle, setQuelle] = React.useState("");
  const [kategorien, setKategorien] = React.useState<string[]>([]);
  const [nurGratis, setNurGratis] = React.useState(false);
  const [maxPreis, setMaxPreis] = React.useState("");
  const [maxProMonat, setMaxProMonat] = React.useState("");
  const [minRabatt, setMinRabatt] = React.useState("");
  const [sortierung, setSortierung] = React.useState("neu");
  const [nurGueltig, setNurGueltig] = React.useState(true);
  const [offset, setOffset] = React.useState(0);
  const [items, setItems] = React.useState<Deal[]>([]);
  const [detailId, setDetailId] = React.useState<number | null>(null);
  // Vorbelegt aus der Einstellung, danach ein Schalter nur für diese Sitzung.
  const [unscharf, setUnscharf] = React.useState(status.unscharf);

  React.useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query), 300);
    return () => window.clearTimeout(timer);
  }, [query]);

  const { data: sources } = useAsync<Source[]>(() => api.sources.list(), []);
  const eigeneQuellen = (sources ?? []).filter((s) => s.erwachsen);

  const filters = React.useMemo(
    () => ({
      bereich: "erwachsen",
      q: debounced || undefined,
      quelle: quelle || undefined,
      kategorie: kategorien.length ? kategorien.join(",") : undefined,
      nur_gratis: nurGratis,
      nur_gueltig: nurGueltig,
      max_preis: maxPreis ? Number(maxPreis) : undefined,
      // Abos vergleichen sich über den Monatspreis, nicht über das
      // Preisschild: "1 € für 3 Monate" ist günstiger als "0,99 € im Monat".
      max_preis_monat: maxProMonat ? Number(maxProMonat) : undefined,
      min_rabatt: minRabatt ? Number(minRabatt) : undefined,
      sortierung,
    }),
    [debounced, quelle, kategorien, nurGratis, nurGueltig, maxPreis,
     maxProMonat, minRabatt, sortierung],
  );

  React.useEffect(() => {
    setOffset(0);
    setItems([]);
  }, [filters]);

  const { data, loading } = useAsync(
    () => api.deals.list({ ...filters, limit: PAGE_SIZE, offset }),
    [filters, offset],
  );

  React.useEffect(() => {
    if (!data) return;
    setItems((current) => (offset === 0 ? data.items : [...current, ...data.items]));
  }, [data, offset]);

  const pruefen = async (id: number) => {
    try {
      const ergebnis = await api.deals.pruefen(id);
      setItems((current) =>
        current.map((d) => (d.id === id ? { ...d, ...ergebnis.deal } : d)));
    } catch {
      /* egal - der Link ist längst offen */
    }
  };

  const merken = async (id: number) => {
    try {
      const ergebnis = await api.deals.bookmark(id);
      setItems((current) =>
        current.map((d) => (d.id === id ? { ...d, bookmarked: ergebnis.bookmarked } : d)));
    } catch (err) {
      toast.push("error", "Konnte nicht merken", (err as Error).message);
    }
  };

  const unscharfMerken = async (an: boolean) => {
    setUnscharf(an);
    try {
      await api.system.erwachsenOptionen({ unscharf: an });
      onStatus();
    } catch {
      /* Anzeige ist schon umgestellt - das Speichern ist Beiwerk. */
    }
  };

  return (
    <>
      <PageHeader
        title="18+"
        description={
          eigeneQuellen.length
            ? `${eigeneQuellen.filter((q) => q.enabled).length} von ${
                eigeneQuellen.length} eigenen Quellen eingeschaltet. ` +
              "Diese Funde erscheinen nirgendwo sonst in SparBit."
            : "Diese Funde erscheinen nirgendwo sonst in SparBit."
        }
        action={
          <label className="flex cursor-pointer items-center gap-2.5 text-sm">
            <Switch checked={unscharf} onChange={unscharfMerken}
                    label="Bilder verdecken" />
            {unscharf ? <EyeOff className="h-3.5 w-3.5" />
                      : <Eye className="h-3.5 w-3.5" />}
            Bilder verdecken
          </label>
        }
      />

      {!eigeneQuellen.some((q) => q.enabled) && (
        <Card className="mb-5 flex items-start gap-3 border-warning/40 bg-warning/10 p-4">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          <div className="min-w-0 text-sm">
            <p className="font-medium">Noch keine eigene Quelle eingeschaltet.</p>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              Unter <Link to="/quellen" className="text-primary hover:underline">
              Quellen</Link> stehen jetzt drei zusätzliche. Keine davon konnte
              beim Bauen live geprüft werden — drück dort erst „Jetzt testen“.
              Was hier trotzdem schon auftaucht, hat SparBit anhand der
              Stichwörter aus den normalen Quellen aussortiert.
            </p>
          </div>
        </Card>
      )}

      <Card className="mb-5 p-3">
        <div className="flex flex-wrap items-end gap-3">
          <div className="relative min-w-[200px] flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2
                               h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input value={query} onChange={(e) => setQuery(e.target.value)}
                   placeholder="Suchen…" className="pl-8" />
          </div>
          <div className="w-44">
            <Label className="mb-1 block text-xs">Quelle</Label>
            <Select value={quelle} onChange={(e) => setQuelle(e.target.value)}>
              <option value="">Alle</option>
              {eigeneQuellen.map((s) => (
                <option key={s.id} value={s.id}>{s.display_name}</option>
              ))}
            </Select>
          </div>
          <div className="w-28">
            <Label className="mb-1 block text-xs">Max. €</Label>
            <Input type="number" min="0" value={maxPreis}
                   onChange={(e) => setMaxPreis(e.target.value)} placeholder="—" />
          </div>
          <div className="w-32">
            <Label className="mb-1 block text-xs" title="Zeigt nur laufende
Angebote — Abos, Mitgliedschaften, Zugänge — und rechnet den Preis auf den
Monat um.">Max. €/Monat</Label>
            <Input type="number" min="0" step="0.01" value={maxProMonat}
                   onChange={(e) => setMaxProMonat(e.target.value)}
                   placeholder="—" />
          </div>
          <div className="w-40">
            <Label className="mb-1 block text-xs">Sortierung</Label>
            <Select value={sortierung}
                    onChange={(e) => setSortierung(e.target.value)}>
              <option value="neu">Neueste zuerst</option>
              <option value="guenstig">Günstigste zuerst</option>
              <option value="rabatt">Höchster Rabatt</option>
            </Select>
          </div>
          <div className="w-28">
            <Label className="mb-1 block text-xs">Min. %</Label>
            <Input type="number" min="0" max="100" value={minRabatt}
                   onChange={(e) => setMinRabatt(e.target.value)} placeholder="—" />
          </div>
          <label className="flex cursor-pointer items-center gap-2.5 pb-2 text-sm">
            <Switch checked={nurGratis} onChange={setNurGratis} label="Nur gratis" />
            nur gratis
          </label>
          <label className="flex cursor-pointer items-center gap-2.5 pb-2 text-sm"
                 title="Blendet aus, was die Zielseite als abgelaufen meldet.">
            <Switch checked={nurGueltig} onChange={setNurGueltig}
                    label="Abgelaufene ausblenden" />
            abgelaufene aus
          </label>
        </div>

        <div className="mt-3 border-t border-border pt-3">
          <KategorieLeiste bereich="erwachsen" ausgewaehlt={kategorien}
                           onChange={setKategorien} nurGueltig={nurGueltig} />
        </div>
      </Card>

      {loading && items.length === 0 ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-72" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={<Lock className="h-8 w-8" strokeWidth={1.25} />}
          title="Noch nichts gefunden"
          description="Sobald eine 18+-Quelle läuft oder eine normale Quelle
                       etwas Passendes meldet, steht es hier."
        />
      ) : (
        <>
          <div className={cn("grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4",
                             unscharf && "sparbit-verdeckt")}>
            {items.map((deal) => (
              <DealCard key={deal.id} deal={deal} onBookmark={merken}
                        onPrueft={pruefen} onOpen={setDetailId} />
            ))}
          </div>
          {data && items.length < data.total && (
            <div className="mt-5 flex justify-center">
              <Button variant="outline" onClick={() => setOffset(offset + PAGE_SIZE)}
                      disabled={loading}>
                {loading ? "Lädt…" : `Mehr laden (${items.length} von ${data.total})`}
              </Button>
            </div>
          )}
        </>
      )}

      {detailId !== null && (
        <DealDetailDialog dealId={detailId} onClose={() => setDetailId(null)} />
      )}
    </>
  );
}
