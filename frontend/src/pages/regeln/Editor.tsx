/* Der Regel-Editor mit Live-Vorschau.
 *
 * Das Herzstueck: jede Aenderung wird entprellt gegen die letzten 500
 * Deals gerechnet, damit man beim Bauen sieht, wie viel Laerm eine
 * Regel machen wuerde - und welche sie knapp verfehlt haette.
 *
 * Herausgeloest aus Rules.tsx, wo er zwischen Liste, Vorschlaegen und
 * Durchsicht stand und die Datei auf tausend Zeilen brachte.
 */
import {
  CheckCircle2, Target, XCircle, } from "lucide-react";
import * as React from "react";
import {
  api, type Channel, type RuleDraft, type RulePreview, type PreviewSample, type Source,
} from "@/lib/api";
import { useAsync } from "@/lib/useEvents";
import { WARENGRUPPEN } from "@/pages/regeln/vorlagen";
import {
  cn, formatPrice, linesToList, listToLines, sourceLabel, } from "@/lib/utils";
import {
  Button, Card, CardContent, CardHeader, CardTitle, Dialog, Input, Label, Select, Switch, Textarea,
} from "@/components/ui";
import { useToast } from "@/components/Toast";

/** Der Regel-Editor mit Live-Vorschau. Jede Änderung wird entprellt gegen die
 *  letzten 500 Deals gerechnet, damit man das Rauschen sofort sieht. */
