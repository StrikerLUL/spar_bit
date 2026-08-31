import {
  Activity, Euro, Gift, Radio, Target, TrendingUp, Zap,
} from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { api, type Deal, type Stats } from "@/lib/api";
import { useAsync } from "@/lib/useEvents";
import { cn, formatAmount, formatNumber, formatPrice, sourceLabel, timeAgo } from "@/lib/utils";
import {
  Badge, Card, CardContent, CardHeader, CardTitle, EmptyState, Skeleton, StatusDot,
} from "@/components/ui";
import { PageHeader } from "@/components/Layout";

/** Deals, die live per SSE reinkommen. Der Ticker aktualisiert ohne Reload. */
export interface LiveItem extends Partial<Deal> {
  id: number;
  titel: string;
  url: string;
  quelle: string;
  regel?: string;
  prioritaet?: string;
  _at: number;
}

export function Dashboard({ live }: { live: LiveItem[] }) {
  const { data: stats, loading } = useAsync<Stats>(() => api.stats(), []);
  const { data: matches } = useAsync(() => api.matches(12), []);

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Was gerade reinkommt — und ob deine Quellen gesund sind."
      />

      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <Tile
          icon={<Target className="h-4 w-4" />}
          label="Treffer heute"
          value={loading ? null : formatNumber(stats?.treffer_heute)}
          hint={`${formatNumber(stats?.deals_heute)} Deals gesammelt`}
        />
        <Tile
          icon={<Gift className="h-4 w-4" />}
          label="Gratis diese Woche"
          value={loading ? null : formatNumber(stats?.gratis_diese_woche)}
          hint="0-€-Funde"
          accent
        />
        <Tile
          icon={<Euro className="h-4 w-4" />}
          label="Gespart (7 Tage)"
          value={loading ? null : formatAmount(stats?.gesparter_betrag ?? 0)}
          hint="Summe über Regeltreffer"
        />
        <Tile
          icon={<Radio className="h-4 w-4" />}
          label="Quellen"
          value={
            loading ? null : (
              <span className="flex items-center gap-2">
                {stats?.quellen_ampel.gruen ?? 0}
                <span className="text-sm font-normal text-muted-foreground">
                  / {(stats?.quellen_ampel.gruen ?? 0) +
                     (stats?.quellen_ampel.gelb ?? 0) +
                     (stats?.quellen_ampel.rot ?? 0)}
                </span>
              </span>
            )
          }
          hint={
            stats ? (
              <span className="flex items-center gap-2.5">
                <Ampel status="ok" count={stats.quellen_ampel.gruen} />
                <Ampel status="warn" count={stats.quellen_ampel.gelb} />
                <Ampel status="error" count={stats.quellen_ampel.rot} />
                <Ampel status="off" count={stats.quellen_ampel.aus} />
              </span>
            ) : undefined
          }
        />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-3 lg:gap-6">
        {/* Live-Ticker */}
        <Card className="lg:col-span-2">
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-primary" />
              Live-Ticker
            </CardTitle>
            <Badge variant="outline">{live.length} in dieser Sitzung</Badge>
          </CardHeader>
          <CardContent className="p-0">
            {live.length === 0 ? (
              <EmptyState
                icon={<Zap className="h-8 w-8" />}
                title="Noch nichts reingekommen"
                description="Sobald eine Quelle etwas Neues findet, erscheint es hier — ohne Neuladen."
              />
            ) : (
              <ul className="divide-y divide-border">
                {live.slice(0, 14).map((item, index) => (
                  <li
                    key={`${item.id}-${item._at}-${index}`}
                    className="flex items-center gap-3 px-5 py-2.5 animate-slide-up sm:px-6"
                  >
                    <StatusDot
                      status={item.regel ? "ok" : "off"}
                      pulse={index === 0}
                    />
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="min-w-0 flex-1 truncate text-sm transition-colors hover:text-primary"
                      title={item.titel}
                    >
                      {item.titel}
                    </a>
                    {item.regel && (
                      <Badge
                        variant={item.prioritaet === "SOFORT" ? "warning" : "default"}
                        className="hidden shrink-0 sm:inline-flex"
                      >
                        {item.regel}
                      </Badge>
                    )}
                    <span className="tabular shrink-0 text-xs font-medium">
                      {item.ist_gratis ? (
                        <span className="text-primary">gratis</span>
                      ) : (
                        formatPrice(item.preis ?? null, item.waehrung ?? "EUR")
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <div className="space-y-4 lg:space-y-6">
          {/* Top-Quellen */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-primary" />
                Aktivste Quellen
              </CardTitle>
            </CardHeader>
            <CardContent>
              {!stats?.top_quellen.length ? (
                <p className="text-sm text-muted-foreground">
                  Noch keine Daten. Schalte unter{" "}
                  <Link to="/quellen" className="text-primary hover:underline">
                    Quellen
                  </Link>{" "}
                  etwas ein.
                </p>
              ) : (
                <ul className="space-y-2.5">
                  {stats.top_quellen.map((entry) => {
                    const max = stats.top_quellen[0].anzahl || 1;
                    return (
                      <li key={entry.quelle} className="space-y-1">
                        <div className="flex justify-between text-xs">
                          <span className="truncate">{sourceLabel(entry.quelle)}</span>
                          <span className="tabular text-muted-foreground">
                            {entry.anzahl}
                          </span>
                        </div>
                        <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                          <div
                            className="h-full rounded-full bg-primary/70 transition-all duration-700"
                            style={{ width: `${(entry.anzahl / max) * 100}%` }}
                          />
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </CardContent>
          </Card>

          {/* Letzte Regeltreffer */}
          <Card>
            <CardHeader>
              <CardTitle>Letzte Regeltreffer</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {!matches?.length ? (
                <p className="px-5 pb-5 text-sm text-muted-foreground sm:px-6 sm:pb-6">
                  Noch keine Treffer.{" "}
                  <Link to="/regeln" className="text-primary hover:underline">
                    Regel anlegen
                  </Link>
                </p>
              ) : (
                <ul className="divide-y divide-border">
                  {matches.slice(0, 6).map((match, i) => (
                    <li key={`${match.id}-${i}`} className="px-5 py-2.5 sm:px-6">
                      <a
                        href={match.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="line-clamp-1 text-sm hover:text-primary"
                      >
                        {match.titel}
                      </a>
                      <div className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground">
                        <span className="truncate">{match.regel}</span>
                        <span className="ml-auto shrink-0">
                          {timeAgo(match.created_at)}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}

const Ampel = ({
  status,
  count,
}: {
  status: "ok" | "warn" | "error" | "off";
  count: number;
}) => (
  <span className="inline-flex items-center gap-1">
    <StatusDot status={status} />
    <span className="tabular">{count}</span>
  </span>
);

function Tile({
  icon,
  label,
  value,
  hint,
  accent,
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode | null;
  hint?: React.ReactNode;
  accent?: boolean;
}) {
  return (
    <Card hover className="overflow-hidden">
      <div className="p-4 sm:p-5">
        <div className="flex items-center gap-2 text-muted-foreground">
          <span className={cn(accent && "text-primary")}>{icon}</span>
          <span className="truncate text-xs font-medium uppercase tracking-wide">
            {label}
          </span>
        </div>
        <div className="mt-2.5 text-2xl font-semibold tabular sm:text-3xl">
          {value === null ? <Skeleton className="h-8 w-20" /> : value}
        </div>
        {hint && (
          <div className="mt-1.5 text-xs text-muted-foreground">{hint}</div>
        )}
      </div>
    </Card>
  );
}
