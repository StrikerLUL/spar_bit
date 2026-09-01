/** Typisierter API-Client. Alle Aufrufe gehen mit Session-Cookie raus. */

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    /** Sekunden bis zum naechsten erlaubten Versuch (bei 429). */
    public retryAfter?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    credentials: "include",
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    ...init,
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.detail) {
        detail = typeof body.detail === "string"
          ? body.detail
          : JSON.stringify(body.detail);
      }
    } catch {
      /* Antwort war kein JSON - Statuszeile reicht. */
    }
    const retry = Number(response.headers.get("Retry-After"));
    throw new ApiError(response.status, detail,
                       Number.isFinite(retry) && retry > 0 ? retry : undefined);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

const get = <T>(path: string) => request<T>(path);
const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });
const put = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "PUT", body: JSON.stringify(body) });
const patch = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
const del = <T>(path: string) => request<T>(path, { method: "DELETE" });

// --- Typen ---------------------------------------------------------------

export interface AuthStatus {
  setup_done: boolean;
  logged_in: boolean;
  username: string | null;
}

export interface Deal {
  id: number;
  titel: string;
  beschreibung: string | null;
  url: string;
  bild: string | null;
  preis: number | null;
  originalpreis: number | null;
  rabatt_prozent: number | null;
  waehrung: string;
  ist_gratis: boolean;
  haendler: string | null;
  kategorie: string | null;
  quelle: string;
  temperatur: number | null;
  tags: string[];
  veroeffentlicht_am: string | null;
  first_seen: string;
  last_seen: string;
  seen_count: number;
  also_from: string[];
  bookmarked: boolean;
  preis_eur: number | null;
  /** Dateiname im lokalen Bild-Cache, falls das Bild geholt werden konnte. */
  bild_lokal: string | null;
  beste_quelle: string;
  anzahl_angebote: number;
  urteil: string | null;
  urteil_text: string | null;
  /** Nur bei Sortierung "fuer_mich" gesetzt. */
  passt_zu_mir?: number;
  passt_weil?: string[];
}

export interface WatchItem {
  id: number;
  name: string;
  url: string;
  ziel_preis: number | null;
  aktiv: boolean;
  intervall_minuten: number;
  letzter_preis: number | null;
  waehrung: string;
  bester_preis: number | null;
  bild: string | null;
  haendler: string | null;
  letzter_lauf: string | null;
  letzter_erfolg: string | null;
  letzter_fehler: string | null;
  fehler_in_folge: number;
  erstellt_am: string;
  ziel_erreicht: boolean;
  verlauf: Array<{ ts: string; preis: number; waehrung: string }>;
  erster_abruf?: { ok: boolean; preis?: number; verfahren?: string; fehler?: string };
}

export interface WatchTest {
  ok: boolean;
  preis?: number;
  waehrung?: string;
  name?: string | null;
  bild?: string | null;
  verfahren?: string;
  fehler?: string;
}

export interface UrteilStufe {
  stufe: string;
  label: string;
}

export interface LernStatus {
  bereit: boolean;
  positiv: number;
  negativ: number;
  hinweis: string;
}

export interface RegelVorschlag {
  titel: string;
  begruendung: string;
  regel: Record<string, unknown>;
  treffer: number;
}

export interface ApiTokenInfo {
  id: number;
  name: string;
  praefix: string;
  erstellt_am: string;
  zuletzt_genutzt: string | null;
}

export interface Angebot {
  quelle: string;
  url: string;
  preis: number | null;
  waehrung: string;
  preis_eur: number | null;
  originalpreis: number | null;
  rabatt_prozent: number | null;
  haendler: string | null;
  ist_gratis: boolean;
  zuletzt_gesehen: string;
}

export interface OptionSpec {
  key: string;
  label: string;
  type: "string" | "int" | "bool" | "list" | "select";
  default: unknown;
  help: string;
  choices: string[];
  /** Ohne diesen Wert funktioniert der Kanal bzw. die Quelle nicht. */
  pflicht: boolean;
}

