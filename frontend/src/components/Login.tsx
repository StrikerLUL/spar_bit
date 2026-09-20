import { Tag } from "lucide-react";
import * as React from "react";
import { ApiError, api } from "@/lib/api";
import { Button, Card, Input, Label } from "@/components/ui";

/** Login und Setup-Assistent in einem - je nachdem, ob es schon einen
 *  Benutzer gibt. Es gibt bewusst kein Standard-Passwort. */
export function Login({
  setupMode,
  onDone,
}: {
  setupMode: boolean;
  onDone: () => void;
}) {
  const [username, setUsername] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [sperreBis, setSperreBis] = React.useState(0);

  // Countdown, damit man nicht ins Leere klickt, sondern sieht wie lange noch.
  React.useEffect(() => {
    if (sperreBis <= 0) return;
    const timer = window.setInterval(() => setSperreBis((s) => Math.max(0, s - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [sperreBis]);

  const tooShort = setupMode && password.length > 0 && password.length < 10;
  const mismatch = setupMode && confirm.length > 0 && password !== confirm;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    if (setupMode && password !== confirm) {
      setError("Die Passwörter stimmen nicht überein.");
      return;
    }
    setBusy(true);
    try {
      if (setupMode) await api.auth.setup(username, password);
      else await api.auth.login(username, password);
      onDone();
    } catch (err) {
      setError((err as Error).message);
      if (err instanceof ApiError && err.status === 429 && err.retryAfter) {
        setSperreBis(err.retryAfter);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-dvh items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <form onSubmit={submit} className="space-y-5 p-6 sm:p-8">
          <div className="space-y-2 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-primary/15">
              <Tag className="h-6 w-6 -rotate-90 text-primary" strokeWidth={2} />
            </div>
            <h1 className="text-xl font-semibold tracking-tight">
              {setupMode ? "SparBit einrichten" : "Willkommen zurück"}
            </h1>
            <p className="text-sm text-muted-foreground">
              {setupMode
                ? "Leg dein Konto an. Es gibt kein Standard-Passwort — was du hier setzt, gilt."
                : "Melde dich an, um weiterzumachen."}
            </p>
          </div>

          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="username">Benutzername</Label>
              <Input
                id="username"
                value={username}
                autoComplete="username"
                autoFocus
                required
                minLength={3}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Passwort</Label>
              <Input
                id="password"
                type="password"
                value={password}
                autoComplete={setupMode ? "new-password" : "current-password"}
                required
                onChange={(e) => setPassword(e.target.value)}
              />
              {tooShort && (
                <p className="text-xs text-warning">Mindestens 10 Zeichen.</p>
              )}
            </div>
            {setupMode && (
              <div className="space-y-1.5">
                <Label htmlFor="confirm">Passwort wiederholen</Label>
                <Input
                  id="confirm"
                  type="password"
                  value={confirm}
                  autoComplete="new-password"
                  required
                  onChange={(e) => setConfirm(e.target.value)}
                />
                {mismatch && (
                  <p className="text-xs text-destructive">
                    Die Passwörter stimmen nicht überein.
                  </p>
                )}
              </div>
            )}
          </div>

          {error && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          <Button type="submit" className="w-full" loading={busy}
            disabled={tooShort || mismatch || sperreBis > 0}>
            {sperreBis > 0
              ? `Gesperrt — noch ${sperreBis} Sekunden`
              : setupMode ? "Konto anlegen" : "Anmelden"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
