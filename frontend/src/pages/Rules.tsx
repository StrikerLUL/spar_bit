import {
  CheckCircle2, Lightbulb, Plus, SlidersHorizontal, Sparkles, Target, Trash2,
  XCircle, Zap,
} from "lucide-react";
import * as React from "react";
import {
  api, type Channel, type RegelVorschlag, type Rule, type RuleDraft,
  type RulePreview, type PreviewSample, type Source,
} from "@/lib/api";
import { urteilLabel } from "@/components/Urteil";
import { useAsync } from "@/lib/useEvents";
import {
  cn, formatPrice, linesToList, listToLines, sourceLabel, timeAgo,
} from "@/lib/utils";
import {
  Badge, Button, Card, CardContent, CardHeader, CardTitle, Dialog, EmptyState,
  Input, Label, Select, Skeleton, Switch, Textarea,
} from "@/components/ui";
import { PageHeader } from "@/components/Layout";
import { useToast } from "@/components/Toast";

/** Startpunkte statt weisses Blatt. Jede Vorlage ist bewusst eng gefasst -
 *  lieber wenige gute Treffer als ein Kanal, den man nach zwei Tagen
 *  stummschaltet. */
const VORLAGEN: Array<{ name: string; beschreibung: string; regel: Partial<RuleDraft> }> = [
  {
    name: "Alles Gratis",
    beschreibung: "Jeder 0-€-Fund, sofort. Der Klassiker zum Anfangen.",
    regel: { name: "Alles Gratis", nur_gratis: true, priority: "SOFORT" },
  },
  {
    name: "Gratis-Spiele",
    beschreibung: "Nur Gaming-Quellen, nur kostenlos.",
    regel: {
      name: "Gratis-Spiele", nur_gratis: true, priority: "SOFORT",
      sources: ["epic", "gog", "steam", "cheapshark", "itad", "reddit"],
    },
  },
  {
    name: "Preisfehler",
    beschreibung: "Mindestens 80 % Rabatt und heiß diskutiert.",
    regel: {
      name: "Preisfehler", min_rabatt_prozent: 80, min_temperatur: 300,
      priority: "SOFORT",
    },
  },
  {
    name: "Starke Rabatte",
    beschreibung: "Ab 70 % reduziert, als stündliche Zusammenfassung.",
    regel: { name: "Starke Rabatte", min_rabatt_prozent: 70, priority: "NORMAL" },
  },
  {
    name: "Günstige Technik",
    beschreibung: "Beispiel für Keywords plus Preisgrenze — bitte anpassen.",
    regel: {
      name: "Günstige Technik", priority: "NORMAL", max_preis: 50,
      keywords: ["ssd", "kopfhörer", "monitor", "tastatur", "maus", "festplatte"],
      blacklist: ["gebraucht", "defekt", "b-ware"],
    },
  },
];

const EMPTY_RULE: RuleDraft = {
  name: "",
  enabled: true,
  priority: "NORMAL",
  keywords: [],
  required_keywords: [],
  blacklist: [],
  max_preis: null,
  min_rabatt_prozent: null,
  nur_gratis: false,
  min_temperatur: null,
  min_urteil: null,
  sources: [],
  kategorien: [],
  haendler: [],
  channels: [],
};

