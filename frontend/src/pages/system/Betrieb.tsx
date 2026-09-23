/* Was laeuft, was klemmt, was aktualisiert werden will.
 *
 * Problemanzeige, Update-Knopf und der lokale Bildspeicher - die drei
 * Karten, die etwas ueber den Zustand der Anlage sagen.
 */
import {
  AlertTriangle, ArrowUpCircle, CheckCircle2, Image, RefreshCw, ShieldCheck,
  Trash2, XCircle,
} from "lucide-react";
import * as React from "react";
import {
  api, type BilderStatus,
  type ProblemStatus, type UpdateStatus, } from "@/lib/api";
import { useAsync } from "@/lib/useEvents";
import { useToast } from "@/components/Toast";
import {
  cn, formatBytes, timeAgo,
} from "@/lib/utils";
import {
  Badge, Button, Card, CardContent, CardHeader, CardTitle, Skeleton, Switch,
} from "@/components/ui";
import { Row } from "@/pages/system/gemeinsam";

export function ProblemCard() {
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

export function UpdateCard() {
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



export function BilderCard() {
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