export interface Source {
  id: string;
  display_name: string;
  category: string;
  beschreibung: string;
  docs_url: string | null;
  requires_api_key: boolean;
  api_key_url: string | null;
  experimental: boolean;
  default_interval: number;
  min_interval: number;
  options_schema: OptionSpec[];
  enabled: boolean;
  interval_seconds: number;
  has_api_key: boolean;
  options: Record<string, unknown>;
  verification: "unverified" | "verified" | "broken";
  last_verified: string | null;
  last_run: string | null;
  last_success: string | null;
  last_error: string | null;
  consecutive_failures: number;
  circuit_open_until: string | null;
  circuit_open: boolean;
  snooze_until: string | null;
  total_runs: number;
  total_errors: number;
  total_items: number;
  fehlerquote: number;
}

export interface SourceTestResult {
  ok: boolean;
  detail: string;
  items_found: number;
  latency_ms: number;
  samples: Array<{
    titel: string;
    url: string;
    preis: number | null;
    originalpreis: number | null;
    rabatt_prozent: number | null;
    ist_gratis: boolean;
    haendler: string | null;
    bild: string | null;
  }>;
}

export interface Rule {
  id: number;
  name: string;
  enabled: boolean;
  priority: "SOFORT" | "NORMAL";
  keywords: string[];
  required_keywords: string[];
  blacklist: string[];
  max_preis: number | null;
  min_rabatt_prozent: number | null;
  nur_gratis: boolean;
  min_temperatur: number | null;
  min_urteil: string | null;
  sources: string[];
  kategorien: string[];
  haendler: string[];
  channels: number[];
  created_at: string;
  match_count: number;
  last_match: string | null;
}

export type RuleDraft = Omit<Rule, "id" | "created_at" | "match_count" | "last_match">;

export interface PreviewSample {
  id: number | null;
  titel: string;
  preis: number | null;
  originalpreis: number | null;
  rabatt_prozent: number | null;
  ist_gratis: boolean;
  quelle: string;
  url: string;
  bild: string | null;
  gruende: string[];
  verfehlt: string[];
}

export interface RulePreview {
  geprueft: number;
  treffer: number;
  trefferquote: number;
  beispiele: PreviewSample[];
  knapp_verfehlt: PreviewSample[];
}

export interface Channel {
  id: number;
  type: string;
  name: string;
  enabled: boolean;
  config: Record<string, unknown>;
  created_at: string;
  last_used: string | null;
  error_count: number;
}

export interface ChannelType {
  type: string;
  display_name: string;
  beschreibung: string;
  /** Kann Aktions-Knöpfe unter die Nachricht setzen (bisher nur Telegram). */
  supports_buttons: boolean;
  options_schema: OptionSpec[];
}

export interface QuietHours {
  enabled: boolean;
  start: string;
  end: string;
  utc_offset: number;
}

export interface Stats {
  treffer_heute: number;
  deals_heute: number;
  gratis_diese_woche: number;
  gesparter_betrag: number;
  deals_gesamt: number;
  quellen_ampel: { gruen: number; gelb: number; rot: number; aus: number };
  aktive_regeln: number;
  top_quellen: Array<{ quelle: string; anzahl: number }>;
}

export interface TimelinePoint {
  tag: string;
  deals: number;
  gratis: number;
  treffer: number;
  ersparnis: number;
}

export interface QuellenStat {
  quelle: string;
  deals: number;
  gratis: number;
  treffer: number;
  signalquote: number;
}

export interface HaendlerStat {
  haendler: string;
  anzahl: number;
  schnitt_rabatt: number;
}

export interface PricePoint {
  ts: string;
  preis: number;
  waehrung: string;
  /** In Euro umgerechnet - der Verlauf kann Währungen mischen. */
  preis_eur: number | null;
  quelle: string | null;
}

export interface DealDetail extends Deal {
  preis_eur: number | null;
  alarm_preis: number | null;
  alarm_ausgeloest: string | null;
  notiz: string | null;
  verlauf: PricePoint[];
  tiefstpreis: number | null;
  hoechstpreis: number | null;
  regeltreffer: Array<{ regel: string; wann: string }>;
  angebote: Angebot[];
  beste_quelle: string;
  beste_url: string;
}

export interface BilderStatus {
  aktiv: boolean;
  pillow: boolean;
  dateien: number;
  fehlgeschlagen: number;
  bytes: number;
  verzeichnis: string;
}

