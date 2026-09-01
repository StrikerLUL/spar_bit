import * as React from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { api, type AuthStatus, type LogLine } from "@/lib/api";
import { showDesktop } from "@/lib/notify";
import { useTheme } from "@/lib/theme";
import { useEventStream } from "@/lib/useEvents";
import { formatPrice } from "@/lib/utils";
import { CommandPalette, useShortcuts } from "@/components/CommandPalette";
import { Layout } from "@/components/Layout";
import { Login } from "@/components/Login";
import { ToastProvider } from "@/components/Toast";
import { Spinner } from "@/components/ui";
import { Claimer } from "@/pages/Claimer";
import { Dashboard, type LiveItem } from "@/pages/Dashboard";
import { Feed } from "@/pages/Feed";
import { Notifications } from "@/pages/Notifications";
import { Rules } from "@/pages/Rules";
import { Sources } from "@/pages/Sources";
import { Statistics } from "@/pages/Statistics";
import { System } from "@/pages/System";

const MAX_LIVE = 60;
const MAX_LOGS = 120;

export default function App() {
  const [auth, setAuth] = React.useState<AuthStatus | null>(null);
  const [live, setLive] = React.useState<LiveItem[]>([]);
  const [liveLogs, setLiveLogs] = React.useState<LogLine[]>([]);
  const { theme, setTheme } = useTheme();

  const refreshAuth = React.useCallback(() => {
    api.auth
      .status()
      .then(setAuth)
      .catch(() => setAuth({ setup_done: true, logged_in: false, username: null }));
  }, []);

  React.useEffect(refreshAuth, [refreshAuth]);

  // Ein SSE-Stream für die ganze App - Ticker, Logs und Desktop-Meldungen
  // hängen daran.
  const handlers = React.useMemo(
    () => ({
      deal: (data: unknown) =>
        setLive((current) =>
          [{ ...(data as LiveItem), _at: Date.now() }, ...current].slice(0, MAX_LIVE)),
      match: (data: unknown) => {
        const item = data as LiveItem;
        setLive((current) =>
          [{ ...item, _at: Date.now() }, ...current].slice(0, MAX_LIVE));
        // Nur echte Regeltreffer melden - jeder eingesammelte Deal wäre Lärm.
        showDesktop(
          item.ist_gratis ? `Gratis: ${item.titel}` : item.titel,
          `${item.ist_gratis ? "geschenkt" : formatPrice(item.preis ?? null,
            item.waehrung ?? "EUR")} · ${item.regel ?? item.quelle}`,
          item.url,
        );
      },
      alarm: (data: unknown) => {
        const item = data as LiveItem;
        setLive((current) =>
          [{ ...item, regel: "Preisalarm", _at: Date.now() }, ...current]
            .slice(0, MAX_LIVE));
        showDesktop(`Preisalarm: ${item.titel}`,
          formatPrice(item.preis ?? null, item.waehrung ?? "EUR"), item.url);
      },
      log: (data: unknown) =>
        setLiveLogs((current) => [data as LogLine, ...current].slice(0, MAX_LOGS)),
    }),
    [],
  );

  const connected = useEventStream(handlers, Boolean(auth?.logged_in));

  const logout = async () => {
    await api.auth.logout().catch(() => undefined);
    setLive([]);
    setLiveLogs([]);
    refreshAuth();
  };

  if (auth === null) {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <Spinner className="h-6 w-6 text-primary" />
      </div>
    );
  }

  if (!auth.logged_in) {
    return (
      <ToastProvider>
        <Login setupMode={!auth.setup_done} onDone={refreshAuth} />
      </ToastProvider>
    );
  }

  return (
    <ToastProvider>
      <BrowserRouter>
        <Shell
          connected={connected}
          username={auth.username}
          onLogout={logout}
          theme={theme}
          setTheme={setTheme}
          live={live}
          liveLogs={liveLogs}
        />
      </BrowserRouter>
    </ToastProvider>
  );
}

/** Eigene Komponente, weil die Tastenkürzel den Router-Kontext brauchen. */
function Shell({
  connected, username, onLogout, theme, setTheme, live, liveLogs,
}: {
  connected: boolean;
  username: string | null;
  onLogout: () => void;
  theme: ReturnType<typeof useTheme>["theme"];
  setTheme: ReturnType<typeof useTheme>["setTheme"];
  live: LiveItem[];
  liveLogs: LogLine[];
}) {
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  const openPalette = React.useCallback(() => setPaletteOpen(true), []);
  useShortcuts(openPalette);

  return (
    <>
      <Layout
        connected={connected}
        username={username}
        onLogout={onLogout}
        theme={theme}
        setTheme={setTheme}
        onOpenPalette={openPalette}
      >
        <Routes>
          <Route path="/" element={<Dashboard live={live} />} />
          <Route path="/feed" element={<Feed />} />
          <Route path="/statistiken" element={<Statistics />} />
          <Route path="/quellen" element={<Sources />} />
          <Route path="/regeln" element={<Rules />} />
          <Route path="/benachrichtigungen" element={<Notifications />} />
          <Route path="/claimer" element={<Claimer />} />
          <Route path="/system" element={<System liveLogs={liveLogs} />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Layout>
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        setTheme={setTheme}
      />
    </>
  );
}
