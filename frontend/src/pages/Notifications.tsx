import {
  Bell, CheckCircle2, Clock, Plus, Send, Trash2, XCircle,
} from "lucide-react";
import * as React from "react";
import {
  api, type Channel, type ChannelType, type NotificationLogEntry,
  type OptionSpec, type QuietHours,
} from "@/lib/api";
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
            <div className="flex flex-wrap gap-2">
              {types?.map((type) => (
                <Button
                  key={type.type}
                  variant="outline"
                  size="sm"
                  onClick={() =>
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
                    })
                  }
                >
                  <Plus className="h-3.5 w-3.5" />
                  {type.display_name}
                </Button>
              ))}
            </div>
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

        <QuietHoursCard />
      </div>

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

  const save = async () => {
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
          <Button onClick={save} loading={saving}>Speichern</Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="space-y-1.5">
          <Label>Anzeigename</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} />
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
  const secret = ["bot_token", "password", "token"].includes(spec.key);

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
        <Label>{spec.label}</Label>
        <Select value={String(value ?? "")} onChange={(e) => onChange(e.target.value)}>
          {spec.choices.map((choice) => (
            <option key={choice} value={choice}>{choice}</option>
          ))}
        </Select>
        {spec.help && <p className="text-xs text-muted-foreground">{spec.help}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      <Label>{spec.label}</Label>
      <Input
        type={secret ? "password" : spec.type === "int" ? "number" : "text"}
        value={typeof value === "string" && value.includes("…") ? "" : String(value ?? "")}
        placeholder={existing ? "•••••••• (gesetzt — leer lassen zum Behalten)" : undefined}
        onChange={(e) =>
          onChange(spec.type === "int" ? Number(e.target.value) : e.target.value)
        }
        className={cn(secret && "font-mono text-xs")}
      />
      {spec.help && (
        <p className="text-xs leading-relaxed text-muted-foreground">{spec.help}</p>
      )}
    </div>
  );
}