export function Rules() {
  const toast = useToast();
  const { data: rules, loading, reload } = useAsync<Rule[]>(() => api.rules.list(), []);
  const [editing, setEditing] = React.useState<{ rule: RuleDraft; id?: number } | null>(null);

  const remove = async (rule: Rule) => {
    if (!window.confirm(`Regel „${rule.name}“ wirklich löschen?`)) return;
    try {
      await api.rules.remove(rule.id);
      toast.push("success", "Regel gelöscht", rule.name);
      reload();
    } catch (err) {
      toast.push("error", "Löschen fehlgeschlagen", (err as Error).message);
    }
  };

  const toggle = async (rule: Rule, enabled: boolean) => {
    try {
      await api.rules.update(rule.id, { ...toDraft(rule), enabled });
      reload();
    } catch (err) {
      toast.push("error", "Fehlgeschlagen", (err as Error).message);
    }
  };

  return (
    <>
      <PageHeader
        title="Regeln"
        description="Beim Bauen siehst du sofort, wie viele der letzten 500 Deals die Regel getroffen hätte — so tunst du sie rauschfrei."
        action={
          <Button onClick={() => setEditing({ rule: { ...EMPTY_RULE } })}>
            <Plus className="h-4 w-4" />
            Neue Regel
          </Button>
        }
      />

      <Vorschlaege onUebernehmen={(regel) =>
        setEditing({ rule: { ...EMPTY_RULE, ...regel } as RuleDraft })} />

      <Card className="mb-6 p-4">
        <p className="mb-2.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Vorlagen — ein Klick, dann anpassen
        </p>
        <div className="flex flex-wrap gap-2">
          {VORLAGEN.map((vorlage) => (
            <button
              key={vorlage.name}
              type="button"
              title={vorlage.beschreibung}
              onClick={() => setEditing({
                rule: { ...EMPTY_RULE, ...vorlage.regel } as RuleDraft,
              })}
              className="rounded-full border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary"
            >
              <Sparkles className="mr-1 inline h-3 w-3" />
              {vorlage.name}
            </button>
          ))}
        </div>
      </Card>

      {loading ? (
        <div className="grid gap-4 md:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-40" />)}
        </div>
      ) : !rules?.length ? (
        <Card>
          <EmptyState
            icon={<SlidersHorizontal className="h-9 w-9" />}
            title="Noch keine Regeln"
            description="Ohne Regel wird nichts verschickt — gesammelt wird trotzdem. Fang mit „alles was gratis ist“ an."
            action={
              <Button onClick={() => setEditing({
                rule: { ...EMPTY_RULE, name: "Alles Gratis", nur_gratis: true,
                        priority: "SOFORT" },
              })}>
                <Plus className="h-4 w-4" />
                Erste Regel anlegen
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {rules.map((rule) => (
            <Card key={rule.id} hover className="p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="truncate font-semibold">{rule.name}</h3>
                    {rule.priority === "SOFORT" && (
                      <Badge variant="warning">
                        <Zap className="h-3 w-3" />
                        SOFORT
                      </Badge>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {rule.match_count} Treffer
                    {rule.last_match && ` · zuletzt ${timeAgo(rule.last_match)}`}
                  </p>
                </div>
                <Switch checked={rule.enabled} onChange={(v) => toggle(rule, v)}
                  label={`${rule.name} ein-/ausschalten`} />
              </div>

              <div className="mt-3 flex flex-wrap gap-1.5">
                {rule.nur_gratis && <Badge variant="success">nur gratis</Badge>}
                {rule.max_preis != null && <Badge variant="outline">≤ {formatPrice(rule.max_preis)}</Badge>}
                {rule.min_rabatt_prozent != null && (
                  <Badge variant="outline">≥ {rule.min_rabatt_prozent}% Rabatt</Badge>
                )}
                {rule.min_temperatur != null && (
                  <Badge variant="outline">≥ {rule.min_temperatur}°</Badge>
                )}
                {rule.min_urteil && (
                  <Badge variant="default">≥ {urteilLabel(rule.min_urteil)}</Badge>
                )}
                {rule.keywords.slice(0, 3).map((keyword) => (
                  <Badge key={keyword}>{keyword}</Badge>
                ))}
                {rule.keywords.length > 3 && (
                  <Badge variant="outline">+{rule.keywords.length - 3}</Badge>
                )}
                {rule.channels.length === 0 && (
                  <Badge variant="destructive" title="Ohne Kanal wird nichts zugestellt">
                    kein Kanal
                  </Badge>
                )}
              </div>

              <div className="mt-4 flex gap-2">
                <Button variant="outline" size="sm"
                  onClick={() => setEditing({ rule: toDraft(rule), id: rule.id })}>
                  Bearbeiten
                </Button>
                <Button variant="ghost" size="sm" onClick={() => remove(rule)}
                  aria-label="Regel löschen">
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {editing && (
        <RuleEditor
          initial={editing.rule}
          ruleId={editing.id}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
        />
      )}
    </>
  );
}

const toDraft = (rule: Rule): RuleDraft => ({
  name: rule.name,
  enabled: rule.enabled,
  priority: rule.priority,
  keywords: rule.keywords,
  required_keywords: rule.required_keywords,
  blacklist: rule.blacklist,
  max_preis: rule.max_preis,
  min_rabatt_prozent: rule.min_rabatt_prozent,
  nur_gratis: rule.nur_gratis,
  min_temperatur: rule.min_temperatur,
  min_urteil: rule.min_urteil,
  sources: rule.sources,
  kategorien: rule.kategorien,
  haendler: rule.haendler,
  channels: rule.channels,
});

/** Der Regel-Editor mit Live-Vorschau. Jede Änderung wird entprellt gegen die
 *  letzten 500 Deals gerechnet, damit man das Rauschen sofort sieht. */
function RuleEditor({
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
            <Label>Name</Label>
            <Input
              value={draft.name}
              autoFocus
              placeholder="z. B. Gratis-Spiele oder LEGO unter 30 €"
              onChange={(e) => set("name", e.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Priorität</Label>
              <Select
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
            <Label>Mindestens dieses Preisurteil</Label>
            <Select
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
            <Label>Quellen</Label>
            <p className="text-xs text-muted-foreground">
              Keine Auswahl = alle Quellen.
            </p>
            <div className="flex flex-wrap gap-1.5 pt-1">
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

          <ListField
            label="Händler"
            help="Teiltreffer genügt: „amazon“ trifft auch „Amazon.de“."
            value={draft.haendler}
            onChange={(v) => set("haendler", v)}
          />

          <div className="space-y-1.5">
            <Label>Benachrichtigen über</Label>
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

function SampleRow({
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

function ListField({
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
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <Textarea
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

function NumberField({
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
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">
        {label} <span className="text-muted-foreground">({suffix})</span>
      </Label>
      <Input
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


/** Regelvorschläge aus dem eigenen Verhalten.
 *  Erscheint nur, wenn wirklich etwas gelernt wurde – sonst wäre es geraten. */
function Vorschlaege({
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
