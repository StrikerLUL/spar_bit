import {
  AlertTriangle, BellOff, CheckCircle2, Copy, ExternalLink, FlaskConical,
  HelpCircle, Key, Play, RotateCcw, Rss, TestTube2, XCircle,
} from "lucide-react";
import * as React from "react";
import {
  api, type FeedSuche, type OptionSpec, type Source, type SourceTestResult,
} from "@/lib/api";
import { useAsync } from "@/lib/useEvents";
import {
  cn, formatDuration, formatPrice, linesToList, listToLines, timeAgo,
} from "@/lib/utils";
import {
  Badge, Button, Card, Dialog, Input, Label, Select, Skeleton, Slider, Switch,
  StatusDot, Textarea,
} from "@/components/ui";
import { PageHeader } from "@/components/Layout";
import { useToast } from "@/components/Toast";

const CATEGORY_LABELS: Record<string, string> = {
  community: "Deal-Communities",
  reddit: "Reddit",
  gaming: "Gaming",
  experimental: "Experimentell",
  erwachsen: "18+",
};

export function Sources() {
  const toast = useToast();
  const { data: sources, loading, reload } = useAsync<Source[]>(
    () => api.sources.list(), []);
  const [editing, setEditing] = React.useState<Source | null>(null);

  const grouped = React.useMemo(() => {
    const map = new Map<string, Source[]>();
    for (const source of sources ?? []) {
      const list = map.get(source.category) ?? [];
      list.push(source);
      map.set(source.category, list);
    }
    return map;
  }, [sources]);

  const toggle = async (source: Source, enabled: boolean) => {
    try {
      await api.sources.update(source.id, { enabled });
      toast.push("success", `${source.display_name} ${enabled ? "aktiviert" : "deaktiviert"}`);
      reload();
    } catch (err) {
      toast.push("error", "Fehlgeschlagen", (err as Error).message);
    }
  };

  return (
    <>
      <PageHeader
        title="Quellen"
        description="Jede Quelle einzeln schaltbar. Prüfe neue Quellen mit „Jetzt testen“, bevor du sie scharf stellst."
      />

      <FeedSucher />

      <Card className="mb-6 border-warning/30 bg-warning/5 p-4">
        <div className="flex gap-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          <div className="space-y-1 text-sm">
            <p className="font-medium">Kein Endpoint ist vorab verifiziert</p>
            <p className="text-muted-foreground">
              Die Build-Umgebung hatte keinen Netzzugang zu den Deal-Seiten, darum
              startet alles als <em>ungeprüft</em>. Drücke bei jeder Quelle einmal
              „Jetzt testen“ — das Ergebnis setzt den Status. Alle URLs sind
              editierbar, falls eine Seite ihre Pfade geändert hat.
            </p>
          </div>
        </div>
      </Card>

      {loading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-56" />)}
        </div>
      ) : (
        [...grouped.entries()].map(([category, list]) => (
          <section key={category} className="mb-8">
            <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted-foreground">
              {CATEGORY_LABELS[category] ?? category}
            </h2>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {list.map((source) => (
                <SourceCard
                  key={source.id}
                  source={source}
                  onToggle={(enabled) => toggle(source, enabled)}
                  onEdit={() => setEditing(source)}
                  onChanged={reload}
                />
              ))}
            </div>
          </section>
        ))
      )}

      {editing && (
        <SourceDialog
          source={editing}
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

/** Den Feed einer Seite finden, statt seinen Pfad zu raten.
 *
 *  Entstanden aus einer Fehlermeldung aus dem Betrieb: ein geratener
 *  Gruppen-Pfad lieferte HTML, und der Parser warf eine SAXParseException.
 *  Die Seite selbst weiß, wo ihr Feed liegt — man muss sie nur fragen.
 */
function FeedSucher() {
  const toast = useToast();
  const [url, setUrl] = React.useState("");
  const [laeuft, setLaeuft] = React.useState(false);
  const [ergebnis, setErgebnis] = React.useState<FeedSuche | null>(null);

  const suchen = async () => {
    if (!url.trim()) return;
    setLaeuft(true);
    setErgebnis(null);
    try {
      setErgebnis(await api.sources.feedSuche(url.trim()));
    } catch (err) {
      toast.push("error", "Suche fehlgeschlagen", (err as Error).message);
    } finally {
      setLaeuft(false);
    }
  };

  const kopieren = async (wert: string) => {
    try {
      await navigator.clipboard.writeText(wert);
      toast.push("success", "Kopiert", wert);
    } catch {
      toast.push("error", "Kopieren ging nicht", wert);
    }
  };

  return (
    <Card className="mb-6 p-4">
      <div className="flex items-start gap-3">
        <Rss className="mt-2 h-4 w-4 shrink-0 text-primary" />
        <div className="min-w-0 flex-1 space-y-2">
          <div>
            <p className="text-sm font-medium">Feed suchen</p>
            <p className="text-xs leading-relaxed text-muted-foreground">
              Adresse einer Shop- oder Übersichtsseite eintragen — SparBit
              liest aus, welche Feeds die Seite selbst angibt. Das Ergebnis
              passt direkt in ein Feed-Feld weiter unten.
            </p>
          </div>
          <form className="flex gap-2"
                onSubmit={(e) => { e.preventDefault(); void suchen(); }}>
            <Input value={url} onChange={(e) => setUrl(e.target.value)}
                   placeholder="https://www.beispiel-shop.de/angebote"
                   className="flex-1" />
            <Button type="submit" variant="outline" loading={laeuft}
                    disabled={!url.trim()}>
              Suchen
            </Button>
          </form>

          {ergebnis && (
            <div className="space-y-2 border-t border-border pt-2">
              <p className={cn("text-xs", ergebnis.ok ? "text-foreground"
                                                      : "text-muted-foreground")}>
                {ergebnis.detail}
              </p>
              {ergebnis.feeds.map((feed) => (
                <div key={feed.url}
                     className="flex items-center gap-2 rounded-md border
                                border-border bg-muted/30 px-2.5 py-1.5">
                  <Badge variant={feed.herkunft === "link" ? "success" : "outline"}>
                    {feed.herkunft === "link" ? "ausgezeichnet" : "geraten"}
                  </Badge>
                  <span className="min-w-0 flex-1 truncate font-mono text-[11px]"
                        title={feed.url}>
                    {feed.url}
                  </span>
                  {feed.titel && (
                    <span className="hidden shrink-0 text-[11px] text-muted-foreground sm:inline">
                      {feed.titel}
                    </span>
                  )}
                  <Button variant="ghost" size="sm" onClick={() => kopieren(feed.url)}
                          title="Adresse kopieren">
                    <Copy className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}

function healthOf(source: Source): { status: "ok" | "warn" | "error" | "off"; label: string } {
  if (!source.enabled) return { status: "off", label: "Aus" };
  if (source.snooze_until && new Date(source.snooze_until) > new Date()) {
    const bis = new Date(source.snooze_until)
      .toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
    // Eine Pause nach HTTP 429 sieht im Datensatz aus wie eine
    // Stummschaltung, ist aber keine: die hat niemand eingestellt, die hat
    // die Gegenseite verlangt. Steht das falsch da, sucht man den Schalter,
    // den man nie umgelegt hat.
    const gedrosselt = (source.last_error || "").startsWith("Rate-Limit");
    return { status: "warn", label: gedrosselt ? `gedrosselt bis ${bis}` : `stumm bis ${bis}` };
  }
  if (source.circuit_open) return { status: "error", label: "Gesperrt" };
  if (source.consecutive_failures > 0)
    return { status: "warn", label: `${source.consecutive_failures} Fehler in Folge` };
  if (source.last_success) return { status: "ok", label: "Läuft" };
  return { status: "warn", label: "Noch kein Lauf" };
}

function SourceCard({
  source,
  onToggle,
  onEdit,
  onChanged,
}: {
  source: Source;
  onToggle: (enabled: boolean) => void;
  onEdit: () => void;
  onChanged: () => void;
}) {
  const toast = useToast();
  const [testing, setTesting] = React.useState(false);
  const [running, setRunning] = React.useState(false);
  const [result, setResult] = React.useState<SourceTestResult | null>(null);
  const health = healthOf(source);

  const test = async () => {
    setTesting(true);
    setResult(null);
    try {
      const res = await api.sources.test(source.id);
      setResult(res);
      toast.push(
        res.ok ? "success" : "error",
        `${source.display_name}: ${res.ok ? "erreichbar" : "nicht erreichbar"}`,
        res.detail,
      );
      onChanged();
    } catch (err) {
      toast.push("error", "Test fehlgeschlagen", (err as Error).message);
    } finally {
      setTesting(false);
    }
  };

  const runNow = async () => {
    setRunning(true);
    try {
      const res = await api.sources.run(source.id) as Record<string, unknown>;
      if (res.error) toast.push("error", "Lauf mit Fehler", String(res.error));
      else
        toast.push(
          "success",
          `${res.items ?? 0} Einträge, ${res.new_items ?? 0} neu`,
          source.display_name,
        );
      onChanged();
    } catch (err) {
      toast.push("error", "Lauf fehlgeschlagen", (err as Error).message);
    } finally {
      setRunning(false);
    }
  };

  const needsKey = source.requires_api_key && !source.has_api_key;

  return (
    <Card hover className="flex flex-col">
      <div className="flex items-start justify-between gap-3 p-5 pb-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate font-semibold">{source.display_name}</h3>
            {source.experimental && (
              <Badge variant="warning" title="Experimentell">
                <FlaskConical className="h-3 w-3" />
                experimentell
              </Badge>
            )}
          </div>
          <p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">
            {source.beschreibung}
          </p>
        </div>
        <Switch
          checked={source.enabled}
          onChange={onToggle}
          disabled={needsKey}
          label={`${source.display_name} ein-/ausschalten`}
        />
      </div>

      <div className="flex flex-wrap items-center gap-2 px-5 pb-3 text-xs">
        <span className="inline-flex items-center gap-1.5">
          <StatusDot status={health.status} pulse={health.status === "ok"} />
          <span className="text-muted-foreground">{health.label}</span>
        </span>
        <VerificationBadge value={source.verification} />
        {source.requires_api_key && (
          <Badge variant={source.has_api_key ? "success" : "outline"}>
            <Key className="h-3 w-3" />
            {source.has_api_key ? "Key gesetzt" : "Key nötig"}
          </Badge>
        )}
      </div>

      <dl className="grid grid-cols-3 gap-2 border-y border-border/60 px-5 py-3 text-center text-xs">
        <div>
          <dt className="text-muted-foreground">Intervall</dt>
          <dd className="tabular mt-0.5 font-medium">
            {formatDuration(source.interval_seconds)}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Letzter Lauf</dt>
          <dd className="mt-0.5 truncate font-medium">{timeAgo(source.last_run)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Fehlerquote</dt>
          <dd
            className={cn(
              "tabular mt-0.5 font-medium",
              source.fehlerquote > 30 && "text-destructive",
              source.fehlerquote > 5 && source.fehlerquote <= 30 && "text-warning",
            )}
          >
            {source.fehlerquote}%
          </dd>
        </div>
      </dl>

      {source.last_error && (
        <p className="mx-5 mt-3 break-words rounded-md bg-destructive/10 px-2.5 py-2 text-[11px] leading-relaxed text-destructive">
          {source.last_error}
        </p>
      )}

      {result && (
        <div
          className={cn(
            "mx-5 mt-3 rounded-md px-2.5 py-2 text-[11px] leading-relaxed",
            result.ok ? "bg-success/10 text-success" : "bg-destructive/10 text-destructive",
          )}
        >
          <p className="flex items-center gap-1.5 font-medium">
            {result.ok ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
            {result.detail} ({result.latency_ms} ms)
          </p>
          {result.samples.length > 0 && (
            <ul className="mt-1.5 space-y-0.5 text-muted-foreground">
              {result.samples.slice(0, 3).map((sample, i) => (
                <li key={i} className="truncate">
                  • {sample.titel} —{" "}
                  {sample.ist_gratis ? "gratis" : formatPrice(sample.preis)}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="mt-auto flex flex-wrap gap-2 p-5 pt-4">
        <Button variant="outline" size="sm" onClick={test} loading={testing}>
          <TestTube2 className="h-3.5 w-3.5" />
          Jetzt testen
        </Button>
        <Button variant="ghost" size="sm" onClick={onEdit}>
          Einstellungen
        </Button>
        {source.enabled && (
          <Button variant="ghost" size="sm" onClick={runNow} loading={running}
            title="Sofort einen Lauf auslösen">
            <Play className="h-3.5 w-3.5" />
          </Button>
        )}
        {source.enabled && (
          <Button
            variant="ghost"
            size="sm"
            title={source.snooze_until && new Date(source.snooze_until) > new Date()
              ? "Stummschaltung aufheben" : "6 Stunden stummschalten"}
            onClick={async () => {
              const aktiv = source.snooze_until
                && new Date(source.snooze_until) > new Date();
              await api.snooze(source.id, aktiv ? 0 : 6);
              toast.push("success", aktiv
                ? "Stummschaltung aufgehoben"
                : `${source.display_name} für 6 Stunden stumm`);
              onChanged();
            }}
          >
            <BellOff className="h-3.5 w-3.5" />
          </Button>
        )}
        {source.circuit_open && (
          <Button
            variant="ghost"
            size="sm"
            title="Sperre aufheben"
            onClick={async () => {
              await api.sources.reset(source.id);
              toast.push("success", "Sperre aufgehoben");
              onChanged();
            }}
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
    </Card>
  );
}

const VerificationBadge = ({ value }: { value: Source["verification"] }) => {
  if (value === "verified")
    return (
      <Badge variant="success">
        <CheckCircle2 className="h-3 w-3" />
        geprüft
      </Badge>
    );
  if (value === "broken")
    return (
      <Badge variant="destructive">
        <XCircle className="h-3 w-3" />
        defekt
      </Badge>
    );
  return (
    <Badge variant="outline" title="Noch nie erfolgreich abgerufen">
      <HelpCircle className="h-3 w-3" />
      ungeprüft
    </Badge>
  );
};

function SourceDialog({
  source,
  onClose,
  onSaved,
}: {
  source: Source;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [interval, setInterval] = React.useState(source.interval_seconds);
  const [apiKey, setApiKey] = React.useState("");
  const [options, setOptions] = React.useState<Record<string, unknown>>(source.options);
  const [saving, setSaving] = React.useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await api.sources.update(source.id, {
        interval_seconds: interval,
        ...(apiKey ? { api_key: apiKey } : {}),
        options,
      } as Partial<Source>);
      toast.push("success", "Gespeichert", source.display_name);
      onSaved();
    } catch (err) {
      toast.push("error", "Speichern fehlgeschlagen", (err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog
      open
      onClose={onClose}
      title={source.display_name}
      description={source.beschreibung}
      wide
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Abbrechen</Button>
          <Button onClick={save} loading={saving}>Speichern</Button>
        </>
      }
    >
      <div className="space-y-6">
        <div className="space-y-2">
          <div className="flex items-baseline justify-between">
            <Label>Abrufintervall</Label>
            <span className="tabular text-sm text-muted-foreground">
              {formatDuration(interval)}
            </span>
          </div>
          <Slider
            value={interval}
            min={source.min_interval}
            max={21600}
            step={source.min_interval < 600 ? 60 : 300}
            onChange={setInterval}
          />
          <p className="text-xs text-muted-foreground">
            Minimum {formatDuration(source.min_interval)} — höflicher Umgang mit
            fremden Servern. Kürzere Werte werden serverseitig angehoben.
          </p>
        </div>

        {source.requires_api_key && (
          <div className="space-y-1.5">
            <Label>API-Key</Label>
            <Input
              type="password"
              value={apiKey}
              placeholder={source.has_api_key ? "•••••••• (gesetzt — leer lassen zum Behalten)" : "Key einfügen"}
              onChange={(e) => setApiKey(e.target.value)}
            />
            {source.api_key_url && (
              <a
                href={source.api_key_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
              >
                Key hier holen <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>
        )}

        {source.options_schema.map((spec) => (
          <OptionField
            key={spec.key}
            spec={spec}
            value={options[spec.key]}
            onChange={(value) => setOptions((current) => ({ ...current, [spec.key]: value }))}
          />
        ))}

        {source.docs_url && (
          <a
            href={source.docs_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-primary"
          >
            Dokumentation der Quelle <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </div>
    </Dialog>
  );
}

function OptionField({
  spec,
  value,
  onChange,
}: {
  spec: OptionSpec;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  const help = spec.help && (
    <p className="text-xs leading-relaxed text-muted-foreground">{spec.help}</p>
  );

  if (spec.type === "bool") {
    return (
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <Label>{spec.label}</Label>
          {help}
        </div>
        <Switch checked={Boolean(value)} onChange={onChange} label={spec.label} />
      </div>
    );
  }

  if (spec.type === "list") {
    return (
      <div className="space-y-1.5">
        <Label>{spec.label}</Label>
        <Textarea
          rows={Math.min(8, Math.max(3, ((value as string[]) ?? []).length + 1))}
          value={listToLines(value as string[])}
          onChange={(e) => onChange(linesToList(e.target.value))}
          className="font-mono text-xs"
          spellCheck={false}
        />
        {help}
      </div>
    );
  }

  if (spec.type === "select") {
    return (
      <div className="space-y-1.5">
        <Label>{spec.label}</Label>
        <Select value={String(value ?? "")} onChange={(e) => onChange(e.target.value)}>
          {spec.choices.map((choice) => (
            <option key={choice} value={choice}>{choice}</option>
          ))}
        </Select>
        {help}
      </div>
    );
  }

  // "float" ist wie "int", nur mit Nachkommastellen — ein Höchstpreis von
  // 4,99 € im Monat wäre sonst nicht einzugeben.
  const zahl = spec.type === "int" || spec.type === "float";
  return (
    <div className="space-y-1.5">
      <Label>{spec.label}</Label>
      <Input
        type={zahl ? "number" : "text"}
        step={spec.type === "float" ? "0.01" : undefined}
        value={String(value ?? "")}
        onChange={(e) => onChange(zahl ? Number(e.target.value) : e.target.value)}
        className={spec.type === "string" ? "font-mono text-xs" : undefined}
        spellCheck={false}
      />
      {help}
    </div>
  );
}
