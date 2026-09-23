/* Konten im Haushalt und der zweite Faktor.
 *
 * Beides betrifft dieselbe Frage - wer hier hereinkommt -, darum stehen
 * sie zusammen. Herausgeloest aus System.tsx, das mit 1355 Zeilen an
 * der Stelle angekommen war, an der man vor dem Suchen erst scrollt.
 */
import {
  Copy,
  Users,
  Lock, ShieldCheck,
  } from "lucide-react";
import * as React from "react";
import {
  api, type Benutzer,
  type ZweiFaktorStatus,
} from "@/lib/api";
import { useAsync } from "@/lib/useEvents";
import { useToast } from "@/components/Toast";
import {
  cn, } from "@/lib/utils";
import {
  Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, Select, Skeleton, Switch,
} from "@/components/ui";



/** Konten im Haushalt.
 *
 *  Sichtbar für alle — wer zusammen wohnt, weiß ohnehin, wer mitliest.
 *  Ändern darf nur ein Admin. Abschalten statt löschen ist die
 *  vorsichtige Variante: Regeln und Wunschliste bleiben erhalten. */
export function BenutzerCard({ meineRolle }: { meineRolle: string | null }) {
  const toast = useToast();
  const { data, reload } = useAsync<Benutzer[]>(() => api.auth.benutzer(), []);
  const [offen, setOffen] = React.useState(false);
  const [name, setName] = React.useState("");
  const [passwort, setPasswort] = React.useState("");
  const [rolle, setRolle] = React.useState("mitglied");
  const admin = meineRolle === "admin";

  if (!data) return <Skeleton className="h-40" />;

  const anlegen = async () => {
    try {
      await api.auth.benutzerAnlegen({ username: name, password: passwort, rolle });
      setName("");
      setPasswort("");
      setOffen(false);
      reload();
      toast.push("success", "Konto angelegt",
        "Eigene Regeln, Kanäle und Wunschliste — getrennt von deinen.");
    } catch (err) {
      toast.push("error", "Anlegen fehlgeschlagen", (err as Error).message);
    }
  };

  const aendern = async (id: number, patch: { rolle?: string; aktiv?: boolean }) => {
    try {
      await api.auth.benutzerAendern(id, patch);
      reload();
    } catch (err) {
      toast.push("error", "Nicht möglich", (err as Error).message);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Users className="h-4 w-4 text-primary" />
          Konten
          <Badge variant="outline">{data.length}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <ul className="space-y-2">
          {data.map((u) => (
            <li key={u.id} className="flex items-center justify-between gap-2 text-xs">
              <span className={cn("truncate", !u.aktiv && "text-muted-foreground line-through")}>
                {u.username}
                {u.ich && <span className="ml-1 text-muted-foreground">(du)</span>}
                {u.zweifaktor && <span className="ml-1" title="Zweiter Faktor aktiv">🔒</span>}
              </span>
              {admin && !u.ich ? (
                <div className="flex shrink-0 items-center gap-1">
                  <Select value={u.rolle} className="h-7 w-28 text-xs"
                          onChange={(e) => void aendern(u.id, { rolle: e.target.value })}>
                    <option value="admin">Admin</option>
                    <option value="mitglied">Mitglied</option>
                    <option value="gast">Gast</option>
                  </Select>
                  <Switch checked={u.aktiv} label="Konto aktiv"
                          onChange={(an) => void aendern(u.id, { aktiv: an })} />
                </div>
              ) : (
                <Badge variant="outline">{u.rolle}</Badge>
              )}
            </li>
          ))}
        </ul>

        {admin && (offen ? (
          <div className="space-y-2 border-t border-border pt-3">
            <Input value={name} placeholder="Benutzername"
                   onChange={(e) => setName(e.target.value)} />
            <Input type="password" value={passwort}
                   placeholder="Passwort (mind. 10 Zeichen)"
                   autoComplete="new-password"
                   onChange={(e) => setPasswort(e.target.value)} />
            <Select value={rolle} onChange={(e) => setRolle(e.target.value)}>
              <option value="mitglied">Mitglied — eigene Regeln und Wunschliste</option>
              <option value="gast">Gast — darf nur zusehen</option>
              <option value="admin">Admin — verwaltet Quellen und Konten</option>
            </Select>
            <div className="flex gap-2">
              <Button className="flex-1" onClick={() => void anlegen()}
                      disabled={name.length < 3 || passwort.length < 10}>
                Anlegen
              </Button>
              <Button variant="ghost" onClick={() => setOffen(false)}>Abbrechen</Button>
            </div>
          </div>
        ) : (
          <Button variant="outline" className="w-full" onClick={() => setOffen(true)}>
            <Users className="h-4 w-4" />
            Konto hinzufügen
          </Button>
        ))}

        <p className="text-xs leading-relaxed text-muted-foreground">
          Jedes Konto hat eigene Regeln, Kanäle, Wunschlisten und gelernte
          Vorlieben. Gemeinsam bleiben Quellen, gesammelte Deals und die
          Systemeinstellungen.
        </p>
      </CardContent>
    </Card>
  );
}


/** Zweiter Faktor per Authenticator-App.
 *
 *  Scharf wird er erst, wenn ein Code aus der App wirklich stimmt -
 *  sonst sperrt sich aus, wessen App das Geheimnis nie bekommen hat. */
export function ZweiFaktorCard() {
  const toast = useToast();
  const { data, reload } = useAsync<ZweiFaktorStatus>(
    () => api.auth.zweifaktor(), []);
  const [einrichtung, setEinrichtung] = React.useState<
    { geheimnis: string; otpauth: string } | null>(null);
  const [code, setCode] = React.useState("");
  const [ersatz, setErsatz] = React.useState<string[] | null>(null);

  if (!data) return <Skeleton className="h-40" />;

  const starten = async () => {
    try {
      setEinrichtung(await api.auth.zweifaktorStart());
    } catch (err) {
      toast.push("error", "Einrichten fehlgeschlagen", (err as Error).message);
    }
  };

  const bestaetigen = async () => {
    try {
      const antwort = await api.auth.zweifaktorBestaetigen(code);
      setErsatz(antwort.ersatzcodes);
      setEinrichtung(null);
      setCode("");
      reload();
    } catch (err) {
      toast.push("error", "Code stimmt nicht", (err as Error).message);
    }
  };

  const abschalten = async () => {
    const passwort = window.prompt("Zum Abschalten dein Passwort:");
    if (!passwort) return;
    try {
      await api.auth.zweifaktorAus(passwort);
      setErsatz(null);
      reload();
      toast.push("success", "Zweiter Faktor aus");
    } catch (err) {
      toast.push("error", "Abschalten fehlgeschlagen", (err as Error).message);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className={cn("h-4 w-4", data.aktiv ? "text-success" : "text-muted-foreground")} />
          Zweiter Faktor
          {data.aktiv && <Badge variant="success">aktiv</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Bevor der naechste Admin-Klick in einem 403 endet. Ohne diesen
            Hinweis sieht die Pflicht aus wie ein Defekt: die Oberflaeche
            ist da, die Knoepfe gehen nicht. */}
        {data.faellig && (
          <p role="alert" className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-xs leading-relaxed">
            Diese Anlage verlangt von Administratoren einen zweiten Faktor.
            Bis er eingerichtet ist, bleiben die Admin-Funktionen gesperrt —
            anmelden und zusehen geht weiter.
          </p>
        )}

        {!data.aktiv && !einrichtung && (
          <>
            <p className="text-xs leading-relaxed text-muted-foreground">
              Ein Passwort schützt so gut, wie es geheim bleibt. Steht SparBit
              unter einer Domain im Netz, reicht ein wiederverwendetes Passwort
              aus einem fremden Datenleck — dagegen hilft keine Anmeldebremse.
            </p>
            <Button variant="outline" className="w-full" onClick={() => void starten()}>
              <Lock className="h-4 w-4" />
              Einrichten
            </Button>
          </>
        )}

        {einrichtung && (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">
              In der Authenticator-App hinzufügen — Adresse scannen oder den
              Schlüssel von Hand eintippen:
            </p>
            <code className="block break-all rounded-md bg-muted px-2 py-1.5 text-[11px]">
              {einrichtung.geheimnis}
            </code>
            <a href={einrichtung.otpauth}
               className="block truncate text-xs text-primary hover:underline"
               title={einrichtung.otpauth}>
              Direkt in der App öffnen
            </a>
            <Input
              value={code}
              inputMode="numeric"
              placeholder="Code aus der App"
              onChange={(e) => setCode(e.target.value)}
            />
            <div className="flex gap-2">
              <Button className="flex-1" disabled={code.length < 6}
                      onClick={() => void bestaetigen()}>
                Bestätigen
              </Button>
              <Button variant="ghost" onClick={() => setEinrichtung(null)}>
                Abbrechen
              </Button>
            </div>
          </div>
        )}

        {ersatz && (
          <div className="space-y-2 rounded-md border border-warning/40 bg-warning/10 p-3">
            <p className="text-xs font-medium text-warning">
              Ersatzcodes — jetzt aufschreiben. Sie werden nie wieder angezeigt.
            </p>
            <div className="grid grid-cols-2 gap-1 font-mono text-xs">
              {ersatz.map((c) => <span key={c}>{c}</span>)}
            </div>
            <Button variant="ghost" size="sm" className="w-full"
                    onClick={() => {
                      void navigator.clipboard.writeText(ersatz.join("\n"));
                      toast.push("success", "Kopiert");
                    }}>
              <Copy className="h-3.5 w-3.5" />
              Kopieren
            </Button>
          </div>
        )}

        {data.aktiv && (
          <>
            <p className="text-xs text-muted-foreground">
              Aktiv. Noch {data.ersatzcodes_uebrig} Ersatzcodes übrig.
            </p>
            <Button variant="ghost" className="w-full" onClick={() => void abschalten()}>
              Abschalten
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}


/** Sicherung: herunterladen, einspielen, automatische Laeufe ansehen.
 *
 *  Eine Sicherung enthaelt Bot-Token, API-Schluessel und Passwort-Hashes.
 *  Darum steht das Passwortfeld gleich daneben und nicht in einem Menue,
 *  das niemand findet. */
