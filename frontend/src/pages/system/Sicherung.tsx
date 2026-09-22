/* Sicherungen: schreiben, herunterladen, einspielen.
 *
 * Der Teil der Systemseite, bei dem ein Fehler nicht nur laestig ist.
 * Darum steht er fuer sich.
 */
import {
  Download, HardDrive, RefreshCw, Trash2, Upload, } from "lucide-react";
import * as React from "react";
import {
  api, type AppSettings, type BackupListe, } from "@/lib/api";
import { useAsync } from "@/lib/useEvents";
import { useToast } from "@/components/Toast";
import {
  formatBytes, timeAgo,
} from "@/lib/utils";
import {
  Button, Card, CardContent, CardHeader, CardTitle, Input, Select, Switch,
} from "@/components/ui";

export function BackupCard() {
  const toast = useToast();
  const [passwort, setPasswort] = React.useState("");
  const [umfang, setUmfang] = React.useState("voll");
  const [laedt, setLaedt] = React.useState(false);
  const { data: liste, reload } = useAsync<BackupListe>(
    () => api.system.backupsListe(), []);
  const [einstellungen, setEinstellungen] = React.useState<AppSettings | null>(null);

  React.useEffect(() => {
    api.settings.get().then(setEinstellungen).catch(() => undefined);
  }, []);

  const herunterladen = async () => {
    if (!passwort) {
      window.open(`${api.system.backupUrl}?umfang=${umfang}`, "_blank");
      return;
    }
    setLaedt(true);
    try {
      const blob = await api.backupVerschluesselt(passwort, umfang);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `sparbit-backup-${new Date().toISOString().slice(0, 10)}.json.enc`;
      a.click();
      URL.revokeObjectURL(url);
      toast.push("success", "Verschlüsselte Sicherung geladen",
        "Ohne das Passwort lässt sie sich nicht mehr öffnen — gut aufheben.");
    } catch (err) {
      toast.push("error", "Sicherung fehlgeschlagen", (err as Error).message);
    } finally {
      setLaedt(false);
    }
  };

  const jetztSichern = async () => {
    try {
      const bericht = await api.system.backupJetzt();
      toast.push("success", "Sicherung geschrieben",
        `${bericht.datei}${bericht.alte_entfernt ? `, ${bericht.alte_entfernt} alte entfernt` : ""}`);
      reload();
    } catch (err) {
      toast.push("error", "Sicherung fehlgeschlagen", (err as Error).message);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <HardDrive className="h-4 w-4 text-primary" />
          Sicherung
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs leading-relaxed text-muted-foreground">
          Vollständig: Regeln, Kanäle, Quellen, Wunschliste, Preisverlauf,
          gelernte Interaktionen und Deals. <strong className="text-warning">
          Enthält API-Keys und Kanal-Tokens</strong> — mit Passwort wird die
          Datei verschlüsselt (AES-256).
        </p>

        <Select value={umfang} onChange={(e) => setUmfang(e.target.value)}>
          <option value="voll">Alles</option>
          <option value="einstellungen">Nur Einstellungen (für den Umzug)</option>
        </Select>

        <Input
          type="password"
          placeholder={liste?.verschluesselung_moeglich
            ? "Passwort (optional, verschlüsselt die Datei)"
            : "Verschlüsselung nicht verfügbar"}
          value={passwort}
          disabled={liste ? !liste.verschluesselung_moeglich : false}
          onChange={(e) => setPasswort(e.target.value)}
          autoComplete="new-password"
        />

        <Button variant="outline" className="w-full" loading={laedt}
                onClick={() => void herunterladen()}>
          <Download className="h-4 w-4" />
          Herunterladen
        </Button>

        <RestoreButton />

        <div className="space-y-2 border-t border-border pt-3">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-medium">Automatisch im Datenordner</span>
            <Button variant="ghost" size="sm" onClick={() => void jetztSichern()}>
              <RefreshCw className="h-3.5 w-3.5" />
              Jetzt
            </Button>
          </div>
          {einstellungen && (
            <div className="flex items-center justify-between gap-2 text-xs">
              <span className="text-muted-foreground">
                Täglich, {einstellungen.backup_behalten} aufheben
                {einstellungen.backup_passwort_gesetzt ? " (verschlüsselt)" : ""}
              </span>
              <Switch
                checked={einstellungen.backup_taeglich}
                onChange={async (an) => {
                  await api.settings.set({ backup_taeglich: an });
                  setEinstellungen({ ...einstellungen, backup_taeglich: an });
                }}
              />
            </div>
          )}
          {!liste?.dateien.length ? (
            <p className="text-xs text-muted-foreground">
              Noch keine — der tägliche Lauf legt sie unter{" "}
              <code className="text-[11px]">{liste?.ordner ?? "data/backups"}</code> ab.
            </p>
          ) : (
            <ul className="space-y-1">
              {liste.dateien.slice(0, 5).map((datei) => (
                <li key={datei.name}
                    className="flex items-center justify-between gap-2 text-xs">
                  <a href={api.system.backupDateiUrl(datei.name)}
                     className="truncate text-primary hover:underline"
                     title={datei.name}>
                    {datei.verschluesselt ? "🔒 " : ""}{timeAgo(datei.erstellt)}
                  </a>
                  <span className="shrink-0 text-muted-foreground">
                    {formatBytes(datei.bytes)}
                  </span>
                  <button
                    className="shrink-0 text-muted-foreground hover:text-destructive"
                    title="Löschen"
                    onClick={async () => {
                      await api.system.backupLoeschen(datei.name);
                      reload();
                    }}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  );
}


/** Sicherung zurueckspielen. Konfiguration wird ersetzt, gesammelte Daten
 *  werden ergaenzt - was seit der Sicherung dazukam, bleibt stehen. */
export function RestoreButton() {
  const toast = useToast();
  const input = React.useRef<HTMLInputElement>(null);
  const [laeuft, setLaeuft] = React.useState(false);

  const einlesen = async (datei: File) => {
    setLaeuft(true);
    try {
      const inhalt = JSON.parse(await datei.text());
      let passwort: string | undefined;
      if (inhalt?.sparbit_backup === "verschluesselt") {
        passwort = window.prompt(
          "Diese Sicherung ist verschlüsselt. Passwort:") ?? undefined;
        if (!passwort) { setLaeuft(false); return; }
      }
      const bericht = await api.restore(inhalt, passwort) as Record<string, number>;
      toast.push("success", "Sicherung eingespielt",
        `${bericht.regeln} Regeln, ${bericht.kanaele} Kanäle, ${bericht.quellen} Quellen, `
        + `${bericht.deals} Deals, ${bericht.wunschliste} Wunschartikel, `
        + `${bericht.interaktionen} gelernte Spuren. Seite neu laden.`);
    } catch (err) {
      toast.push("error", "Einspielen fehlgeschlagen", (err as Error).message);
    } finally {
      setLaeuft(false);
      if (input.current) input.current.value = "";
    }
  };

  return (
    <>
      <input
        ref={input}
        type="file"
        accept="application/json,.json,.enc"
        className="hidden"
        onChange={(e) => {
          const datei = e.target.files?.[0];
          if (datei) void einlesen(datei);
        }}
      />
      <Button
        variant="ghost"
        className="w-full"
        loading={laeuft}
        onClick={() => {
          if (window.confirm(
            "Sicherung einspielen? Regeln, Kanäle und gespeicherte Suchen "
            + "werden ersetzt. Deals, Wunschliste und Verlauf werden ergänzt — "
            + "was seitdem dazukam, bleibt stehen.")) {
            input.current?.click();
          }
        }}
      >
        <Upload className="h-4 w-4" />
        Sicherung einspielen
      </Button>
    </>
  );
}


/** Bild-Cache: Zustand und Aufräumen. */
