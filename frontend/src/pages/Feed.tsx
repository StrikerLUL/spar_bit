import { Boxes, Bookmark, Search, SlidersHorizontal, X } from "lucide-react";
import * as React from "react";
import { api, type Deal, type Source } from "@/lib/api";
import { useAsync } from "@/lib/useEvents";
import { sourceLabel } from "@/lib/utils";
import {
  Badge, Button, Card, EmptyState, Input, Label, Select, Skeleton, Switch,
} from "@/components/ui";
import { DealCard } from "@/components/DealCard";
import { PageHeader } from "@/components/Layout";
import { useToast } from "@/components/Toast";

const PAGE_SIZE = 60;

export function Feed() {
  const toast = useToast();
  const [query, setQuery] = React.useState("");
  const [debounced, setDebounced] = React.useState("");
  const [quelle, setQuelle] = React.useState("");
  const [nurGratis, setNurGratis] = React.useState(false);
  const [nurGemerkt, setNurGemerkt] = React.useState(false);
  const [minRabatt, setMinRabatt] = React.useState("");
  const [maxPreis, setMaxPreis] = React.useState("");
  const [filtersOpen, setFiltersOpen] = React.useState(false);
  const [offset, setOffset] = React.useState(0);
  const [items, setItems] = React.useState<Deal[]>([]);

  // Sucheingabe entprellen - sonst feuert jede Taste einen Request.
  React.useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query), 300);
    return () => window.clearTimeout(timer);
  }, [query]);

  const { data: sources } = useAsync<Source[]>(() => api.sources.list(), []);

  const filters = React.useMemo(
    () => ({
      q: debounced || undefined,
      quelle: quelle || undefined,
      nur_gratis: nurGratis,
      bookmarked: nurGemerkt,
      min_rabatt: minRabatt ? Number(minRabatt) : undefined,
      max_preis: maxPreis ? Number(maxPreis) : undefined,
    }),
    [debounced, quelle, nurGratis, nurGemerkt, minRabatt, maxPreis],
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
    [quelle, nurGratis, nurGemerkt, minRabatt, maxPreis].filter(Boolean).length;

  const bookmark = async (id: number) => {
    try {
      const result = await api.deals.bookmark(id);
      setItems((current) =>
        current.map((d) => (d.id === id ? { ...d, bookmarked: result.bookmarked } : d)),
      );
    } catch (err) {
      toast.push("error", "Konnte nicht merken", (err as Error).message);
    }
  };

  const resetFilters = () => {
    setQuelle("");
    setNurGratis(false);
    setNurGemerkt(false);
    setMinRabatt("");
    setMaxPreis("");
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
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Titel, Beschreibung oder Händler durchsuchen…"
              className="pl-9"
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
        </div>

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
          <p className="mb-4 text-sm text-muted-foreground">
            {data?.total ?? 0} Treffer
          </p>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {items.map((deal) => (
              <DealCard key={deal.id} deal={deal} onBookmark={bookmark} />
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
    </>
  );
}

export { sourceLabel };