export interface SavedSearch {
  id: number;
  name: string;
  filter: Record<string, unknown>;
}

export interface AppSettings {
  waehrungskurse: Record<string, number>;
  aktive_kurse: Record<string, number>;
  benachrichtigungen_pausiert: boolean;
}

export interface SystemInfo {
  version: string;
  python: string;
  platform: string;
  gestartet: string;
  laufzeit_sekunden: number;
  db_pfad: string;
  db_groesse_bytes: number;
  db_groesse_mb: number;
  sse_clients: number;
  zeilen: Record<string, number>;
}

export interface LogLine {
  ts: string;
  level: string;
  logger: string;
  message: string;
  exc?: string;
}

export interface ClaimEvent {
  platform: string;
  titel: string;
  status: string;
  seen_at: string;
  detail: string | null;
}

export interface ClaimerStatus {
  log_dir: string;
  log_vorhanden: boolean;
  dateien: string[];
  letzte_aenderung: string | null;
  geclaimt_gesamt: number;
  ereignisse: ClaimEvent[];
}

export interface NotificationLogEntry {
  id: number;
  channel_type: string;
  rule_name: string | null;
  deal_titel: string | null;
  ok: boolean;
  error: string | null;
  created_at: string;
}

export interface SourceRun {
  started_at: string;
  ok: boolean;
  items: number;
  new_items: number;
  duration_ms: number;
  error: string | null;
}

// --- API -----------------------------------------------------------------

