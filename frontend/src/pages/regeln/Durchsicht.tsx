/* Was Aufmerksamkeit verdient - und was man weitergeben kann.
 *
 * Regelvorschlaege aus dem eigenen Verhalten, die Durchsicht (welche
 * Regel laermt, welche laeuft leer) und der Knopf zum Teilen. Drei
 * Karten, die alle um dieselbe Frage kreisen: stimmen die Regeln noch?
 */
import {
  BellOff, Lightbulb, Share2, Stethoscope, Upload, VolumeX, XCircle, } from "lucide-react";
import * as React from "react";
import {
  api, type Hygiene, type HygieneBefund, type RegelVorschlag,
  } from "@/lib/api";
import { useAsync } from "@/lib/useEvents";
import {
  cn, } from "@/lib/utils";
import {
  Button, Card, } from "@/components/ui";
import { useToast } from "@/components/Toast";

/** Regelvorschläge aus dem eigenen Verhalten.
 *  Erscheint nur, wenn wirklich etwas gelernt wurde – sonst wäre es geraten. */
export function Vorschlaege({
  onUebernehmen,
}: {
  onUebernehmen: (regel: Record<string, unknown>) => void;
}) {
  const { data } = useAsync<RegelVorschlag[]>(() => api.lernen.regeln(), []);
  if (!data?.length) return null;

  return (
    <Card className="mb-6 border-primary/25 bg-primary/5 p-4">
      <div className="mb-2.5 flex items-center gap-2">
        <Lightbulb className="h-4 w-4 text-primary" />
        <p className="text-xs font-medium uppercase tracking-wide text-primary">
          Aus deinem Verhalten abgeleitet
        </p>
      </div>
      <div className="space-y-2">
        {data.map((vorschlag) => (
          <div key={vorschlag.titel}
               className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border/60 bg-background/40 px-3 py-2">
            <div className="min-w-0">
              <p className="text-sm font-medium">{vorschlag.titel}</p>
              <p className="text-xs text-muted-foreground">{vorschlag.begruendung}</p>
            </div>
            <Button size="sm" variant="outline"
                    onClick={() => onUebernehmen({ name: vorschlag.titel,
                                                   ...vorschlag.regel })}>
              Als Regel anlegen
            </Button>
          </div>
        ))}
      </div>
    </Card>
  );
}


/** Regeln und Quellen, die Aufmerksamkeit verdienen.
 *
 *  Regeln werden einmal gebaut und dann vergessen. Die eine liefert 400
 *  Treffer im Monat, von denen man zwei angesehen hat — die schult einen
 *  darauf, Meldungen wegzuwischen. Die andere hat seit Wochen nie
 *  getroffen, weil ein Tippfehler im Stichwort steht.
 *
 *  Vorgeschlagen, nie ausgeführt: eine Regel abzuschalten, die jemand
 *  absichtlich weit gefasst hat, wäre schlimmer als der Hinweis nützt.
 */
