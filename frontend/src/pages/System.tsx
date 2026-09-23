import {
  HardDrive, Keyboard, RefreshCw, ScrollText, } from "lucide-react";
import * as React from "react";
import {
  api, type LogLine,
  type SystemInfo, } from "@/lib/api";
import { useAsync } from "@/lib/useEvents";
import {
  cn, formatBytes, formatDateTime, formatDuration, } from "@/lib/utils";
import {
  Badge, Button, Card, CardContent, CardHeader, CardTitle, Select, Skeleton, } from "@/components/ui";
import { PageHeader } from "@/components/Layout";
import { ProblemCard, UpdateCard, BilderCard } from "@/pages/system/Betrieb";
import { BenutzerCard, ZweiFaktorCard } from "@/pages/system/Konten";
import { BackupCard } from "@/pages/system/Sicherung";
import {
  ErwachsenCard, ErweiterungCard, GratisCheckCard, KalenderCard,
} from "@/pages/system/Bereiche";
import { SicherheitCard, WerkzeugeCard } from "@/pages/system/Werkzeuge";
import { LEVEL_STYLES, Row } from "@/pages/system/gemeinsam";

export function System({ liveLogs }: { liveLogs: LogLine[] }) {
  const { data: info, loading, reload } = useAsync<SystemInfo>(
    () => api.system.info(), []);
  // Die eigene Rolle entscheidet, was auf dieser Seite überhaupt
  // bedienbar ist - ein Mitglied sieht die Konten, ändert sie aber nicht.
  const { data: status } = useAsync(() => api.auth.status(), []);
  const rolle = status?.rolle ?? null;
  const [level, setLevel] = React.useState("ALL");
  const { data: logs, reload: reloadLogs } = useAsync<LogLine[]>(
    () => api.system.logs(level), [level]);
  const [follow, setFollow] = React.useState(true);

  // Live-Logs vorne dranhaengen, aber nur wenn "Folgen" aktiv ist.
  const merged = React.useMemo(() => {
    if (!follow) return logs ?? [];
    const seen = new Set<string>();
    return [...liveLogs, ...(logs ?? [])].filter((line) => {
      const key = `${line.ts}|${line.message}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    }).slice(0, 400);
  }, [liveLogs, logs, follow]);

  return (
    <>
      <PageHeader
        title="Logs & System"
        description="Was gerade passiert, wie groß die Datenbank ist, und wo dein Backup liegt."
        action={
          <Button variant="outline" onClick={() => { reload(); reloadLogs(); }}>
            <RefreshCw className="h-4 w-4" />
            Aktualisieren
          </Button>
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex-row flex-wrap items-center justify-between gap-3 space-y-0">
            <CardTitle className="flex items-center gap-2">
              <ScrollText className="h-4 w-4 text-primary" />
              Live-Logs
            </CardTitle>
            <div className="flex items-center gap-2">
              <Button
                variant={follow ? "default" : "outline"}
                size="sm"
                onClick={() => setFollow((f) => !f)}
              >
                {follow ? "Folgt" : "Angehalten"}
              </Button>
              <Select value={level} onChange={(e) => setLevel(e.target.value)}
                className="h-8 w-32 text-xs">
                <option value="ALL">Alle</option>
                <option value="INFO">Info+</option>
                <option value="WARNING">Warnung+</option>
                <option value="ERROR">Nur Fehler</option>
              </Select>
            </div>
          </CardHeader>
          <CardContent>
            <div className="max-h-[34rem] overflow-auto rounded-md bg-background/60 p-3">
              {!merged.length ? (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  Keine Log-Einträge.
                </p>
              ) : (
                <ul className="space-y-0.5 font-mono text-[11px] leading-relaxed">
                  {merged.map((line, index) => (
                    <li key={index} className="flex gap-2">
                      <span className="shrink-0 text-muted-foreground/50">
                        {new Date(line.ts).toLocaleTimeString("de-DE")}
                      </span>
                      <span className={cn("w-14 shrink-0", LEVEL_STYLES[line.level])}>
                        {line.level}
                      </span>
                      <span className="hidden w-40 shrink-0 truncate text-muted-foreground/60 sm:block">
                        {line.logger}
                      </span>
                      <span className="min-w-0 break-words">{line.message}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </CardContent>
        </Card>

        <div className="space-y-4">
          <ProblemCard />
          <GratisCheckCard />
          <ErwachsenCard />
          <UpdateCard />

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <HardDrive className="h-4 w-4 text-primary" />
                System
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2.5 text-sm">
              {loading || !info ? (
                <Skeleton className="h-40" />
              ) : (
                <>
                  <Row label="Version" value={info.version} />
                  <Row label="Python" value={info.python} />
                  <Row label="Läuft seit" value={formatDuration(info.laufzeit_sekunden)} />
                  <Row label="Gestartet" value={formatDateTime(info.gestartet)} />
                  <Row label="Datenbank" value={formatBytes(info.db_groesse_bytes)} />
                  <Row label="Live-Clients" value={String(info.sse_clients)} />

                  <div className="border-t border-border pt-3">
                    <p className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">
                      Datensätze
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(info.zeilen).map(([key, value]) => (
                        <Badge key={key} variant="outline">
                          {key}: <span className="tabular font-medium">{value}</span>
                        </Badge>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          <BenutzerCard meineRolle={rolle} />

          <ZweiFaktorCard />

          <SicherheitCard />

          <BackupCard />

          <KalenderCard />

          <ErweiterungCard />

          <BilderCard />

          <WerkzeugeCard />

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Keyboard className="h-4 w-4 text-primary" />
                Tastenkürzel
              </CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="space-y-1.5 text-xs">
                {[
                  ["Strg / Cmd + K", "Schnellzugriff öffnen"],
                  ["/", "In die Suche springen"],
                  ["g dann d", "Dashboard"],
                  ["g dann f", "Feed"],
                  ["g dann s", "Statistiken"],
                  ["g dann q", "Quellen"],
                  ["g dann r", "Regeln"],
                  ["Esc", "Dialog schließen"],
                ].map(([taste, was]) => (
                  <div key={taste} className="flex items-baseline justify-between gap-3">
                    <dt>
                      <kbd className="rounded border border-border px-1.5 py-0.5 font-mono text-[10px]">
                        {taste}
                      </kbd>
                    </dt>
                    <dd className="text-muted-foreground">{was}</dd>
                  </div>
                ))}
              </dl>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}

/** Was gerade nicht läuft — und ob SparBit darüber Bescheid geben soll.
 *
 *  Dieselbe Prüfung, die auch der Melder benutzt. Sie ist absichtlich
 *  nebenwirkungsfrei, damit das Hinsehen hier nicht die Drosselung des
 *  Melders verbraucht.
 */
