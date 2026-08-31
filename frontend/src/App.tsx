import * as React from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { api, type AuthStatus, type LogLine } from "@/lib/api";
import { useEventStream } from "@/lib/useEvents";
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
import { System } from "@/pages/System";

const MAX_LIVE = 60;
const MAX_LOGS = 120;

export default function App() {
  const [auth, setAuth] = React.useState<AuthStatus | null>(null);
  const [live, setLive] = React.useState<LiveItem[]>([]);
  const [liveLogs, setLiveLogs] = React.useState<LogLine[]>([]);

  const refreshAuth = React.useCallback(() => {
    api.auth
      .status()
      .then(setAuth)
      .catch(() => setAuth({ setup_done: true, logged_in: false, username: null }));
  }, []);

  React.useEffect(refreshAuth, [refreshAuth]);

  // Ein SSE-Stream für die ganze App - Ticker und Logs hängen daran.
  const handlers = React.useMemo(
    () => ({
      deal: (data: unknown) =>
        setLive((current) =>
          [{ ...(data as LiveItem), _at: Date.now() }, ...current].slice(0, MAX_LIVE)),
      match: (data: unknown) =>
        setLive((current) =>
          [{ ...(data as LiveItem), _at: Date.now() }, ...current].slice(0, MAX_LIVE)),
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
        <Layout connected={connected} username={auth.username} onLogout={logout}>
          <Routes>
            <Route path="/" element={<Dashboard live={live} />} />
            <Route path="/feed" element={<Feed />} />
            <Route path="/quellen" element={<Sources />} />
            <Route path="/regeln" element={<Rules />} />
            <Route path="/benachrichtigungen" element={<Notifications />} />
            <Route path="/claimer" element={<Claimer />} />
            <Route path="/system" element={<System liveLogs={liveLogs} />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Layout>
      </BrowserRouter>
    </ToastProvider>
  );
}
