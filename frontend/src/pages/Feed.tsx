import {
  Bookmark, Boxes, Download, Search, SlidersHorizontal, Star, Target, Trash2, X,
} from "lucide-react";
import * as React from "react";
import { api, type Deal, type SavedSearch, type Source } from "@/lib/api";
import { useAsync } from "@/lib/useEvents";
import { cn, sourceLabel } from "@/lib/utils";
import {
  Badge, Button, Card, EmptyState, Input, Label, Select, Skeleton, Switch,
} from "@/components/ui";
import { DealCard } from "@/components/DealCard";
import { KategorieLeiste } from "@/components/Kategorien";
import { DealDetailDialog } from "@/components/DealDetail";
import { PageHeader } from "@/components/Layout";
import { useToast } from "@/components/Toast";

const PAGE_SIZE = 60;

export function Feed() {
  const toast = useToast();
  const [query, setQuery] = React.useState("");
  const [debounced, setDebounced] = React.useState("");
  const [quelle, setQuelle] = React.useState("");
  const [kategorien, setKategorien] = React.useState<string[]>([]);
  const [nurGratis, setNurGratis] = React.useState(false);
  const [nurGemerkt, setNurGemerkt] = React.useState(false);
  // Vorgabe an: abgelaufene Deals sind der häufigste Ärger im Feed, und
  // ausgeblendet werden nur die, bei denen die Zielseite es selbst gesagt
  // hat — Ungeprüftes bleibt sichtbar.
  const [nurGueltig, setNurGueltig] = React.useState(true);
  const [minRabatt, setMinRabatt] = React.useState("");
  const [maxPreis, setMaxPreis] = React.useState("");
  const [urteil, setUrteil] = React.useState("");
  const [sortierung, setSortierung] = React.useState("neu");
  const [filtersOpen, setFiltersOpen] = React.useState(false);
  const [offset, setOffset] = React.useState(0);
  const [items, setItems] = React.useState<Deal[]>([]);
  const [detailId, setDetailId] = React.useState<number | null>(null);

  // Sucheingabe entprellen - sonst feuert jede Taste einen Request.
  React.useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query), 300);
    return () => window.clearTimeout(timer);
  }, [query]);

  const { data: sources } = useAsync<Source[]>(() => api.sources.list(), []);
  const { data: searches, reload: reloadSearches } =
    useAsync<SavedSearch[]>(() => api.searches.list(), []);

  const filters = React.useMemo(
    () => ({
      q: debounced || undefined,
      quelle: quelle || undefined,
      kategorie: kategorien.length ? kategorien.join(",") : undefined,
      nur_gratis: nurGratis,
      nur_gueltig: nurGueltig,
      bookmarked: nurGemerkt,
      min_rabatt: minRabatt ? Number(minRabatt) : undefined,
      max_preis: maxPreis ? Number(maxPreis) : undefined,
      urteil: urteil || undefined,
      sortierung,
    }),
    [debounced, quelle, kategorien, nurGratis, nurGueltig, nurGemerkt,
     minRabatt, maxPreis, urteil, sortierung],
  );

  // Filterwechsel setzt die Paginierung zurueck.
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

  const activeFilters =
    [quelle, nurGratis, nurGemerkt, minRabatt, maxPreis, urteil,
     !nurGueltig].filter(Boolean).length + kategorien.length;

  // Beim Öffnen eines Deals die Zielseite gegenprüfen und das Ergebnis in
  // die Karte zurückschreiben. Fehler bleiben still: das ist eine
  // Nebenbeschäftigung, kein Auftrag des Benutzers.
  const pruefen = async (id: number) => {
    try {
      const ergebnis = await api.deals.pruefen(id);
      setItems((current) =>
        current.map((d) => (d.id === id ? { ...d, ...ergebnis.deal } : d)));
    } catch {
      /* egal - der Link ist längst offen */
    }
  };

  const bookmark = async (id: number) => {
    try {
      const result = await api.deals.bookmark(id);
      // Merken ist das staerkste Signal fuer den lernenden Feed.
      void api.lernen.notiere(id, result.bookmarked ? "gemerkt" : "verworfen")
        .catch(() => undefined);
      setItems((current) =>
        current.map((d) => (d.id === id ? { ...d, bookmarked: result.bookmarked } : d)),
      );
    } catch (err) {
      toast.push("error", "Konnte nicht merken", (err as Error).message);
    }
  };

  const resetFilters = () => {
    setQuelle("");
    setKategorien([]);
    setNurGratis(false);
    setNurGemerkt(false);
    setNurGueltig(true);
    setMinRabatt("");
    setMaxPreis("");
    setUrteil("");
  };

  const sucheSpeichern = async () => {
    const name = window.prompt("Name für diese Suche?",
      query || quelle || (nurGratis ? "Nur Gratis" : "Meine Suche"));
    if (!name) return;
    try {
      await api.searches.create(name, {
        q: query, quelle, kategorie: kategorien.join(","),
        nur_gratis: nurGratis, bookmarked: nurGemerkt,
        min_rabatt: minRabatt, max_preis: maxPreis,
      });
      toast.push("success", "Suche gespeichert", name);
      reloadSearches();
    } catch (err) {
      toast.push("error", "Speichern fehlgeschlagen", (err as Error).message);
    }
  };

  const sucheAnwenden = (gespeichert: SavedSearch) => {
    const f = gespeichert.filter as Record<string, string | boolean>;
    setQuery(String(f.q ?? ""));
    setQuelle(String(f.quelle ?? ""));
    setKategorien(String(f.kategorie ?? "").split(",").filter(Boolean));
    setNurGratis(Boolean(f.nur_gratis));
    setNurGemerkt(Boolean(f.bookmarked));
    setMinRabatt(String(f.min_rabatt ?? ""));
    setMaxPreis(String(f.max_preis ?? ""));
  };

  return (
    <>
      <PageHeader
        title="Feed"
        description="Alles, was eingesammelt wurde — auch das, was keine Regel getroffen hat."
      />

      <Card className="mb-5 p-3 sm:p-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              data-suchfeld
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={'Suchen…  "genaue phrase"  -ausschluss  präfix*   (Taste /)'}
              className="pl-9"
              title={'Mehrere Wörter werden UND-verknüpft.\n'
                + '"nintendo switch" sucht die genaue Wortfolge.\n'
                + '-gebraucht schließt Treffer aus.\n'
                + 'kopfhör* findet auch Kopfhörern.'}
            />
          </div>
          <Button
            variant={filtersOpen || activeFilters ? "default" : "outline"}
            onClick={() => setFiltersOpen((open) => !open)}
          >
            <SlidersHorizontal className="h-4 w-4" />
            Filter
            {activeFilters > 0 && (
              <Badge variant="secondary" className="ml-1">{activeFilters}</Badge>
            )}
          </Button>
          <div className="flex gap-1 rounded-md bg-muted/40 p-1 text-xs">
            {([["neu", "Neueste"], ["guenstig", "Günstigste"],
               ["fuer_mich", "Für dich"]] as const).map(
              ([wert, label]) => (
                <button
                  key={wert}
                  type="button"
                  onClick={() => setSortierung(wert)}
                  className={cn(
                    "rounded px-2.5 py-1.5 font-medium transition-colors",
                    sortierung === wert
                      ? "bg-card text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {label}
                </button>
              ))}
          </div>
          <Button variant="ghost" size="icon" title="Als CSV herunterladen"
                  onClick={() => window.open(
                    api.csvUrl({ nur_gratis: nurGratis, nur_gemerkt: nurGemerkt }),
                    "_blank")}>
            <Download className="h-4 w-4" />
          </Button>
        </div>

        <div className="mt-3 border-t border-border pt-3">
          <KategorieLeiste ausgewaehlt={kategorien} onChange={setKategorien} />
        </div>

        {(searches?.length || activeFilters > 0 || query) && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-border pt-3">
            {searches?.map((gespeichert) => (
              <span key={gespeichert.id}
                    className="group flex items-center rounded-full border border-border text-xs">
                <button type="button" onClick={() => sucheAnwenden(gespeichert)}
                        className="py-1 pl-2.5 pr-1 hover:text-primary">
                  <Star className="mr-1 inline h-3 w-3" />
                  {gespeichert.name}
                </button>
                <button type="button" aria-label="Suche löschen"
                        onClick={async () => {
                          await api.searches.remove(gespeichert.id);
                          reloadSearches();
                        }}
                        className="py-1 pr-2 text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100">
                  <Trash2 className="h-3 w-3" />
                </button>
              </span>
            ))}
            {(activeFilters > 0 || query) && (
              <Button variant="ghost" size="sm" onClick={sucheSpeichern}>
                <Star className="h-3.5 w-3.5" />
                Suche merken
              </Button>
            )}
          </div>
        )}

        {filtersOpen && (
          <div className="mt-4 grid gap-4 border-t border-border pt-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="space-y-1.5">
              <Label>Quelle</Label>
              <Select value={quelle} onChange={(e) => setQuelle(e.target.value)}>
                <option value="">Alle Quellen</option>
                {sources?.map((source) => (
                  <option key={source.id} value={source.id}>
                    {source.display_name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Preisurteil</Label>
              <Select value={urteil} onChange={(e) => setUrteil(e.target.value)}>
                <option value="">egal</option>
                <option value="bestpreis">nur Bestpreise</option>
                <option value="sehr_gut">sehr gut oder besser</option>
                <option value="gut">gut oder besser</option>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Mindest-Rabatt (%)</Label>
              <Input
                type="number"
                min={0}
                max={100}
                value={minRabatt}
                placeholder="z. B. 80"
                onChange={(e) => setMinRabatt(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Höchstpreis (€)</Label>
              <Input
                type="number"
                min={0}
                step="0.01"
                value={maxPreis}
                placeholder="z. B. 25"
                onChange={(e) => setMaxPreis(e.target.value)}
              />
            </div>
            <div className="flex flex-col justify-center gap-3 pt-1">
              <label className="flex cursor-pointer items-center gap-2.5 text-sm">
                <Switch checked={nurGratis} onChange={setNurGratis} label="Nur gratis" />
                Nur gratis
              </label>
              <label className="flex cursor-pointer items-center gap-2.5 text-sm">
                <Switch checked={nurGemerkt} onChange={setNurGemerkt} label="Nur gemerkte" />
                Nur gemerkte
              </label>
              <label className="flex cursor-pointer items-center gap-2.5 text-sm"
                     title="Blendet aus, was die Zielseite selbst als abgelaufen
oder als anderen Preis gemeldet hat. Ungeprüftes bleibt sichtbar.">
                <Switch checked={nurGueltig} onChange={setNurGueltig}
                        label="Abgelaufene ausblenden" />
                Abgelaufene ausblenden
              </label>
            </div>
            {activeFilters > 0 && (
              <Button variant="ghost" size="sm" onClick={resetFilters}
                className="justify-self-start">
                <X className="h-3.5 w-3.5" />
                Filter zurücksetzen
              </Button>
            )}
          </div>
        )}
      </Card>

      {loading && offset === 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-80" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <Card>
          <EmptyState
            icon={nurGemerkt ? <Bookmark className="h-9 w-9" /> : <Boxes className="h-9 w-9" />}
            title={
              activeFilters || debounced
                ? "Nichts gefunden"
                : "Noch keine Deals gesammelt"
            }
            description={
              activeFilters || debounced
                ? "Andere Filter probieren — oder warten, bis mehr reinkommt."
                : "Schalte unter „Quellen“ etwas ein. Der erste Lauf startet dann binnen Sekunden."
            }
          />
        </Card>
      ) : (
        <>
          {sortierung === "fuer_mich" && data?.hinweis && (
            <Card className="mb-4 border-warning/30 bg-warning/5 p-3">
              <p className="text-xs leading-relaxed text-muted-foreground">
                <Target className="mr-1 inline h-3.5 w-3.5 text-primary" />
                {data.hinweis}
              </p>
            </Card>
          )}
          <p className="mb-4 text-sm text-muted-foreground">
            {data?.total ?? 0} Treffer
          </p>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {items.map((deal) => (
              <DealCard
                key={deal.id}
                deal={deal}
                onBookmark={bookmark}
                onPrueft={pruefen}
                onOpen={(id) => {
                  setDetailId(id);
                  void api.lernen.notiere(id, "geoeffnet").catch(() => undefined);
                }}
              />
            ))}
          </div>
          {data && items.length < data.total && (
            <div className="mt-6 flex justify-center">
              <Button
                variant="outline"
                loading={loading}
                onClick={() => setOffset(items.length)}
              >
                Weitere laden ({data.total - items.length} übrig)
              </Button>
            </div>
          )}
        </>
      )}

      {detailId !== null && (
        <DealDetailDialog
          dealId={detailId}
          onClose={() => setDetailId(null)}
          onChanged={() => {
            // Merk-Status in der Liste nachziehen, ohne alles neu zu laden.
            api.deals.list({ ...filters, limit: PAGE_SIZE, offset: 0 })
              .then((r) => setItems((cur) =>
                cur.map((d) => r.items.find((n) => n.id === d.id) ?? d)))
              .catch(() => undefined);
          }}
        />
      )}
    </>
  );
}

export { sourceLabel };