export const api = {
  auth: {
    status: () => get<AuthStatus>("/auth/status"),
    setup: (username: string, password: string) =>
      post<{ ok: boolean }>("/auth/setup", { username, password }),
    login: (username: string, password: string) =>
      post<{ ok: boolean }>("/auth/login", { username, password }),
    logout: () => post<{ ok: boolean }>("/auth/logout"),
    changePassword: (old_password: string, new_password: string) =>
      post<{ ok: boolean }>("/auth/password", { old_password, new_password }),
  },
  deals: {
    list: (params: Record<string, string | number | boolean | undefined>) => {
      const query = new URLSearchParams();
      for (const [key, value] of Object.entries(params)) {
        if (value !== undefined && value !== "" && value !== false) {
          query.set(key, String(value));
        }
      }
      return get<{
        total: number; items: Deal[];
        empfehlung_aktiv?: boolean; hinweis?: string;
      }>(`/deals?${query}`);
    },
    bookmark: (id: number) =>
      post<{ id: number; bookmarked: boolean }>(`/deals/${id}/bookmark`),
  },
  stats: () => get<Stats>("/stats"),
  matches: (limit = 40) =>
    get<Array<Deal & { regel: string; created_at: string }>>(`/matches?limit=${limit}`),
  sources: {
    list: () => get<Source[]>("/sources"),
    update: (id: string, body: Partial<Source>) => patch<Source>(`/sources/${id}`, body),
    test: (id: string) => post<SourceTestResult>(`/sources/${id}/test`),
    run: (id: string) => post<Record<string, unknown>>(`/sources/${id}/run`),
    reset: (id: string) => post<{ ok: boolean }>(`/sources/${id}/reset`),
    runs: (id: string) => get<SourceRun[]>(`/sources/${id}/runs`),
  },
  rules: {
    list: () => get<Rule[]>("/rules"),
    create: (body: RuleDraft) => post<Rule>("/rules", body),
    update: (id: number, body: RuleDraft) => put<Rule>(`/rules/${id}`, body),
    remove: (id: number) => del<{ ok: boolean }>(`/rules/${id}`),
    preview: (body: RuleDraft) => post<RulePreview>("/rules/preview", body),
    matches: (id: number) => get<unknown[]>(`/rules/${id}/matches`),
  },
  channels: {
    list: () => get<Channel[]>("/channels"),
    types: () => get<ChannelType[]>("/channels/types"),
    create: (body: Partial<Channel>) => post<Channel>("/channels", body),
    update: (id: number, body: Partial<Channel>) => put<Channel>(`/channels/${id}`, body),
    remove: (id: number) => del<{ ok: boolean }>(`/channels/${id}`),
    test: (id: number) => post<{ ok: boolean; error?: string }>(`/channels/${id}/test`),
    log: () => get<NotificationLogEntry[]>("/channels/log"),
  },
  quietHours: {
    get: () => get<QuietHours>("/quiet-hours"),
    set: (body: QuietHours) => put<QuietHours>("/quiet-hours", body),
  },
  system: {
    info: () => get<SystemInfo>("/system/info"),
    logs: (level = "ALL", limit = 300) =>
      get<LogLine[]>(`/system/logs?level=${level}&limit=${limit}`),
    backupUrl: "/api/system/backup",
  },
  claimer: {
    status: () => get<ClaimerStatus>("/claimer/status"),
    log: () => get<{ log: string }>("/claimer/log"),
    scan: () => post<{ neue_ereignisse: number }>("/claimer/scan"),
  },
  statistik: {
    timeline: (tage = 30) => get<{ tage: number; punkte: TimelinePoint[] }>(
      `/stats/timeline?tage=${tage}`),
    quellen: (tage = 30) => get<QuellenStat[]>(`/stats/quellen?tage=${tage}`),
    haendler: () => get<HaendlerStat[]>("/stats/haendler"),
  },
  detail: (id: number) => get<DealDetail>(`/deals/${id}/detail`),
  alarm: (id: number, ziel_preis: number | null, notiz?: string | null) =>
    put<{ id: number; alarm_preis: number | null; notiz: string | null }>(
      `/deals/${id}/alarm`, { ziel_preis, notiz }),
  searches: {
    list: () => get<SavedSearch[]>("/searches"),
    create: (name: string, filter: Record<string, unknown>) =>
      post<SavedSearch>("/searches", { name, filter }),
    remove: (id: number) => del<{ ok: boolean }>(`/searches/${id}`),
  },
  settings: {
    get: () => get<AppSettings>("/settings"),
    set: (body: { waehrungskurse: Record<string, number>;
                  benachrichtigungen_pausiert: boolean }) =>
      put<AppSettings>("/settings", body),
  },
  bilder: {
    status: () => get<BilderStatus>("/bilder-status"),
    aufraeumen: () => post<{ entfernt: number }>("/bilder-aufraeumen"),
  },
  watch: {
    list: () => get<WatchItem[]>("/watch"),
    einzeln: (id: number) => get<WatchItem>(`/watch/${id}`),
    create: (body: Partial<WatchItem>) => post<WatchItem>("/watch", body),
    update: (id: number, body: Partial<WatchItem>) =>
      put<WatchItem>(`/watch/${id}`, body),
    remove: (id: number) => del<{ ok: boolean }>(`/watch/${id}`),
    pruefen: (id: number) => post<WatchTest>(`/watch/${id}/pruefen`),
    testen: (url: string) => post<WatchTest>("/watch-test", { url }),
  },
  urteil: {
    stufen: () => get<UrteilStufe[]>("/urteile"),
    neu: (dealId: number) =>
      post<{ stufe: string; label: string; text: string; punkte: number }>(
        `/deals/${dealId}/urteil`),
  },
  lernen: {
    status: () => get<LernStatus>("/empfehlungen/status"),
    regeln: () => get<RegelVorschlag[]>("/empfehlungen/regeln"),
    notiere: (dealId: number, art: string) =>
      post<{ ok: boolean }>(`/deals/${dealId}/interaktion`, { art }),
  },
  tokens: {
    list: () => get<ApiTokenInfo[]>("/tokens"),
    create: (name: string) =>
      post<{ id: number; name: string; token: string; hinweis: string }>(
        "/tokens", { name }),
    remove: (id: number) => del<{ ok: boolean }>(`/tokens/${id}`),
  },
  snooze: (sourceId: string, stunden: number) =>
    post<{ id: string; snooze_until: string | null }>(
      `/sources/${sourceId}/snooze?stunden=${stunden}`),
  restore: (payload: unknown) => post<Record<string, unknown>>("/system/restore", payload),
  csvUrl: (params: Record<string, boolean>) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v) q.set(k, "true");
    return `/api/deals/export.csv?${q}`;
  },
};
