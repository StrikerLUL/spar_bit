/* Die zuschaltbaren Bereiche: Gratis-Gegenprobe, 18+, Kalender,
 * Browser-Erweiterung.
 *
 * Alle vier sind Karten, die man einmal einstellt und dann nie wieder
 * anfasst - und alle vier waren Gruende, warum System.tsx so lang war.
 */
import {
  BadgeCheck, CalendarClock, Copy,
  Lock, Puzzle, Trash2, } from "lucide-react";
import * as React from "react";
import {
  api, type ApiTokenInfo, type ErwachsenStatus, type GratisCheckStatus, } from "@/lib/api";
import { useAsync } from "@/lib/useEvents";
import { useToast } from "@/components/Toast";
import {
  formatDateTime, timeAgo,
} from "@/lib/utils";
import {
  Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, Label,
  Skeleton, Switch,
} from "@/components/ui";

export function GratisCheckCard() {
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
export function ErwachsenCard() {
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


export function KalenderCard() {
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
export function ErweiterungCard() {
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
