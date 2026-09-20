import {
  AlertTriangle, ArrowUpCircle, CheckCircle2, Copy, Download, HardDrive, Image,
  Keyboard, Puzzle, RefreshCw, ScrollText, ShieldCheck, Trash2, Upload, XCircle,
} from "lucide-react";
import * as React from "react";
import {
  api, type ApiTokenInfo, type BilderStatus, type LogLine, type ProblemStatus,
  type SystemInfo, type UpdateStatus,
} from "@/lib/api";
import { useAsync } from "@/lib/useEvents";
import { useToast } from "@/components/Toast";
import {
  cn, formatBytes, formatDateTime, formatDuration, timeAgo,
} from "@/lib/utils";
import {
  Badge, Button, Card, CardContent, CardHeader, CardTitle, Select, Skeleton,
  Switch,
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
          <ProblemCard />
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

          <ErweiterungCard />

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

/** Was gerade nicht läuft — und ob SparBit darüber Bescheid geben soll.
 *
 *  Dieselbe Prüfung, die auch der Melder benutzt. Sie ist absichtlich
 *  nebenwirkungsfrei, damit das Hinsehen hier nicht die Drosselung des
 *  Melders verbraucht.
 */
function ProblemCard() {
  const toast = useToast();
  const { data, reload } = useAsync<ProblemStatus>(
    () => api.system.probleme(), []);

  if (!data) return <Skeleton className="h-32" />;

  const schalte = async (an: boolean) => {
    try {
      await api.system.problemeMelden(an);
      toast.push("success", an ? "Meldungen an" : "Meldungen aus",
        an ? "Ausfälle kommen künftig über deine Kanäle."
           : "Ausfälle stehen nur noch hier.");
      reload();
    } catch (err) {
      toast.push("error", "Ging nicht", (err as Error).message);
    }
  };

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2">
          {data.probleme.length ? (
            <AlertTriangle className="h-4 w-4 text-warning" />
          ) : (
            <ShieldCheck className="h-4 w-4 text-success" />
          )}
          Selbstüberwachung
        </CardTitle>
        {data.probleme.length > 0 && (
          <Badge variant="destructive">{data.probleme.length}</Badge>
        )}
      </CardHeader>

      <CardContent className="space-y-3">
        {data.probleme.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Alle eingeschalteten Quellen liefern, alle Kanäle stellen zu.
          </p>
        ) : (
          <ul className="space-y-2">
            {data.probleme.map((p) => (
              <li key={`${p.art}:${p.betrifft}`}
                className="rounded-md bg-warning/10 px-3 py-2">
                <p className="text-sm leading-snug">{p.text}</p>
                {p.rat && (
                  <p className="mt-0.5 break-words text-xs text-muted-foreground">
                    {p.rat}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}

        <div className="flex items-start justify-between gap-3 border-t border-border pt-3">
          <div className="space-y-0.5">
            <p className="text-sm font-medium">Ausfälle melden</p>
            <p className="text-xs leading-relaxed text-muted-foreground">
              Über deine Kanäle, höchstens einmal je Problem und Tag.
            </p>
          </div>
          <Switch checked={data.an} onChange={schalte} label="Ausfälle melden" />
        </div>
      </CardContent>
    </Card>
  );
}


/** Stand des Codes, Knopf zum Aktualisieren, Schalter fuer die Automatik.
 *
 *  Die Arbeit macht ein Skript auf dem Host - hier wird nur ein Auftrag
 *  hinterlegt und der Stand angezeigt, den das Skript zurueckmeldet. Darum
 *  wird waehrend eines Laufs gepollt: eine Rueckmeldung per SSE gaebe es
 *  nicht, das Backend startet zwischendurch ja selbst neu.
 */
function UpdateCard() {
  const toast = useToast();
  const { data, reload } = useAsync<UpdateStatus>(() => api.system.update(), []);
  const [sende, setSende] = React.useState(false);

  const laeuft = Boolean(data?.laeuft || data?.angefordert);

  React.useEffect(() => {
    if (!laeuft) return;
    const timer = window.setInterval(reload, 4000);
    return () => window.clearInterval(timer);
  }, [laeuft, reload]);

  if (!data) return <Skeleton className="h-44" />;

  if (!data.eingerichtet) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ArrowUpCircle className="h-4 w-4 text-primary" />
            Updates
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs leading-relaxed text-muted-foreground">{data.grund}</p>
        </CardContent>
      </Card>
    );
  }

  const neue = data.neue_commits ?? 0;
  const letztes = data.letztes_update;

  const jetzt = async () => {
    setSende(true);
    try {
      const antwort = await api.system.updateJetzt();
      toast.push("success", "Update angestoßen", antwort.hinweis);
      reload();
    } catch (err) {
      toast.push("error", "Ging nicht", (err as Error).message);
    } finally {
      setSende(false);
    }
  };

  const schalteAuto = async (an: boolean) => {
    try {
      await api.system.updateAuto(an);
      toast.push("success", an ? "Automatik an" : "Automatik aus",
        an ? "Neue Commits werden künftig selbst eingespielt."
           : "Updates nur noch auf Knopfdruck.");
      reload();
    } catch (err) {
      toast.push("error", "Ging nicht", (err as Error).message);
    }
  };

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2">
          <ArrowUpCircle className="h-4 w-4 text-primary" />
          Updates
        </CardTitle>
        {neue > 0 && !laeuft && (
          <Badge variant="default">{neue} neu</Badge>
        )}
      </CardHeader>

      <CardContent className="space-y-3">
        <div className="space-y-1 text-sm">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-muted-foreground">Stand</span>
            <span className="tabular font-medium">
              {data.commit_kurz ?? "—"}
              {data.zweig && (
                <span className="ml-1.5 font-normal text-muted-foreground">
                  ({data.zweig})
                </span>
              )}
            </span>
          </div>
          {data.betreff && (
            <p className="truncate text-xs text-muted-foreground" title={data.betreff}>
              {data.betreff}
            </p>
          )}
        </div>

        {laeuft ? (
          <div className="flex items-center gap-2 rounded-md bg-muted/40 px-3 py-2 text-xs">
            <RefreshCw className="h-3.5 w-3.5 animate-spin text-primary" />
            <span>
              {data.laeuft
                ? "Wird gebaut und neu gestartet …"
                : "Angefordert — startet binnen einer Minute."}
            </span>
          </div>
        ) : (
          <Button variant={neue > 0 ? "default" : "outline"} size="sm"
            className="w-full" onClick={jetzt} loading={sende}>
            <ArrowUpCircle className="h-3.5 w-3.5" />
            {neue > 0 ? `${neue} Update${neue > 1 ? "s" : ""} einspielen`
                      : "Auf Updates prüfen"}
          </Button>
        )}

        <div className="flex items-start justify-between gap-3 border-t border-border pt-3">
          <div className="space-y-0.5">
            <p className="text-sm font-medium">Automatisch</p>
            <p className="text-xs leading-relaxed text-muted-foreground">
              Neue Commits ohne Nachfrage einspielen.
            </p>
          </div>
          <Switch checked={Boolean(data.auto)} onChange={schalteAuto}
            label="Automatische Updates" />
        </div>

        {letztes && (
          <div className="border-t border-border pt-3">
            <div className="flex items-center gap-1.5 text-xs">
              {letztes.ok ? (
                <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-success" />
              ) : (
                <XCircle className="h-3.5 w-3.5 shrink-0 text-destructive" />
              )}
              <span className={cn(!letztes.ok && "text-destructive")}>
                {letztes.ok ? "Zuletzt aktualisiert" : "Letztes Update fehlgeschlagen"}
              </span>
              <span className="ml-auto text-muted-foreground">
                {timeAgo(letztes.zeit)}
              </span>
            </div>
            <p className="mt-1 text-[11px] tabular text-muted-foreground">
              {letztes.von} → {letztes.nach}
              {letztes.grund === "automatisch" && " · automatisch"}
            </p>
            {!letztes.ok && letztes.fehler && (
              <pre className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap break-words
                              rounded-md bg-destructive/10 p-2 text-[10px] leading-snug
                              text-destructive">
                {letztes.fehler.trim()}
              </pre>
            )}
          </div>
        )}

        {data.geprueft_am && (
          <p className="text-[11px] text-muted-foreground">
            Zuletzt geprüft {timeAgo(data.geprueft_am)}
          </p>
        )}
      </CardContent>
    </Card>
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


/** Zugangsschlüssel für die Browser-Erweiterung. */
function ErweiterungCard() {
  const toast = useToast();
  const { data, reload } = useAsync<ApiTokenInfo[]>(() => api.tokens.list(), []);
  const [neu, setNeu] = React.useState<string | null>(null);
  const [legtAn, setLegtAn] = React.useState(false);

  const anlegen = async () => {
    setLegtAn(true);
    try {
      const ergebnis = await api.tokens.create("Browser-Erweiterung");
      setNeu(ergebnis.token);
      reload();
    } catch (err) {
      toast.push("error", "Anlegen fehlgeschlagen", (err as Error).message);
    } finally {
      setLegtAn(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Puzzle className="h-4 w-4 text-primary" />
          Browser-Erweiterung
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs leading-relaxed text-muted-foreground">
          Mit der Erweiterung setzt du Artikel von jeder Shop-Seite aus auf die
          Wunschliste. Sie braucht einen eigenen Schlüssel — das Sitzungs-Cookie
          kann sie auf fremden Seiten nicht nutzen. Ordner{" "}
          <code className="text-primary">browser-extension/</code> im Projekt.
        </p>

        {neu && (
          <div className="space-y-2 rounded-md border border-primary/30 bg-primary/5 p-3">
            <p className="text-xs font-medium text-primary">
              Jetzt kopieren — dieser Schlüssel wird nie wieder angezeigt.
            </p>
            <code className="block break-all rounded bg-background/60 px-2 py-1.5 font-mono text-[11px]">
              {neu}
            </code>
            <Button
              size="sm" variant="outline" className="w-full"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(neu);
                  toast.push("success", "In die Zwischenablage kopiert");
                } catch {
                  toast.push("error", "Kopieren nicht möglich",
                    "Bitte von Hand markieren.");
                }
              }}
            >
              <Copy className="h-3.5 w-3.5" />
              Kopieren
            </Button>
          </div>
        )}

        {data?.map((token) => (
          <div key={token.id}
               className="flex items-center justify-between gap-2 rounded-md border border-border px-2.5 py-2 text-xs">
            <div className="min-w-0">
              <p className="truncate font-medium">{token.name}</p>
              <p className="font-mono text-[10px] text-muted-foreground">
                {token.praefix}… ·{" "}
                {token.zuletzt_genutzt
                  ? `zuletzt ${timeAgo(token.zuletzt_genutzt)}`
                  : "noch nie genutzt"}
              </p>
            </div>
            <Button
              variant="ghost" size="sm" aria-label="Schlüssel zurückziehen"
              onClick={async () => {
                if (!window.confirm("Diesen Schlüssel zurückziehen? Die "
                  + "Erweiterung muss dann neu verbunden werden.")) return;
                await api.tokens.remove(token.id);
                setNeu(null);
                reload();
              }}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        ))}

        <Button variant="outline" size="sm" className="w-full" loading={legtAn}
                onClick={anlegen}>
          Neuen Schlüssel anlegen
        </Button>
      </CardContent>
    </Card>
  );
}
