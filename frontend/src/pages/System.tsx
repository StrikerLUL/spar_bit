import {
  AlertTriangle, ArrowUpCircle, BadgeCheck, CalendarClock, CheckCircle2, Copy,
  Download,
  HardDrive, Image, Keyboard, Lock, Puzzle, RefreshCw, ScrollText, ShieldCheck,
  Trash2, Upload, XCircle,
} from "lucide-react";
import * as React from "react";
import {
  api, type ApiTokenInfo, type AppSettings, type BackupListe, type BilderStatus,
  type ErwachsenStatus, type GratisCheckStatus, type LogLine,
  type ProblemStatus, type SystemInfo, type UpdateStatus, type ZweiFaktorStatus,
} from "@/lib/api";
import { useAsync } from "@/lib/useEvents";
import { useToast } from "@/components/Toast";
import {
  cn, formatBytes, formatDateTime, formatDuration, timeAgo,
} from "@/lib/utils";
import {
  Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, Label,
  Select, Skeleton, Switch,
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

          <ZweiFaktorCard />

          <BackupCard />

          <KalenderCard />

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
/** Die Gegenprobe auf der Zielseite - an/aus und was sie zuletzt fand. */
function GratisCheckCard() {
  const toast = useToast();
  const { data, reload } = useAsync<GratisCheckStatus>(
    () => api.system.gratischeck(), []);

  if (!data) return <Skeleton className="h-32" />;

  const setzen = async (body: { an?: boolean; max_pro_lauf?: number }) => {
    try {
      await api.system.gratischeckSetzen(body);
      reload();
    } catch (err) {
      toast.push("error", "Ging nicht", (err as Error).message);
    }
  };

  const woche = Object.entries(data.woche)
    .filter(([status]) => status !== "unklar" && status !== "unerreichbar");

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2">
          <BadgeCheck className="h-4 w-4 text-primary" />
          Gratis-Gegenprobe
        </CardTitle>
        <Switch checked={data.an} onChange={(v) => setzen({ an: v })}
                label="Gegenprobe ein-/ausschalten" />
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-xs leading-relaxed text-muted-foreground">
          Ruft bei jedem als gratis oder fast gratis gemeldeten Fund die
          Zielseite auf und vergleicht mit dem, was der Händler dort
          maschinenlesbar auszeichnet. Verlangt die Seite Geld, wird der Preis
          korrigiert und die Meldung unterbleibt. Findet sich dort keine
          eindeutige Angabe, bleibt alles, wie die Quelle es gemeldet hat —
          geraten wird nicht.
        </p>

        {data.an && (
          <>
            <label className="flex items-center justify-between gap-3">
              <span className="text-xs text-muted-foreground">
                Höchstens Seitenaufrufe je Lauf
              </span>
              <Input
                type="number" min="0" max="60" defaultValue={data.max_pro_lauf}
                className="h-8 w-20 text-xs"
                onBlur={(e) => {
                  const wert = Number(e.target.value);
                  if (wert !== data.max_pro_lauf) setzen({ max_pro_lauf: wert });
                }}
              />
            </label>

            {woche.length > 0 && (
              <div className="flex flex-wrap gap-1.5 border-t border-border pt-3">
                {woche.map(([status, anzahl]) => (
                  <Badge key={status}
                         variant={status === "widerlegt" ? "destructive"
                                  : status === "abgelaufen" ? "outline" : "success"}>
                    {anzahl}× {data.label[status] ?? status}
                  </Badge>
                ))}
                <span className="w-full text-[11px] text-muted-foreground">
                  in den letzten sieben Tagen
                </span>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

/** Der 18+-Bereich: aus, bis hier jemand ausdrücklich Ja sagt. */
function ErwachsenCard() {
  const toast = useToast();
  const { data, reload } = useAsync<ErwachsenStatus>(
    () => api.system.erwachsen(), []);
  const [bestaetigt, setBestaetigt] = React.useState(false);

  if (!data) return <Skeleton className="h-32" />;

  const schalten = async (an: boolean) => {
    try {
      await api.system.erwachsenSchalten(an, bestaetigt);
      toast.push("success", an ? "18+-Bereich frei" : "18+-Bereich aus",
        an ? "Die Quellen stehen jetzt unter „Quellen“, die Funde unter „18+“."
           : "Quellen gestoppt, Funde ausgeblendet. Gelöscht wird nichts.");
      setBestaetigt(false);
      reload();
    } catch (err) {
      toast.push("error", "Ging nicht", (err as Error).message);
    }
  };

  const optionen = async (body: { melden?: boolean; unscharf?: boolean }) => {
    try {
      await api.system.erwachsenOptionen(body);
      reload();
    } catch (err) {
      toast.push("error", "Ging nicht", (err as Error).message);
    }
  };

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2">
          <Lock className="h-4 w-4 text-muted-foreground" />
          18+-Bereich
        </CardTitle>
        {data.an && <Badge variant="success">frei</Badge>}
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-xs leading-relaxed text-muted-foreground">
          Ein getrennter Bereich für Angebote ab 18. Solange er aus ist, gibt
          es die zugehörigen Quellen nicht, es wird nichts eingesammelt und
          nichts gemeldet. Diese Funde erscheinen nie im normalen Feed, nie in
          der Suche, nie in den Statistiken — nur auf ihrer eigenen Seite.
        </p>

        {!data.an ? (
          <>
            <label className="flex cursor-pointer items-start gap-2.5 rounded-md
                              border border-border bg-muted/30 p-3 text-xs">
              <input type="checkbox" checked={bestaetigt}
                     onChange={(e) => setBestaetigt(e.target.checked)}
                     className="mt-0.5 h-4 w-4 shrink-0 accent-[hsl(var(--primary))]" />
              <span>Ich bin mindestens 18 Jahre alt und möchte diesen
                    Bereich sehen.</span>
            </label>
            <Button onClick={() => schalten(true)} disabled={!bestaetigt}
                    variant="outline" className="w-full">
              Freischalten
            </Button>
          </>
        ) : (
          <>
            <dl className="space-y-1.5 border-t border-border pt-3 text-xs">
              <div className="flex justify-between gap-3">
                <dt className="text-muted-foreground">Eigene Quellen</dt>
                <dd className="tabular">{data.quellen ?? 0}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-muted-foreground">Funde bisher</dt>
                <dd className="tabular">{data.deals ?? 0}</dd>
              </div>
              {data.bestaetigt_am && (
                <div className="flex justify-between gap-3">
                  <dt className="text-muted-foreground">Freigeschaltet</dt>
                  <dd>{formatDateTime(data.bestaetigt_am)}</dd>
                </div>
              )}
            </dl>

            <label className="flex cursor-pointer items-start gap-2.5 border-t
                              border-border pt-3 text-xs">
              <Switch checked={data.melden}
                      onChange={(v) => optionen({ melden: v })}
                      label="18+ auch über Kanäle melden" />
              <span className="min-w-0">
                Auch über Telegram, Discord &amp; Co. melden
                <span className="mt-0.5 block leading-relaxed text-muted-foreground">
                  Aus heißt: nur auf der Seite. Zusätzlich braucht jede Regel
                  ein eigenes Häkchen — ohne das sieht sie diese Funde gar nicht.
                </span>
              </span>
            </label>

            <Button onClick={() => schalten(false)} variant="ghost"
                    className="w-full text-muted-foreground">
              Bereich wieder ausschalten
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}

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


/** Zweiter Faktor per Authenticator-App.
 *
 *  Scharf wird er erst, wenn ein Code aus der App wirklich stimmt -
 *  sonst sperrt sich aus, wessen App das Geheimnis nie bekommen hat. */
function ZweiFaktorCard() {
  const toast = useToast();
  const { data, reload } = useAsync<ZweiFaktorStatus>(
    () => api.auth.zweifaktor(), []);
  const [einrichtung, setEinrichtung] = React.useState<
    { geheimnis: string; otpauth: string } | null>(null);
  const [code, setCode] = React.useState("");
  const [ersatz, setErsatz] = React.useState<string[] | null>(null);

  if (!data) return <Skeleton className="h-40" />;

  const starten = async () => {
    try {
      setEinrichtung(await api.auth.zweifaktorStart());
    } catch (err) {
      toast.push("error", "Einrichten fehlgeschlagen", (err as Error).message);
    }
  };

  const bestaetigen = async () => {
    try {
      const antwort = await api.auth.zweifaktorBestaetigen(code);
      setErsatz(antwort.ersatzcodes);
      setEinrichtung(null);
      setCode("");
      reload();
    } catch (err) {
      toast.push("error", "Code stimmt nicht", (err as Error).message);
    }
  };

  const abschalten = async () => {
    const passwort = window.prompt("Zum Abschalten dein Passwort:");
    if (!passwort) return;
    try {
      await api.auth.zweifaktorAus(passwort);
      setErsatz(null);
      reload();
      toast.push("success", "Zweiter Faktor aus");
    } catch (err) {
      toast.push("error", "Abschalten fehlgeschlagen", (err as Error).message);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className={cn("h-4 w-4", data.aktiv ? "text-success" : "text-muted-foreground")} />
          Zweiter Faktor
          {data.aktiv && <Badge variant="success">aktiv</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {!data.aktiv && !einrichtung && (
          <>
            <p className="text-xs leading-relaxed text-muted-foreground">
              Ein Passwort schützt so gut, wie es geheim bleibt. Steht SparBit
              unter einer Domain im Netz, reicht ein wiederverwendetes Passwort
              aus einem fremden Datenleck — dagegen hilft keine Anmeldebremse.
            </p>
            <Button variant="outline" className="w-full" onClick={() => void starten()}>
              <Lock className="h-4 w-4" />
              Einrichten
            </Button>
          </>
        )}

        {einrichtung && (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">
              In der Authenticator-App hinzufügen — Adresse scannen oder den
              Schlüssel von Hand eintippen:
            </p>
            <code className="block break-all rounded-md bg-muted px-2 py-1.5 text-[11px]">
              {einrichtung.geheimnis}
            </code>
            <a href={einrichtung.otpauth}
               className="block truncate text-xs text-primary hover:underline"
               title={einrichtung.otpauth}>
              Direkt in der App öffnen
            </a>
            <Input
              value={code}
              inputMode="numeric"
              placeholder="Code aus der App"
              onChange={(e) => setCode(e.target.value)}
            />
            <div className="flex gap-2">
              <Button className="flex-1" disabled={code.length < 6}
                      onClick={() => void bestaetigen()}>
                Bestätigen
              </Button>
              <Button variant="ghost" onClick={() => setEinrichtung(null)}>
                Abbrechen
              </Button>
            </div>
          </div>
        )}

        {ersatz && (
          <div className="space-y-2 rounded-md border border-warning/40 bg-warning/10 p-3">
            <p className="text-xs font-medium text-warning">
              Ersatzcodes — jetzt aufschreiben. Sie werden nie wieder angezeigt.
            </p>
            <div className="grid grid-cols-2 gap-1 font-mono text-xs">
              {ersatz.map((c) => <span key={c}>{c}</span>)}
            </div>
            <Button variant="ghost" size="sm" className="w-full"
                    onClick={() => {
                      void navigator.clipboard.writeText(ersatz.join("\n"));
                      toast.push("success", "Kopiert");
                    }}>
              <Copy className="h-3.5 w-3.5" />
              Kopieren
            </Button>
          </div>
        )}

        {data.aktiv && (
          <>
            <p className="text-xs text-muted-foreground">
              Aktiv. Noch {data.ersatzcodes_uebrig} Ersatzcodes übrig.
            </p>
            <Button variant="ghost" className="w-full" onClick={() => void abschalten()}>
              Abschalten
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}


/** Sicherung: herunterladen, einspielen, automatische Laeufe ansehen.
 *
 *  Eine Sicherung enthaelt Bot-Token, API-Schluessel und Passwort-Hashes.
 *  Darum steht das Passwortfeld gleich daneben und nicht in einem Menue,
 *  das niemand findet. */
function BackupCard() {
  const toast = useToast();
  const [passwort, setPasswort] = React.useState("");
  const [umfang, setUmfang] = React.useState("voll");
  const [laedt, setLaedt] = React.useState(false);
  const { data: liste, reload } = useAsync<BackupListe>(
    () => api.system.backupsListe(), []);
  const [einstellungen, setEinstellungen] = React.useState<AppSettings | null>(null);

  React.useEffect(() => {
    api.settings.get().then(setEinstellungen).catch(() => undefined);
  }, []);

  const herunterladen = async () => {
    if (!passwort) {
      window.open(`${api.system.backupUrl}?umfang=${umfang}`, "_blank");
      return;
    }
    setLaedt(true);
    try {
      const blob = await api.backupVerschluesselt(passwort, umfang);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `sparbit-backup-${new Date().toISOString().slice(0, 10)}.json.enc`;
      a.click();
      URL.revokeObjectURL(url);
      toast.push("success", "Verschlüsselte Sicherung geladen",
        "Ohne das Passwort lässt sie sich nicht mehr öffnen — gut aufheben.");
    } catch (err) {
      toast.push("error", "Sicherung fehlgeschlagen", (err as Error).message);
    } finally {
      setLaedt(false);
    }
  };

  const jetztSichern = async () => {
    try {
      const bericht = await api.system.backupJetzt();
      toast.push("success", "Sicherung geschrieben",
        `${bericht.datei}${bericht.alte_entfernt ? `, ${bericht.alte_entfernt} alte entfernt` : ""}`);
      reload();
    } catch (err) {
      toast.push("error", "Sicherung fehlgeschlagen", (err as Error).message);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <HardDrive className="h-4 w-4 text-primary" />
          Sicherung
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs leading-relaxed text-muted-foreground">
          Vollständig: Regeln, Kanäle, Quellen, Wunschliste, Preisverlauf,
          gelernte Interaktionen und Deals. <strong className="text-warning">
          Enthält API-Keys und Kanal-Tokens</strong> — mit Passwort wird die
          Datei verschlüsselt (AES-256).
        </p>

        <Select value={umfang} onChange={(e) => setUmfang(e.target.value)}>
          <option value="voll">Alles</option>
          <option value="einstellungen">Nur Einstellungen (für den Umzug)</option>
        </Select>

        <Input
          type="password"
          placeholder={liste?.verschluesselung_moeglich
            ? "Passwort (optional, verschlüsselt die Datei)"
            : "Verschlüsselung nicht verfügbar"}
          value={passwort}
          disabled={liste ? !liste.verschluesselung_moeglich : false}
          onChange={(e) => setPasswort(e.target.value)}
          autoComplete="new-password"
        />

        <Button variant="outline" className="w-full" loading={laedt}
                onClick={() => void herunterladen()}>
          <Download className="h-4 w-4" />
          Herunterladen
        </Button>

        <RestoreButton />

        <div className="space-y-2 border-t border-border pt-3">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-medium">Automatisch im Datenordner</span>
            <Button variant="ghost" size="sm" onClick={() => void jetztSichern()}>
              <RefreshCw className="h-3.5 w-3.5" />
              Jetzt
            </Button>
          </div>
          {einstellungen && (
            <div className="flex items-center justify-between gap-2 text-xs">
              <span className="text-muted-foreground">
                Täglich, {einstellungen.backup_behalten} aufheben
                {einstellungen.backup_passwort_gesetzt ? " (verschlüsselt)" : ""}
              </span>
              <Switch
                checked={einstellungen.backup_taeglich}
                onChange={async (an) => {
                  await api.settings.set({ backup_taeglich: an });
                  setEinstellungen({ ...einstellungen, backup_taeglich: an });
                }}
              />
            </div>
          )}
          {!liste?.dateien.length ? (
            <p className="text-xs text-muted-foreground">
              Noch keine — der tägliche Lauf legt sie unter{" "}
              <code className="text-[11px]">{liste?.ordner ?? "data/backups"}</code> ab.
            </p>
          ) : (
            <ul className="space-y-1">
              {liste.dateien.slice(0, 5).map((datei) => (
                <li key={datei.name}
                    className="flex items-center justify-between gap-2 text-xs">
                  <a href={api.system.backupDateiUrl(datei.name)}
                     className="truncate text-primary hover:underline"
                     title={datei.name}>
                    {datei.verschluesselt ? "🔒 " : ""}{timeAgo(datei.erstellt)}
                  </a>
                  <span className="shrink-0 text-muted-foreground">
                    {formatBytes(datei.bytes)}
                  </span>
                  <button
                    className="shrink-0 text-muted-foreground hover:text-destructive"
                    title="Löschen"
                    onClick={async () => {
                      await api.system.backupLoeschen(datei.name);
                      reload();
                    }}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  );
}


/** Sicherung zurueckspielen. Konfiguration wird ersetzt, gesammelte Daten
 *  werden ergaenzt - was seit der Sicherung dazukam, bleibt stehen. */
function RestoreButton() {
  const toast = useToast();
  const input = React.useRef<HTMLInputElement>(null);
  const [laeuft, setLaeuft] = React.useState(false);

  const einlesen = async (datei: File) => {
    setLaeuft(true);
    try {
      const inhalt = JSON.parse(await datei.text());
      let passwort: string | undefined;
      if (inhalt?.sparbit_backup === "verschluesselt") {
        passwort = window.prompt(
          "Diese Sicherung ist verschlüsselt. Passwort:") ?? undefined;
        if (!passwort) { setLaeuft(false); return; }
      }
      const bericht = await api.restore(inhalt, passwort) as Record<string, number>;
      toast.push("success", "Sicherung eingespielt",
        `${bericht.regeln} Regeln, ${bericht.kanaele} Kanäle, ${bericht.quellen} Quellen, `
        + `${bericht.deals} Deals, ${bericht.wunschliste} Wunschartikel, `
        + `${bericht.interaktionen} gelernte Spuren. Seite neu laden.`);
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
        accept="application/json,.json,.enc"
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
            "Sicherung einspielen? Regeln, Kanäle und gespeicherte Suchen "
            + "werden ersetzt. Deals, Wunschliste und Verlauf werden ergänzt — "
            + "was seitdem dazukam, bleibt stehen.")) {
            input.current?.click();
          }
        }}
      >
        <Upload className="h-4 w-4" />
        Sicherung einspielen
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


/** Fristen als abonnierbarer Kalender.
 *
 *  Ein Gratis-Spiel mit Frist ist ein Termin. In einer Liste sieht man
 *  ihn erst, wenn man die Liste aufmacht — im Kalender sagt er selbst
 *  Bescheid. */
function KalenderCard() {
  const toast = useToast();
  const { data: tokens, reload } = useAsync<ApiTokenInfo[]>(
    () => api.tokens.list(), []);
  const [adresse, setAdresse] = React.useState<string | null>(null);
  const [nurGratis, setNurGratis] = React.useState(false);

  const adresseHolen = async () => {
    try {
      // Ein eigenes Token für den Kalender: zurückziehbar, ohne die
      // Browser-Erweiterung mit abzuschalten.
      const ergebnis = await api.tokens.create("Kalender");
      setAdresse(`${window.location.origin}${api.kalenderUrl(ergebnis.token, nurGratis)}`);
      reload();
    } catch (err) {
      toast.push("error", "Anlegen fehlgeschlagen", (err as Error).message);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CalendarClock className="h-4 w-4 text-primary" />
          Fristen im Kalender
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs leading-relaxed text-muted-foreground">
          Angebote mit Ablaufdatum als Kalender-Abo — mit Erinnerung sechs
          Stunden vorher. Funktioniert in Apple Kalender, Google Kalender,
          Thunderbird und allem, was ICS abonnieren kann.
        </p>

        <div className="flex items-center justify-between gap-3">
          <Label>Nur Gratis-Sachen</Label>
          <Switch checked={nurGratis} onChange={setNurGratis}
                  label="Nur Gratis-Sachen" />
        </div>

        {adresse ? (
          <div className="space-y-2">
            <code className="block break-all rounded-md bg-muted px-2 py-1.5 text-[11px]">
              {adresse}
            </code>
            <Button variant="ghost" size="sm" className="w-full"
                    onClick={() => {
                      void navigator.clipboard.writeText(adresse);
                      toast.push("success", "Kopiert",
                        "Im Kalender unter „Abonnement hinzufügen“ einfügen.");
                    }}>
              <Copy className="h-3.5 w-3.5" />
              Adresse kopieren
            </Button>
            <p className="text-xs text-warning">
              Wer die Adresse hat, sieht deine Fristen — nicht weitergeben.
              Zurückziehen geht unten bei den Schlüsseln.
            </p>
          </div>
        ) : (
          <Button variant="outline" className="w-full"
                  onClick={() => void adresseHolen()}>
            <CalendarClock className="h-4 w-4" />
            Kalender-Adresse erzeugen
          </Button>
        )}
        {!!tokens?.length && (
          <p className="text-xs text-muted-foreground">
            {tokens.length} Schlüssel vergeben.
          </p>
        )}
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