export function RuleEditor({
  initial,
  ruleId,
  onClose,
  onSaved,
}: {
  initial: RuleDraft;
  ruleId?: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [draft, setDraft] = React.useState<RuleDraft>(initial);
  // Das 18+-Haekchen gibt es nur, wenn der Bereich ueberhaupt offen ist.
  const { data: erwachsenStatus } = useAsync(() => api.system.erwachsen(), []);
  const erwachsenFrei = Boolean(erwachsenStatus?.an);
  const [preview, setPreview] = React.useState<RulePreview | null>(null);
  const [previewing, setPreviewing] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [tab, setTab] = React.useState<"treffer" | "knapp">("treffer");

  const { data: sources } = useAsync<Source[]>(() => api.sources.list(), []);
  const { data: channels } = useAsync<Channel[]>(() => api.channels.list(), []);

  const set = <K extends keyof RuleDraft>(key: K, value: RuleDraft[K]) =>
    setDraft((current) => ({ ...current, [key]: value }));

  // Vorschau entprellt nachziehen.
  React.useEffect(() => {
    const timer = window.setTimeout(async () => {
      setPreviewing(true);
      try {
        setPreview(await api.rules.preview(draft));
      } catch {
        setPreview(null);
      } finally {
        setPreviewing(false);
      }
    }, 400);
    return () => window.clearTimeout(timer);
  }, [draft]);

  const save = async () => {
    if (!draft.name.trim()) {
      toast.push("error", "Die Regel braucht einen Namen");
      return;
    }
    setSaving(true);
    try {
      if (ruleId) await api.rules.update(ruleId, draft);
      else await api.rules.create(draft);
      toast.push("success", ruleId ? "Regel aktualisiert" : "Regel angelegt", draft.name);
      onSaved();
    } catch (err) {
      toast.push("error", "Speichern fehlgeschlagen", (err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const samples = tab === "treffer" ? preview?.beispiele : preview?.knapp_verfehlt;

  return (
    <Dialog
      open
      onClose={onClose}
      title={ruleId ? "Regel bearbeiten" : "Neue Regel"}
      description="Links definieren, rechts sofort sehen, was sie getroffen hätte."
      wide
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Abbrechen</Button>
          <Button onClick={save} loading={saving}>
            {ruleId ? "Speichern" : "Regel anlegen"}
          </Button>
        </>
      }
    >
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        {/* --- Definition --- */}
        <div className="space-y-5">
          <div className="space-y-1.5">
            <Label htmlFor="regel-name">Name</Label>
            <Input
              id="regel-name"
              value={draft.name}
              autoFocus
              placeholder="z. B. Gratis-Spiele oder LEGO unter 30 €"
              onChange={(e) => set("name", e.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="regel-prio">Priorität</Label>
              <Select
                id="regel-prio"
                value={draft.priority}
                onChange={(e) => set("priority", e.target.value as RuleDraft["priority"])}
              >
                <option value="NORMAL">NORMAL — stündlicher Digest</option>
                <option value="SOFORT">SOFORT — Push in Sekunden</option>
              </Select>
            </div>
            <div className="flex items-end pb-1">
              <label className="flex cursor-pointer items-center gap-2.5 text-sm">
                <Switch checked={draft.nur_gratis}
                  onChange={(v) => set("nur_gratis", v)} label="Nur gratis" />
                Nur gratis
              </label>
            </div>
          </div>

          {/* Nur sichtbar, wenn der 18+-Bereich freigeschaltet ist - sonst
              waere es eine Einstellung fuer etwas, das es nicht gibt. */}
          {erwachsenFrei && (
            <label className="flex cursor-pointer items-start gap-2.5 rounded-md
                              border border-border bg-muted/30 p-3 text-sm">
              <Switch checked={draft.erwachsen}
                onChange={(v) => set("erwachsen", v)} label="18+ einbeziehen" />
              <span className="min-w-0">
                18+-Funde einbeziehen
                <span className="mt-0.5 block text-xs leading-relaxed text-muted-foreground">
                  Ohne dieses Häkchen sieht die Regel diese Funde gar nicht —
                  auch dann nicht, wenn sonst alles passt. Gemeldet wird
                  trotzdem nur, wenn unter Logs &amp; System die Zustellung
                  für 18+ eingeschaltet ist.
                </span>
              </span>
            </label>
          )}

          <ListField
            label="Keywords (ODER)"
            help="Einer pro Zeile. Trifft, wenn mindestens einer vorkommt. „lego*“ als Präfix, „nintendo switch“ als Phrase."
            value={draft.keywords}
            onChange={(v) => set("keywords", v)}
          />
          <ListField
            label="Pflicht-Keywords (UND)"
            help="Müssen alle vorkommen. Gut, um „ssd“ + „2tb“ zu erzwingen."
            value={draft.required_keywords}
            onChange={(v) => set("required_keywords", v)}
          />
          <ListField
            label="Blacklist"
            help="Trifft eines davon, fällt der Deal raus — egal was sonst passt."
            value={draft.blacklist}
            onChange={(v) => set("blacklist", v)}
          />

          <div className="grid grid-cols-3 gap-3">
            <NumberField label="Max. Preis" suffix="€" value={draft.max_preis}
              onChange={(v) => set("max_preis", v)} />
            <NumberField label="Min. Rabatt" suffix="%" value={draft.min_rabatt_prozent}
              onChange={(v) => set("min_rabatt_prozent", v)} />
            <NumberField label="Min. Temp." suffix="°" value={draft.min_temperatur}
              onChange={(v) => set("min_temperatur", v)} />
          </div>

          <div className="space-y-1.5">
            <Label id="regel-preisfehler">Preisfehler-Verdacht</Label>
            <Select
              value={draft.min_fehler_score ? String(draft.min_fehler_score) : ""}
              onChange={(e) =>
                set("min_fehler_score", e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">egal</option>
              <option value="45">ab Verdacht (45 Punkte)</option>
              <option value="70">nur belegte Fälle (70 Punkte)</option>
              <option value="85">nur eindeutige Fälle (85 Punkte)</option>
            </Select>
            <p className="text-xs leading-relaxed text-muted-foreground">
              Preise, die kein Rabatt erklärt — verrutschte Kommastelle,
              ausdrücklich als Preisfehler gemeldet, oder weit unter allem,
              was andere Quellen verlangen. Belegte Fälle meldet der Wächter
              ohnehin sofort; eine Regel braucht es nur, wenn du sie an einen
              bestimmten Kanal schicken willst.
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="regel-urteil">Mindestens dieses Preisurteil</Label>
            <Select
              id="regel-urteil"
              value={draft.min_urteil ?? ""}
              onChange={(e) => set("min_urteil", e.target.value || null)}
            >
              <option value="">egal</option>
              <option value="bestpreis">nur echte Bestpreise</option>
              <option value="sehr_gut">sehr gut oder besser</option>
              <option value="gut">gut oder besser</option>
              <option value="normal">normal oder besser</option>
            </Select>
            <p className="text-xs leading-relaxed text-muted-foreground">
              Gerechnet aus dem eigenen Preisverlauf, nicht aus dem Rabatt der
              Quelle. Deals ohne genug Verlauf fallen dabei heraus.
            </p>
          </div>

          <div className="space-y-1.5">
            <Label id="regel-quellen">Quellen</Label>
            <p className="text-xs text-muted-foreground">
              Keine Auswahl = alle Quellen.
            </p>
            <div className="flex flex-wrap gap-1.5 pt-1" role="group"
                 aria-labelledby="regel-quellen">
              {sources?.map((source) => {
                const active = draft.sources.includes(source.id);
                return (
                  <button
                    key={source.id}
                    type="button"
                    onClick={() =>
                      set("sources", active
                        ? draft.sources.filter((s) => s !== source.id)
                        : [...draft.sources, source.id])
                    }
                    className={cn(
                      "rounded-full border px-2.5 py-1 text-xs transition-colors",
                      active
                        ? "border-primary/40 bg-primary/15 text-primary"
                        : "border-border text-muted-foreground hover:bg-accent",
                    )}
                  >
                    {source.display_name}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label id="regel-warengruppen">Warengruppen</Label>
            <p className="text-xs leading-relaxed text-muted-foreground">
              Keine Auswahl = alle. Nicht dasselbe wie die Quelle: hier geht es
              darum, <em>was</em> der Artikel ist, nicht woher er kommt.
              SparBit erkennt die Gruppe aus Stichwörtern im Titel — was nicht
              erkennbar ist, bleibt ohne Gruppe und fällt bei einer Auswahl
              heraus.
            </p>
            <div className="flex flex-wrap gap-1.5 pt-1" role="group"
                 aria-labelledby="regel-warengruppen">
              {WARENGRUPPEN.map(({ id, label }) => {
                const aktiv = draft.warengruppen.includes(id);
                return (
                  <button
                    key={id}
                    type="button"
                    aria-pressed={aktiv}
                    onClick={() =>
                      set("warengruppen", aktiv
                        ? draft.warengruppen.filter((g) => g !== id)
                        : [...draft.warengruppen, id])
                    }
                    className={cn(
                      "rounded-full border px-2.5 py-1 text-xs transition-colors",
                      aktiv
                        ? "border-primary/40 bg-primary/15 text-primary"
                        : "border-border text-muted-foreground hover:bg-accent",
                    )}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>

          <ListField
            label="Händler"
            help="Teiltreffer genügt: „amazon“ trifft auch „Amazon.de“."
            value={draft.haendler}
            onChange={(v) => set("haendler", v)}
          />

          <div className="space-y-1.5">
            <Label id="regel-kanaele">Benachrichtigen über</Label>
            {!channels?.length ? (
              <p className="text-xs text-warning">
                Noch kein Kanal eingerichtet — ohne Kanal wird nichts zugestellt.
              </p>
            ) : (
              <div className="flex flex-wrap gap-1.5 pt-1">
                {channels.map((channel) => {
                  const active = draft.channels.includes(channel.id);
                  return (
                    <button
                      key={channel.id}
                      type="button"
                      onClick={() =>
                        set("channels", active
                          ? draft.channels.filter((c) => c !== channel.id)
                          : [...draft.channels, channel.id])
                      }
                      className={cn(
                        "rounded-full border px-2.5 py-1 text-xs transition-colors",
                        active
                          ? "border-primary/40 bg-primary/15 text-primary"
                          : "border-border text-muted-foreground hover:bg-accent",
                      )}
                    >
                      {channel.name}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* --- Live-Vorschau --- */}
        <div className="lg:sticky lg:top-0 lg:self-start">
          <Card className="overflow-hidden">
            <CardHeader className="pb-4">
              <CardTitle className="flex items-center gap-2">
                <Target className="h-4 w-4 text-primary" />
                Vorschau
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-baseline gap-2">
                <span
                  className={cn(
                    "tabular text-4xl font-semibold transition-opacity",
                    previewing && "opacity-40",
                    preview && preview.treffer > 0 ? "text-primary" : "text-muted-foreground",
                  )}
                >
                  {preview?.treffer ?? "—"}
                </span>
                <span className="text-sm text-muted-foreground">
                  von {preview?.geprueft ?? 0} Deals
                  {preview ? ` (${preview.trefferquote}%)` : ""}
                </span>
              </div>

              {preview && preview.geprueft === 0 && (
                <p className="rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                  Noch keine Deals in der Datenbank — die Vorschau wird
                  aussagekräftig, sobald die ersten Quellen gelaufen sind.
                </p>
              )}
              {preview && preview.treffer > 40 && (
                <p className="rounded-md bg-warning/10 px-3 py-2 text-xs text-warning">
                  Das ist viel. Enger fassen, sonst wird der Kanal zur Spam-Quelle.
                </p>
              )}

              <div className="flex gap-1 rounded-md bg-muted/40 p-1 text-xs">
                {(["treffer", "knapp"] as const).map((key) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setTab(key)}
                    className={cn(
                      "flex-1 rounded px-2 py-1.5 font-medium transition-colors",
                      tab === key
                        ? "bg-card text-foreground shadow-sm"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {key === "treffer"
                      ? `Treffer (${preview?.beispiele.length ?? 0})`
                      : `Knapp verfehlt (${preview?.knapp_verfehlt.length ?? 0})`}
                  </button>
                ))}
              </div>

              <ul className="max-h-[26rem] space-y-2 overflow-y-auto pr-1">
                {!samples?.length ? (
                  <li className="py-6 text-center text-xs text-muted-foreground">
                    {tab === "treffer"
                      ? "Keine Treffer mit dieser Regel."
                      : "Nichts, was nur an einer Bedingung scheitert."}
                  </li>
                ) : (
                  samples.map((sample, index) => (
                    <SampleRow key={`${sample.id}-${index}`} sample={sample} mode={tab} />
                  ))
                )}
              </ul>
            </CardContent>
          </Card>
        </div>
      </div>
    </Dialog>
  );
}

export function SampleRow({
  sample,
  mode,
}: {
  sample: PreviewSample;
  mode: "treffer" | "knapp";
}) {
  return (
    <li className="rounded-md border border-border/60 bg-background/40 p-2.5">
      <div className="flex items-start gap-2">
        {mode === "treffer" ? (
          <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" />
        ) : (
          <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
        )}
        <div className="min-w-0 flex-1">
          <p className="line-clamp-2 text-xs font-medium leading-snug">{sample.titel}</p>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-muted-foreground">
            <span>{sourceLabel(sample.quelle)}</span>
            <span className="tabular">
              {sample.ist_gratis ? "gratis" : formatPrice(sample.preis)}
            </span>
            {sample.rabatt_prozent != null && (
              <span>−{Math.round(sample.rabatt_prozent)}%</span>
            )}
          </div>
          <p
            className={cn(
              "mt-1 text-[10px] leading-relaxed",
              mode === "treffer" ? "text-success/80" : "text-warning/90",
            )}
          >
            {(mode === "treffer" ? sample.gruende : sample.verfehlt).join(" · ")}
          </p>
        </div>
      </div>
    </li>
  );
}

export function ListField({
  label,
  help,
  value,
  onChange,
}: {
  label: string;
  help?: string;
  value: string[];
  onChange: (value: string[]) => void;
}) {
  // Aus der Beschriftung eine id ableiten: die Felder heissen "Keywords",
  // "Blacklist" und so weiter, das ist eindeutig genug - und eine id von
  // aussen durchzureichen waere an jeder Aufrufstelle eine Gelegenheit,
  // sie zu vergessen.
  const kennung = `feld-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  return (
    <div className="space-y-1.5">
      <Label htmlFor={kennung}>{label}</Label>
      <Textarea
        id={kennung}
        rows={3}
        value={listToLines(value)}
        onChange={(e) => onChange(linesToList(e.target.value))}
        className="font-mono text-xs"
        spellCheck={false}
      />
      {help && <p className="text-xs leading-relaxed text-muted-foreground">{help}</p>}
    </div>
  );
}

export function NumberField({
  label,
  suffix,
  value,
  onChange,
}: {
  label: string;
  suffix: string;
  value: number | null;
  onChange: (value: number | null) => void;
}) {
  const kennung = `zahl-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  return (
    <div className="space-y-1.5">
      <Label htmlFor={kennung} className="text-xs">
        {label} <span className="text-muted-foreground">({suffix})</span>
      </Label>
      <Input
        id={kennung}
        type="number"
        min={0}
        step="any"
        value={value ?? ""}
        placeholder="—"
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
      />
    </div>
  );
}
