import {
  Download, HardDrive, Image, Keyboard, RefreshCw, ScrollText, Trash2, Upload,
} from "lucide-react";
import * as React from "react";
import { api, type BilderStatus, type LogLine, type SystemInfo } from "@/lib/api";
import { useAsync } from "@/lib/useEvents";
import { useToast } from "@/components/Toast";
import { cn, formatBytes, formatDuration, formatDateTime } from "@/lib/utils";
import {
  Badge, Button, Card, CardContent, CardHeader, CardTitle, Select, Skeleton,
} from "@/components/ui";
import { PageHeader } from "@/components/Layout";

const LEVEL_STYLES: Record<string, string> = {
  DEBUG: "text-muted-foreground/70",
  INFO: "text-foreground/80",
  WARNING: "text-warning",
  ERROR: "text-destructive",
  CRITICAL: "text-destructive font-semibold",
};

export function System({ liveLogs }: { liveLogs: LogLine[] }) {
  const { data: info, loading, reload } = useAsync<SystemInfo>(
    () => api.system.info(), []);
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

          <Card>
            <CardHeader>
              <CardTitle>Backup</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-xs leading-relaxed text-muted-foreground">
                Vollständiger Export als JSON: Regeln, Kanäle, Quellen-Konfiguration
                und Deals. <strong className="text-warning">Enthält deine API-Keys
                und Kanal-Tokens</strong> — behandle die Datei wie ein Passwort.
              </p>
              <Button
                variant="outline"
                className="w-full"
                onClick={() => window.open(api.system.backupUrl, "_blank")}
              >
                <Download className="h-4 w-4" />
                Backup herunterladen
              </Button>
              <RestoreButton />
            </CardContent>
          </Card>

          <BilderCard />

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

const Row = ({ label, value }: { label: string; value: string }) => (
  <div className="flex items-baseline justify-between gap-3">
    <span className="text-muted-foreground">{label}</span>
    <span className="truncate text-right font-medium" title={value}>{value}</span>
  </div>
);


/** Backup zurueckspielen. Regeln, Kanaele und Quellen-Konfiguration werden
 *  ersetzt - gesammelte Deals bleiben, die kommen ohnehin wieder rein. */
function RestoreButton() {
  const toast = useToast();
  const input = React.useRef<HTMLInputElement>(null);
  const [laeuft, setLaeuft] = React.useState(false);

  const einlesen = async (datei: File) => {
    setLaeuft(true);
    try {
      const inhalt = JSON.parse(await datei.text());
      const bericht = await api.restore(inhalt) as Record<string, number>;
      toast.push("success", "Backup eingespielt",
        `${bericht.regeln} Regeln, ${bericht.kanaele} Kanäle, `
        + `${bericht.quellen} Quellen. Seite neu laden.`);
    } catch (err) {
      toast.push("error", "Einspielen fehlgeschlagen", (err as Error).message);
    } finally {
      setLaeuft(false);
      if (input.current) input.current.value = "";
    }
  };

  return (
    <>
      <input
        ref={input}
        type="file"
        accept="application/json,.json"
        className="hidden"
        onChange={(e) => {
          const datei = e.target.files?.[0];
          if (datei) void einlesen(datei);
        }}
      />
      <Button
        variant="ghost"
        className="w-full"
        loading={laeuft}
        onClick={() => {
          if (window.confirm(
            "Backup einspielen? Regeln, Kanäle und Quellen-Einstellungen "
            + "werden dabei ersetzt. Gesammelte Deals bleiben erhalten.")) {
            input.current?.click();
          }
        }}
      >
        <Upload className="h-4 w-4" />
        Backup einspielen
      </Button>
    </>
  );
}


/** Bild-Cache: Zustand und Aufräumen. */
function BilderCard() {
  const toast = useToast();
  const { data, loading, reload } = useAsync<BilderStatus>(
    () => api.bilder.status(), []);
  const [putzt, setPutzt] = React.useState(false);

  if (loading || !data) return <Skeleton className="h-40" />;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Image className="h-4 w-4 text-primary" />
          Bild-Cache
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-xs leading-relaxed text-muted-foreground">
          Deal-Bilder werden einmal geholt und lokal ausgeliefert. Ohne das
          erfährt jeder Händler bei jedem Öffnen des Feeds, welche Deals du
          dir ansiehst.
        </p>
        <Row label="Gespeichert" value={`${data.dateien} Bilder`} />
        <Row label="Belegt" value={formatBytes(data.bytes)} />
        {data.fehlgeschlagen > 0 && (
          <Row label="Nicht erreichbar" value={String(data.fehlgeschlagen)} />
        )}
        {!data.pillow && (
          <p className="rounded-md bg-warning/10 px-2.5 py-2 text-xs text-warning">
            Pillow fehlt — Bilder werden unverkleinert abgelegt und brauchen
            mehr Platz.
          </p>
        )}
        <Button
          variant="outline" size="sm" className="w-full" loading={putzt}
          onClick={async () => {
            setPutzt(true);
            try {
              const r = await api.bilder.aufraeumen();
              toast.push("success", `${r.entfernt} verwaiste Bilder entfernt`);
              reload();
            } catch (err) {
              toast.push("error", "Aufräumen fehlgeschlagen", (err as Error).message);
            } finally {
              setPutzt(false);
            }
          }}
        >
          <Trash2 className="h-3.5 w-3.5" />
          Verwaiste Bilder entfernen
        </Button>
      </CardContent>
    </Card>
  );
}