export function Hygienekarte({ onBearbeiten }: { onBearbeiten: (id: number) => void }) {
  const toast = useToast();
  const { data, reload } = useAsync<Hygiene>(() => api.hygiene(), []);
  const [zu, setZu] = React.useState<string[]>([]);

  const offen = (data?.befunde ?? []).filter(
    (b) => !zu.includes(`${b.art}:${b.betrifft}`));
  if (!data || offen.length === 0) return null;

  const quelleAus = async (befund: HygieneBefund) => {
    if (!befund.quelle_id) return;
    try {
      await api.sources.update(befund.quelle_id, { enabled: false });
      toast.push("success", "Quelle abgeschaltet", befund.quelle_id);
      reload();
    } catch (err) {
      toast.push("error", "Ging nicht", (err as Error).message);
    }
  };

  return (
    <Card className="mb-6 border-warning/35 p-4">
      <p className="mb-1 flex items-center gap-1.5 text-xs font-medium
                    uppercase tracking-wide text-muted-foreground">
        <Stethoscope className="h-3.5 w-3.5 text-warning" />
        Durchsicht — letzte {data.fenster_tage} Tage
      </p>
      <p className="mb-3 text-xs text-muted-foreground">
        Vorschläge, keine Änderungen. Du entscheidest.
      </p>

      <ul className="space-y-2.5">
        {offen.map((b) => (
          <li key={`${b.art}:${b.betrifft}`}
              className="rounded-md bg-muted/40 p-3">
            <div className="flex items-start gap-2.5">
              <BefundZeichen art={b.art} />
              <div className="min-w-0 flex-1">
                <p className="text-sm leading-snug">{b.text}</p>
                <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                  {b.vorschlag}
                </p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {b.regel_id !== null && (
                    <Button size="sm" variant="outline"
                            onClick={() => onBearbeiten(b.regel_id!)}>
                      Regel öffnen
                    </Button>
                  )}
                  {b.aktion.art === "quelle_aus" && (
                    <Button size="sm" variant="outline"
                            onClick={() => quelleAus(b)}>
                      Quelle abschalten
                    </Button>
                  )}
                  <Button size="sm" variant="ghost"
                          onClick={() => setZu((v) => [...v, `${b.art}:${b.betrifft}`])}>
                    Passt so
                  </Button>
                </div>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}


export function BefundZeichen({ art }: { art: HygieneBefund["art"] }) {
  const stil = "mt-0.5 h-4 w-4 shrink-0";
  if (art === "regel_laut") return <VolumeX className={cn(stil, "text-warning")} />;
  if (art === "regel_ohne_kanal") return <BellOff className={cn(stil, "text-warning")} />;
  if (art === "quelle_rauschen") return <VolumeX className={cn(stil, "text-muted-foreground")} />;
  return <XCircle className={cn(stil, "text-muted-foreground")} />;
}


/** Regeln mitnehmen und mitbringen.
 *
 *  Eine gute Regel ist Arbeit, und bisher blieb sie in der Installation,
 *  in der sie gebaut wurde. Eingespielte Regeln kommen ausgeschaltet an:
 *  eine fremde Regel, die sofort losmeldet, ist der schnellste Weg zu
 *  einem stummgeschalteten Kanal. */
export function TeilenKnopf({ onFertig }: { onFertig: () => void }) {
  const toast = useToast();
  const datei = React.useRef<HTMLInputElement>(null);

  const herunterladen = async () => {
    try {
      const daten = await api.regeln.export();
      const blob = new Blob([JSON.stringify(daten, null, 2)],
        { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "sparbit-regeln.json";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.push("error", "Export fehlgeschlagen", (err as Error).message);
    }
  };

  const einlesen = async (f: File) => {
    try {
      const inhalt = JSON.parse(await f.text());
      const regeln = Array.isArray(inhalt) ? inhalt : inhalt.regeln;
      const bericht = await api.regeln.import(regeln);
      toast.push("success", `${bericht.angelegt.length} Regeln eingesetzt`,
        bericht.hinweis
        + (bericht.uebersprungen.length
          ? ` ${bericht.uebersprungen.length} gab es schon.` : ""));
      onFertig();
    } catch (err) {
      toast.push("error", "Import fehlgeschlagen", (err as Error).message);
    } finally {
      if (datei.current) datei.current.value = "";
    }
  };

  return (
    <>
      <input ref={datei} type="file" accept="application/json,.json"
             className="hidden"
             onChange={(e) => {
               const f = e.target.files?.[0];
               if (f) void einlesen(f);
             }} />
      <Button variant="outline" onClick={() => void herunterladen()}
              title="Regeln als Datei sichern oder weitergeben">
        <Share2 className="h-4 w-4" />
        Teilen
      </Button>
      <Button variant="ghost" onClick={() => datei.current?.click()}
              title="Regeln aus einer Datei einsetzen">
        <Upload className="h-4 w-4" />
      </Button>
    </>
  );
}
