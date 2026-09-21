import { BarChart3, Euro, PiggyBank, Signal, Store } from "lucide-react";
import * as React from "react";
import {
  api, type HaendlerStat, type QuellenStat, type Sparbilanz, type TimelinePoint,
} from "@/lib/api";
import { useAsync } from "@/lib/useEvents";
import { formatAmount, formatNumber, sourceLabel } from "@/lib/utils";
import { BarList, TimeSeries } from "@/components/charts";
import {
  Card, CardContent, CardHeader, CardTitle, Select, Skeleton,
} from "@/components/ui";
import { PageHeader } from "@/components/Layout";

const SERIES = [
  { key: "deals", label: "Deals gesammelt", color: "var(--viz-1)" },
  { key: "gratis", label: "davon gratis", color: "var(--viz-3)" },
  { key: "treffer", label: "Regeltreffer", color: "var(--viz-2)" },
];

export function Statistics() {
  const [tage, setTage] = React.useState(30);
  const { data: timeline, loading } = useAsync(
    () => api.statistik.timeline(tage), [tage]);
  const { data: quellen } = useAsync<QuellenStat[]>(
    () => api.statistik.quellen(tage), [tage]);
  const { data: haendler } = useAsync<HaendlerStat[]>(
    () => api.statistik.haendler(), []);

  const punkte = (timeline?.punkte ?? []) as unknown as Array<
    Record<string, string | number>>;

  const summe = React.useMemo(() => {
    const p = (timeline?.punkte ?? []) as TimelinePoint[];
    return {
      deals: p.reduce((a, x) => a + x.deals, 0),
      gratis: p.reduce((a, x) => a + x.gratis, 0),
      treffer: p.reduce((a, x) => a + x.treffer, 0),
      ersparnis: p.reduce((a, x) => a + x.ersparnis, 0),
    };
  }, [timeline]);

  return (
    <>
      <PageHeader
        title="Statistiken"
        description="Welche Quelle liefert Signal und welche nur Rauschen — die Grundlage zum Aufräumen."
        action={
          <div className="w-44">
            <Select value={String(tage)} onChange={(e) => setTage(Number(e.target.value))}>
              <option value="7">Letzte 7 Tage</option>
              <option value="30">Letzte 30 Tage</option>
              <option value="90">Letzte 90 Tage</option>
              <option value="180">Letzte 180 Tage</option>
            </Select>
          </div>
        }
      />

      <div className="mb-5 grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <Kachel icon={<BarChart3 className="h-4 w-4" />} label="Deals gesammelt"
                wert={formatNumber(summe.deals)} />
        <Kachel icon={<Signal className="h-4 w-4" />} label="Regeltreffer"
                wert={formatNumber(summe.treffer)}
                zusatz={summe.deals
                  ? `${((summe.treffer / summe.deals) * 100).toFixed(1)}% Signalanteil`
                  : undefined} />
        <Kachel icon={<Store className="h-4 w-4" />} label="Gratis-Funde"
                wert={formatNumber(summe.gratis)} akzent />
        <Kachel icon={<Euro className="h-4 w-4" />} label="Ersparnis gesamt"
                wert={formatAmount(summe.ersparnis)} />
      </div>

      <BilanzCard />

      <Card className="mb-5">
        <CardHeader>
          <CardTitle>Verlauf</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-56" />
          ) : (
            <TimeSeries points={punkte as never} series={SERIES} height={240} />
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2 lg:gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Quellen nach Ausbeute</CardTitle>
            <p className="text-xs text-muted-foreground">
              Der Signalanteil sagt, wie viel Prozent der Funde eine Regel
              getroffen haben. Dauerhaft niedrig heißt: Intervall hochsetzen
              oder Quelle abschalten.
            </p>
          </CardHeader>
          <CardContent>
            <BarList
              items={(quellen ?? []).map((q) => ({
                label: sourceLabel(q.quelle),
                value: q.deals,
                sub: `${q.signalquote}% Signal · ${q.gratis} gratis`,
              }))}
              emptyText="Noch keine Deals im gewählten Zeitraum."
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Häufigste Händler</CardTitle>
            <p className="text-xs text-muted-foreground">
              Mit dem durchschnittlichen Rabatt — nützlich für Händlerfilter
              in Regeln.
            </p>
          </CardHeader>
          <CardContent>
            <BarList
              items={(haendler ?? []).map((h) => ({
                label: h.haendler,
                value: h.anzahl,
                sub: h.schnitt_rabatt ? `⌀ −${h.schnitt_rabatt}%` : undefined,
              }))}
              emptyText="Noch keine Händler erkannt."
            />
          </CardContent>
        </Card>
      </div>
    </>
  );
}

function Kachel({
  icon, label, wert, zusatz, akzent,
}: {
  icon: React.ReactNode;
  label: string;
  wert: string;
  zusatz?: string;
  akzent?: boolean;
}) {
  return (
    <Card hover className="p-4 sm:p-5">
      <div className="flex items-center gap-2 text-muted-foreground">
        <span className={akzent ? "text-primary" : ""}>{icon}</span>
        <span className="truncate text-xs font-medium uppercase tracking-wide">
          {label}
        </span>
      </div>
      <p className="tabular mt-2.5 text-2xl font-semibold sm:text-3xl">{wert}</p>
      {zusatz && <p className="mt-1 text-xs text-muted-foreground">{zusatz}</p>}
    </Card>
  );
}


/** Was das Ganze unter dem Strich gebracht hat.
 *
 *  Die Daten dafür liegen seit dem ersten Tag da — beantwortet hat die
 *  Frage nur nie jemand. Die Zahl steht bewusst mit ihrer Einschränkung
 *  daneben: sie ist geschätzt, nicht abgerechnet. */
function BilanzCard() {
  const { data } = useAsync<Sparbilanz>(() => api.bilanz(365), []);
  if (!data) return <Skeleton className="mb-5 h-32" />;

  return (
    <Card className="mb-5">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <PiggyBank className="h-4 w-4 text-primary" />
          Deine Bilanz — letzte 12 Monate
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
          <Kachel icon={<Euro className="h-4 w-4" />} label="Geschätzt gespart"
                  wert={formatAmount(data.ersparnis_eur)} akzent />
          <Kachel icon={<Signal className="h-4 w-4" />} label="Gemerkte Artikel"
                  wert={formatNumber(data.beobachtete_deals)}
                  zusatz={data.ohne_verlauf
                    ? `${data.ohne_verlauf} ohne genug Verlauf`
                    : undefined} />
          <Kachel icon={<Store className="h-4 w-4" />} label="Gratis mitgenommen"
                  wert={formatNumber(data.gratis_mitgenommen)} />
          <Kachel icon={<BarChart3 className="h-4 w-4" />} label="Geclaimte Spiele"
                  wert={formatNumber(data.claims)} />
        </div>

        {data.top.length > 0 && (
          <ul className="space-y-1.5 border-t border-border pt-3">
            {data.top.slice(0, 5).map((eintrag) => (
              <li key={eintrag.id} className="flex items-baseline justify-between gap-3 text-sm">
                <a href={eintrag.url} target="_blank" rel="noreferrer noopener"
                   className="truncate text-primary hover:underline">
                  {eintrag.titel}
                </a>
                <span className="shrink-0 tabular text-success">
                  −{formatAmount(eintrag.gespart)}
                </span>
              </li>
            ))}
          </ul>
        )}

        <p className="text-xs leading-relaxed text-muted-foreground">
          {data.hinweis}
        </p>
      </CardContent>
    </Card>
  );
}
