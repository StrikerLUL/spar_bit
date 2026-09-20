import {
  CheckCircle2, Gift, Play, RefreshCw, Terminal, XCircle,
} from "lucide-react";
import * as React from "react";
import { api, type ClaimerLauf, type ClaimerStatus } from "@/lib/api";
import { useAsync } from "@/lib/useEvents";
import { cn, formatDateTime, timeAgo } from "@/lib/utils";
import {
  Badge, Button, Card, CardContent, CardHeader, CardTitle, EmptyState, Skeleton,
} from "@/components/ui";
import { PageHeader } from "@/components/Layout";
import { useToast } from "@/components/Toast";

const PLATFORM_LABELS: Record<string, string> = {
  epic: "Epic Games",
  prime: "Prime Gaming",
  gog: "GOG",
  unbekannt: "Unbekannt",
};

export function Claimer() {
  const toast = useToast();
  const { data, loading, reload } = useAsync<ClaimerStatus>(
    () => api.claimer.status(), []);
  const { data: logData, reload: reloadLog } = useAsync(() => api.claimer.log(), []);
  const [scanning, setScanning] = React.useState(false);

  const scan = async () => {
    setScanning(true);
    try {
      const result = await api.claimer.scan();
      toast.push("success",
        result.neue_ereignisse > 0
          ? `${result.neue_ereignisse} neue Ereignisse gefunden`
          : "Keine neuen Ereignisse");
      reload();
      reloadLog();
    } catch (err) {
      toast.push("error", "Scan fehlgeschlagen", (err as Error).message);
    } finally {
      setScanning(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Auto-Claimer"
        description="Epic, Prime Gaming und GOG holen sich ihre Gratis-Titel selbst. Diese Seite liest die Logs des Claimer-Containers."
        action={
          <Button variant="outline" onClick={scan} loading={scanning}>
            <RefreshCw className="h-4 w-4" />
            Logs neu einlesen
          </Button>
        }
      />

      {loading ? (
        <Skeleton className="h-64" />
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="space-y-4 lg:col-span-2">
            <Card>
              <CardHeader className="flex-row items-center justify-between space-y-0">
                <CardTitle className="flex items-center gap-2">
                  <Gift className="h-4 w-4 text-primary" />
                  Geclaimte Titel
                </CardTitle>
                <Badge variant="success">{data?.geclaimt_gesamt ?? 0} insgesamt</Badge>
              </CardHeader>
              <CardContent className="p-0">
                {!data?.ereignisse.length ? (
                  <EmptyState
                    icon={<Gift className="h-9 w-9" />}
                    title="Noch nichts gefunden"
                    description={
                      data?.log_vorhanden
                        ? "Logs sind da, aber es wurde noch nichts geclaimt. Der Claimer läuft laut Zeitplan."
                        : "Noch keine Claimer-Logs. Läuft der Container, und ist das Volume gemountet?"
                    }
                  />
                ) : (
                  <ul className="max-h-[32rem] divide-y divide-border overflow-y-auto">
                    {data.ereignisse.map((event, index) => (
                      <li key={index} className="flex items-start gap-3 px-5 py-3 sm:px-6">
                        {event.status === "claimed" ? (
                          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                        ) : event.status === "failed" ? (
                          <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
                        ) : (
                          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground/50" />
                        )}
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium">{event.titel}</p>
                          <div className="mt-0.5 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                            <Badge variant="outline">
                              {PLATFORM_LABELS[event.platform] ?? event.platform}
                            </Badge>
                            <span
                              className={cn(
                                event.status === "claimed" && "text-success",
                                event.status === "failed" && "text-destructive",
                              )}
                            >
                              {event.status === "claimed"
                                ? "geholt"
                                : event.status === "already"
                                  ? "hattest du schon"
                                  : "fehlgeschlagen"}
                            </span>
                            <span className="ml-auto">{timeAgo(event.seen_at)}</span>
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Terminal className="h-4 w-4" />
                  Rohlog
                </CardTitle>
              </CardHeader>
              <CardContent>
                <pre className="max-h-80 overflow-auto rounded-md bg-background/60 p-3 font-mono text-[11px] leading-relaxed text-muted-foreground">
                  {logData?.log || "— kein Log gefunden —"}
                </pre>
              </CardContent>
            </Card>
          </div>

          <Card className="h-fit">
            <CardHeader>
              <CardTitle>Status</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <Row label="Logs gefunden"
                value={data?.log_vorhanden ? "ja" : "nein"}
                tone={data?.log_vorhanden ? "ok" : "warn"} />
              <Row label="Dateien" value={String(data?.dateien.length ?? 0)} />
              <Row label="Zuletzt geändert"
                value={data?.letzte_aenderung ? formatDateTime(data.letzte_aenderung) : "—"} />
              <Row label="Log-Verzeichnis" value={data?.log_dir ?? "—"} mono />

              <Starter />
            </CardContent>
          </Card>
        </div>
      )}
    </>
  );
}

const Row = ({
  label,
  value,
  tone,
  mono,
}: {
  label: string;
  value: string;
  tone?: "ok" | "warn";
  mono?: boolean;
}) => (
  <div className="flex items-baseline justify-between gap-3">
    <span className="text-muted-foreground">{label}</span>
    <span
      className={cn(
        "truncate text-right",
        mono && "font-mono text-xs",
        tone === "ok" && "text-success",
        tone === "warn" && "text-warning",
      )}
      title={value}
    >
      {value}
    </span>
  </div>
);


/** Den Claimer-Container starten — ohne SSH.
 *
 *  Der Backend-Container bekommt bewusst keinen Docker-Socket: damit
 *  könnte er den ganzen Host übernehmen, nur um einen Nebencontainer zu
 *  starten. Der Auftrag geht denselben Weg wie ein Update, über das
 *  Host-Skript. Ohne eingerichteten Helfer bleibt der Befehl zum Abtippen.
 */
function Starter() {
  const toast = useToast();
  const { data, reload } = useAsync<ClaimerLauf>(() => api.claimer.lauf(), []);
  const [sende, setSende] = React.useState(false);

  const laeuft = Boolean(data?.laeuft || data?.angefordert);

  React.useEffect(() => {
    if (!laeuft) return;
    const timer = window.setInterval(reload, 5000);
    return () => window.clearInterval(timer);
  }, [laeuft, reload]);

  if (!data) return <Skeleton className="h-24" />;

  if (!data.eingerichtet) {
    return (
      <div className="rounded-md bg-muted/40 p-3 text-xs leading-relaxed text-muted-foreground">
        <p className="mb-1 font-medium text-foreground">Manueller Start</p>
        <p>{data.grund} Auf dem Server:</p>
        <code className="mt-1.5 block break-all rounded bg-background/60 px-2 py-1
                         font-mono text-[11px] text-primary">
          docker compose run --rm claimer
        </code>
        <p className="mt-2">
          Erste Anmeldung siehe README — dafür gibt es den VNC-Zugang auf
          Port 5900.
        </p>
      </div>
    );
  }

  const starten = async () => {
    setSende(true);
    try {
      const antwort = await api.claimer.starten();
      toast.push("success", "Claimer angestoßen", antwort.hinweis);
      reload();
    } catch (err) {
      toast.push("error", "Ging nicht", (err as Error).message);
    } finally {
      setSende(false);
    }
  };

  return (
    <div className="rounded-md bg-muted/40 p-3">
      <p className="mb-2 text-xs font-medium">Jetzt laufen lassen</p>

      {laeuft ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <RefreshCw className="h-3.5 w-3.5 animate-spin text-primary" />
          {data.laeuft ? "Läuft gerade …" : "Angefordert — startet binnen einer Minute."}
        </div>
      ) : (
        <Button size="sm" className="w-full" onClick={starten} loading={sende}>
          <Play className="h-3.5 w-3.5" />
          Claimer starten
        </Button>
      )}

      {data.zuletzt && !laeuft && (
        <div className="mt-3 border-t border-border pt-2.5">
          <div className="flex items-center gap-1.5 text-xs">
            {data.ok ? (
              <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-success" />
            ) : (
              <XCircle className="h-3.5 w-3.5 shrink-0 text-destructive" />
            )}
            <span className={cn(!data.ok && "text-destructive")}>
              {data.ok ? "Zuletzt gelaufen" : "Letzter Lauf fehlgeschlagen"}
            </span>
            <span className="ml-auto text-muted-foreground">
              {timeAgo(data.zuletzt)}
            </span>
          </div>
          {data.ausgabe && (
            <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap
                            break-words rounded bg-background/60 p-2 text-[10px]
                            leading-snug text-muted-foreground">
              {data.ausgabe.trim().split("\n").slice(-25).join("\n")}
            </pre>
          )}
        </div>
      )}

      <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
        Erste Anmeldung siehe README — dafür gibt es den VNC-Zugang auf Port 5900.
      </p>
    </div>
  );
}
