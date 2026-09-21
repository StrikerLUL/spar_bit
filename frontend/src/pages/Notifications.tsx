import {
  Bell, BellRing, CheckCircle2, Clock, Coins, Monitor, Pause, Play, Plus, Send,
  Trash2, XCircle,
} from "lucide-react";
import * as React from "react";
import {
  api, type AppSettings, type Channel, type ChannelType,
  type NotificationLogEntry, type OptionSpec, type PushGeraet, type QuietHours,
} from "@/lib/api";
import { pushAbmelden, pushAnmelden, pushMoeglich } from "@/lib/push";
import {
  desktopEnabled, desktopSupported, requestDesktopPermission, setDesktopEnabled,
  showDesktop,
} from "@/lib/notify";
import { useAsync } from "@/lib/useEvents";
import { cn, formatDateTime, timeAgo } from "@/lib/utils";
import {
  Badge, Button, Card, CardContent, CardHeader, CardTitle, Dialog, EmptyState,
  Input, Label, Select, Skeleton, Switch,
} from "@/components/ui";
import { PageHeader } from "@/components/Layout";
import { useToast } from "@/components/Toast";

export function Notifications() {
  const toast = useToast();
  const { data: channels, loading, reload } = useAsync<Channel[]>(
    () => api.channels.list(), []);
  const { data: types } = useAsync<ChannelType[]>(() => api.channels.types(), []);
  const { data: log, reload: reloadLog } = useAsync<NotificationLogEntry[]>(
    () => api.channels.log(), []);
  const [editing, setEditing] = React.useState<
    { channel: Partial<Channel>; type: ChannelType } | null
  >(null);
  const [testing, setTesting] = React.useState<number | null>(null);
  const [picking, setPicking] = React.useState(false);

  const anlegen = (type: ChannelType) => {
    setPicking(false);
    setEditing({
      type,
      channel: {
        type: type.type,
        name: type.display_name,
        enabled: true,
        config: Object.fromEntries(
          type.options_schema.map((o) => [o.key, o.default]),
        ),
      },
    });
  };

  const test = async (channel: Channel) => {
    setTesting(channel.id);
    try {
      const result = await api.channels.test(channel.id);
      if (result.ok) toast.push("success", "Testnachricht verschickt", channel.name);
      else toast.push("error", "Test fehlgeschlagen", result.error);
      reloadLog();
    } catch (err) {
      toast.push("error", "Test fehlgeschlagen", (err as Error).message);
    } finally {
      setTesting(null);
    }
  };

  const remove = async (channel: Channel) => {
    if (!window.confirm(`Kanal „${channel.name}“ löschen?`)) return;
    await api.channels.remove(channel.id);
    toast.push("success", "Kanal gelöscht");
    reload();
  };

  return (
    <>
      <PageHeader
        title="Benachrichtigungen"
        description="Kanäle einrichten, testen und Ruhezeiten festlegen."
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-medium uppercase tracking-wide text-muted-foreground">
              Kanäle
            </h2>
            <Button variant="outline" size="sm" onClick={() => setPicking(true)}>
              <Plus className="h-3.5 w-3.5" />
              Kanal hinzufügen
            </Button>
          </div>

          {loading ? (
            <Skeleton className="h-40" />
          ) : !channels?.length ? (
            <Card>
              <EmptyState
                icon={<Bell className="h-9 w-9" />}
                title="Noch kein Kanal"
                description="Ohne Kanal sammelt SparBit still vor sich hin. Telegram ist am schnellsten eingerichtet."
              />
            </Card>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              {channels.map((channel) => {
                const type = types?.find((t) => t.type === channel.type);
                return (
                  <Card key={channel.id} hover className="p-5">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <h3 className="truncate font-semibold">{channel.name}</h3>
                        <p className="text-xs text-muted-foreground">
                          {type?.display_name ?? channel.type}
                        </p>
                      </div>
                      <Switch
                        checked={channel.enabled}
                        label={`${channel.name} ein-/ausschalten`}
                        onChange={async (enabled) => {
                          await api.channels.update(channel.id, {
                            name: channel.name,
                            type: channel.type,
                            enabled,
                            config: {},
                          });
                          reload();
                        }}
                      />
                    </div>

                    <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
                      {channel.last_used && <span>zuletzt {timeAgo(channel.last_used)}</span>}
                      {channel.error_count > 0 && (
                        <Badge variant="destructive">{channel.error_count} Fehler</Badge>
                      )}
                    </div>

                    <div className="mt-4 flex gap-2">
                      <Button variant="outline" size="sm" onClick={() => test(channel)}
                        loading={testing === channel.id}>
                        <Send className="h-3.5 w-3.5" />
                        Test senden
                      </Button>
                      {type && (
                        <Button variant="ghost" size="sm"
                          onClick={() => setEditing({ channel, type })}>
                          Bearbeiten
                        </Button>
                      )}
                      <Button variant="ghost" size="sm" onClick={() => remove(channel)}
                        aria-label="Kanal löschen">
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </Card>
                );
              })}
            </div>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Verlauf</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {!log?.length ? (
                <p className="px-5 pb-5 text-sm text-muted-foreground sm:px-6 sm:pb-6">
                  Noch nichts verschickt.
                </p>
              ) : (
                <ul className="max-h-96 divide-y divide-border overflow-y-auto">
                  {log.map((entry) => (
                    <li key={entry.id} className="flex items-start gap-3 px-5 py-2.5 sm:px-6">
                      {entry.ok ? (
                        <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" />
                      ) : (
                        <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" />
                      )}
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm">{entry.deal_titel ?? "—"}</p>
                        <p className="text-[11px] text-muted-foreground">
                          {entry.channel_type}
                          {entry.rule_name && ` · ${entry.rule_name}`}
                          {" · "}
                          {formatDateTime(entry.created_at)}
                        </p>
                        {entry.error && (
                          <p className="mt-0.5 break-words text-[11px] text-destructive">
                            {entry.error}
                          </p>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4 lg:space-y-6">
          <PushCard />
          <DesktopCard />
          <QuietHoursCard />
          <EinstellungenCard />
        </div>
      </div>

      {picking && (
        <ChannelPicker
          types={types ?? []}
          onPick={anlegen}
          onClose={() => setPicking(false)}
        />
      )}

      {editing && (
        <ChannelDialog
          channel={editing.channel}
          type={editing.type}
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

function ChannelPicker({
  types,
  onPick,
  onClose,
}: {
  types: ChannelType[];
  onPick: (type: ChannelType) => void;
  onClose: () => void;
}) {
  return (
    <Dialog
      open
      onClose={onClose}
      title="Kanal hinzufügen"
      description="Wohin sollen die Treffer? Mehrere Kanäle parallel sind möglich."
    >
      <ul className="space-y-2">
        {types.map((type) => (
          <li key={type.type}>
            <button
              type="button"
              onClick={() => onPick(type)}
              className={cn(
                "w-full rounded-lg border border-border p-3 text-left transition",
                "hover:border-primary/60 hover:bg-muted/50",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              )}
            >
              <span className="flex items-center gap-2">
                <span className="font-medium">{type.display_name}</span>
                {type.supports_buttons && (
                  <Badge variant="outline">mit Knöpfen</Badge>
                )}
              </span>
              <span className="mt-0.5 block text-xs leading-relaxed text-muted-foreground">
                {type.beschreibung}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </Dialog>
  );
}

function QuietHoursCard() {
  const toast = useToast();
  const { data, loading } = useAsync<QuietHours>(() => api.quietHours.get(), []);
  const [value, setValue] = React.useState<QuietHours | null>(null);
  const state = value ?? data;

  const save = async (next: QuietHours) => {
    setValue(next);
    try {
      await api.quietHours.set(next);
    } catch (err) {
      toast.push("error", "Speichern fehlgeschlagen", (err as Error).message);
    }
  };

  if (loading || !state) return <Skeleton className="h-64" />;

  return (
    <Card className="h-fit">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Clock className="h-4 w-4 text-primary" />
          Ruhezeiten
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <Label>Aktiv</Label>
          <Switch checked={state.enabled}
            onChange={(enabled) => save({ ...state, enabled })} label="Ruhezeiten" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label>Von</Label>
            <Input type="time" value={state.start}
              onChange={(e) => save({ ...state, start: e.target.value })} />
          </div>
          <div className="space-y-1.5">
            <Label>Bis</Label>
            <Input type="time" value={state.end}
              onChange={(e) => save({ ...state, end: e.target.value })} />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label>UTC-Versatz</Label>
          <Select
            value={String(state.utc_offset)}
            onChange={(e) => save({ ...state, utc_offset: Number(e.target.value) })}
          >
            <option value="1">UTC+1 (Winterzeit DE)</option>
            <option value="2">UTC+2 (Sommerzeit DE)</option>
            <option value="0">UTC+0</option>
          </Select>
        </div>
        <p className="rounded-md bg-muted/40 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
          Regeln mit Priorität <strong className="text-warning">SOFORT</strong> kommen
          auch während der Ruhezeit durch. Alles andere wird gesammelt und danach
          als Digest zugestellt.
        </p>
      </CardContent>
    </Card>
  );
}

function ChannelDialog({
  channel,
  type,
  onClose,
  onSaved,
}: {
  channel: Partial<Channel>;
  type: ChannelType;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [name, setName] = React.useState(channel.name ?? type.display_name);
  const [config, setConfig] = React.useState<Record<string, unknown>>(channel.config ?? {});
  const [saving, setSaving] = React.useState(false);

  const fehlend = type.options_schema.filter(
    (spec) =>
      spec.pflicht
      && !String(config[spec.key] ?? "").trim()
      && !config[`${spec.key}__set`],
  );

  const save = async () => {
    if (fehlend.length) {
      toast.push("error", "Es fehlt noch etwas",
        fehlend.map((spec) => spec.label).join(", "));
      return;
    }
    setSaving(true);
    try {
      const body = { type: type.type, name, enabled: channel.enabled ?? true, config };
      if (channel.id) await api.channels.update(channel.id, body);
      else await api.channels.create(body);
      toast.push("success", "Gespeichert", name);
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
      title={channel.id ? `${name} bearbeiten` : `${type.display_name} einrichten`}
      description={type.beschreibung}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Abbrechen</Button>
          <Button onClick={save} loading={saving} disabled={fehlend.length > 0}>
            Speichern
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="kanal-name">Name in SparBit</Label>
          <Input id="kanal-name" value={name}
            onChange={(e) => setName(e.target.value)} />
        </div>
        {type.options_schema.map((spec) => (
          <ChannelField
            key={spec.key}
            spec={spec}
            value={config[spec.key]}
            existing={Boolean(config[`${spec.key}__set`])}
            onChange={(value) =>
              setConfig((current) => ({ ...current, [spec.key]: value }))
            }
          />
        ))}
        {type.type === "telegram" && (
          <div className="rounded-md bg-muted/40 p-3 text-xs leading-relaxed text-muted-foreground">
            <p className="mb-1 font-medium text-foreground">So kommst du an die Daten</p>
            <ol className="list-inside list-decimal space-y-0.5">
              <li>In Telegram <code className="text-primary">@BotFather</code> anschreiben, <code>/newbot</code> senden.</li>
              <li>Namen vergeben — du bekommst den Bot-Token.</li>
              <li><code className="text-primary">@userinfobot</code> anschreiben für deine Chat-ID.</li>
              <li>Deinem eigenen Bot einmal <code>/start</code> senden, sonst darf er dir nicht schreiben.</li>
            </ol>
          </div>
        )}
      </div>
    </Dialog>
  );
}

function ChannelField({
  spec,
  value,
  existing,
  onChange,
}: {
  spec: OptionSpec;
  value: unknown;
  existing: boolean;
  onChange: (value: unknown) => void;
}) {
  const secret = ["bot_token", "password", "token", "user"].includes(spec.key);
  const feldId = React.useId();
  const hilfeId = `${feldId}-hilfe`;
  const beschriftung = (
    <Label htmlFor={feldId}>
      {spec.label}
      {spec.pflicht && (
        <span className="ml-1 text-destructive" title="Pflichtfeld">*</span>
      )}
    </Label>
  );

  if (spec.type === "bool") {
    return (
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <Label>{spec.label}</Label>
          {spec.help && <p className="text-xs text-muted-foreground">{spec.help}</p>}
        </div>
        <Switch checked={Boolean(value)} onChange={onChange} label={spec.label} />
      </div>
    );
  }

  if (spec.type === "select") {
    return (
      <div className="space-y-1.5">
        {beschriftung}
        <Select
          id={feldId}
          aria-describedby={spec.help ? hilfeId : undefined}
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
        >
          {spec.choices.map((choice) => (
            <option key={choice} value={choice}>{choice}</option>
          ))}
        </Select>
        {spec.help && (
          <p id={hilfeId} className="text-xs text-muted-foreground">{spec.help}</p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {beschriftung}
      <Input
        id={feldId}
        aria-describedby={spec.help ? hilfeId : undefined}
        aria-required={spec.pflicht || undefined}
        type={secret ? "password" : spec.type === "int" ? "number" : "text"}
        value={typeof value === "string" && value.includes("…") ? "" : String(value ?? "")}
        placeholder={existing ? "•••••••• (gesetzt — leer lassen zum Behalten)" : undefined}
        onChange={(e) =>
          onChange(spec.type === "int" ? Number(e.target.value) : e.target.value)
        }
        className={cn(secret && "font-mono text-xs")}
      />
      {spec.help && (
        <p id={hilfeId} className="text-xs leading-relaxed text-muted-foreground">
          {spec.help}
        </p>
      )}
    </div>
  );
}


/** Desktop-Benachrichtigungen - der kuerzeste Weg, wenn SparBit auf dem
 *  eigenen Rechner laeuft. Kein Bot, kein Token. */
/** Web Push: Meldungen auch dann, wenn SparBit zu ist.
 *
 *  Der Unterschied zur Karte darunter: Desktop-Meldungen brauchen einen
 *  offenen Tab. Web Push nicht - die Meldung kommt aufs Handy, wenn der
 *  Browser laengst geschlossen ist. */
function PushCard() {
  const toast = useToast();
  const [laeuft, setLaeuft] = React.useState(false);
  const { data: schluessel } = useAsync(() => api.push.schluessel(), []);
  const { data: geraete, reload } = useAsync<PushGeraet[]>(
    () => api.push.abos(), []);
  const moeglich = pushMoeglich();

  const anmelden = async () => {
    setLaeuft(true);
    try {
      const { neu } = await pushAnmelden();
      toast.push("success", neu ? "Gerät angemeldet" : "Gerät aufgefrischt",
        "Ein Test über „Kanal testen“ zeigt, ob es ankommt.");
      reload();
    } catch (err) {
      toast.push("error", "Anmelden fehlgeschlagen", (err as Error).message);
    } finally {
      setLaeuft(false);
    }
  };

  return (
    <Card className="h-fit">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BellRing className="h-4 w-4 text-primary" />
          Push aufs Gerät
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {!moeglich || schluessel?.verfuegbar === false ? (
          <p className="text-xs leading-relaxed text-muted-foreground">
            {schluessel?.grund
              ?? "Dieser Browser kann kein Web Push. Auf dem iPhone muss SparBit "
                 + "dafür zum Home-Bildschirm hinzugefügt sein."}
          </p>
        ) : (
          <>
            <p className="text-xs leading-relaxed text-muted-foreground">
              Meldungen direkt aufs Gerät — auch wenn SparBit gar nicht offen
              ist. Kein Konto, kein fremder Dienst: der Inhalt ist verschlüsselt,
              der Push-Dienst leitet ihn nur weiter.
            </p>
            <Button variant="outline" className="w-full" loading={laeuft}
                    onClick={() => void anmelden()}>
              <BellRing className="h-4 w-4" />
              Dieses Gerät anmelden
            </Button>
            {!!geraete?.length && (
              <ul className="space-y-1 border-t border-border pt-3">
                {geraete.map((g) => (
                  <li key={g.id} className="flex items-center justify-between gap-2 text-xs">
                    <span className="truncate" title={g.host}>{g.geraet}</span>
                    <span className="shrink-0 text-muted-foreground">
                      {g.zuletzt_ok ? timeAgo(g.zuletzt_ok) : "noch nichts"}
                    </span>
                    <button
                      className="shrink-0 text-muted-foreground hover:text-destructive"
                      title="Abmelden"
                      onClick={async () => {
                        await api.push.entfernen(g.id);
                        await pushAbmelden();
                        reload();
                      }}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <p className="text-xs text-muted-foreground">
              Damit etwas ankommt, muss außerdem ein Kanal vom Typ
              <strong> Browser (Web Push)</strong> angelegt und aktiv sein.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}


function DesktopCard() {
  const toast = useToast();
  const [an, setAn] = React.useState(desktopEnabled());
  const unterstuetzt = desktopSupported();

  const umschalten = async (wert: boolean) => {
    if (!wert) {
      setDesktopEnabled(false);
      setAn(false);
      return;
    }
    const erlaubt = await requestDesktopPermission();
    if (!erlaubt) {
      toast.push("error", "Vom Browser abgelehnt",
        "Benachrichtigungen sind für diese Seite blockiert. In den "
        + "Seiteneinstellungen des Browsers wieder erlauben.");
      return;
    }
    setDesktopEnabled(true);
    setAn(true);
    showDesktop("SparBit ist bereit", "So sehen deine Treffer künftig aus.");
  };

  return (
    <Card className="h-fit">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Monitor className="h-4 w-4 text-primary" />
          Desktop-Meldungen
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {!unterstuetzt ? (
          <p className="text-xs text-muted-foreground">
            Dieser Browser kennt keine Desktop-Benachrichtigungen.
          </p>
        ) : (
          <>
            <div className="flex items-center justify-between gap-3">
              <Label>Aktiv</Label>
              <Switch checked={an} onChange={umschalten} label="Desktop-Meldungen" />
            </div>
            <p className="text-xs leading-relaxed text-muted-foreground">
              Zeigt Regeltreffer direkt als Systemmeldung — solange dieser Tab
              offen ist. Gilt nur für diesen Browser, unabhängig von Telegram.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

/** Waehrungskurse und globale Pause. */
function EinstellungenCard() {
  const toast = useToast();
  const { data, loading, reload } = useAsync<AppSettings>(() => api.settings.get(), []);
  const [kurse, setKurse] = React.useState<Record<string, string>>({});

  React.useEffect(() => {
    if (data) {
      setKurse(Object.fromEntries(
        Object.entries(data.waehrungskurse).map(([k, v]) => [k, String(v)])));
    }
  }, [data]);

  if (loading || !data) return <Skeleton className="h-64" />;

  const speichern = async (pausiert = data.benachrichtigungen_pausiert) => {
    try {
      await api.settings.set({
        waehrungskurse: Object.fromEntries(
          Object.entries(kurse)
            .map(([k, v]) => [k, Number(v)])
            .filter(([, v]) => Number.isFinite(v as number) && (v as number) > 0)),
        benachrichtigungen_pausiert: pausiert,
      });
      toast.push("success", "Gespeichert");
      reload();
    } catch (err) {
      toast.push("error", "Speichern fehlgeschlagen", (err as Error).message);
    }
  };

  return (
    <Card className="h-fit">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Coins className="h-4 w-4 text-primary" />
          Währung & Pause
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <Button
            variant={data.benachrichtigungen_pausiert ? "default" : "outline"}
            size="sm"
            className="w-full"
            onClick={() => speichern(!data.benachrichtigungen_pausiert)}
          >
            {data.benachrichtigungen_pausiert
              ? <><Play className="h-3.5 w-3.5" /> Zustellung fortsetzen</>
              : <><Pause className="h-3.5 w-3.5" /> Zustellung pausieren</>}
          </Button>
          <p className="mt-1.5 text-xs text-muted-foreground">
            {data.benachrichtigungen_pausiert
              ? "Treffer werden weiter gesammelt, aber nicht zugestellt."
              : "Geht auch per Telegram: /pause und /weiter."}
          </p>
        </div>

        <div className="space-y-2 border-t border-border pt-3">
          <Label>Wechselkurse (1 Einheit in €)</Label>
          <p className="text-xs leading-relaxed text-muted-foreground">
            CheapShark liefert USD, HotUKDeals GBP. Damit „max. 20 €" überall
            gleich greift, rechnet SparBit alles in Euro um.
          </p>
          <div className="grid grid-cols-2 gap-2 pt-1">
            {["USD", "GBP", "CHF", "PLN"].map((code) => (
              <div key={code} className="flex items-center gap-2">
                <span className="w-9 text-xs text-muted-foreground">{code}</span>
                <Input
                  type="number" step="0.01" min="0"
                  value={kurse[code] ?? ""}
                  onChange={(e) => setKurse((c) => ({ ...c, [code]: e.target.value }))}
                  className="h-8"
                />
              </div>
            ))}
          </div>
          <Button size="sm" variant="outline" className="w-full"
                  onClick={() => speichern()}>
            Kurse speichern
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
