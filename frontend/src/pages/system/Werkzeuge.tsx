/* Drei Schalter, die selten angefasst werden - und die man dann an einer
 * Stelle sucht.
 *
 * Die Pflicht zum zweiten Faktor für Administratoren, der Render-Dienst
 * für Shops, die ihren Preis erst per JavaScript einsetzen, und ein
 * lokales Sprachmodell für Warengruppen, die aus Stichwörtern nicht
 * hervorgehen. Alle drei sind aus, bis jemand sie einschaltet.
 */
import { Cpu, Globe, ShieldAlert } from "lucide-react";
import * as React from "react";
import { api, type AppSettings } from "@/lib/api";
import { useAsync } from "@/lib/useEvents";
import { useToast } from "@/components/Toast";
import {
  Button, Card, CardContent, CardHeader, CardTitle, Input, Label, Skeleton, Switch,
} from "@/components/ui";

export function SicherheitCard() {
  const toast = useToast();
  const { data, reload } = useAsync<AppSettings>(() => api.settings.get(), []);

  if (!data) return <Skeleton className="h-40" />;

  const umschalten = async (an: boolean) => {
    try {
      await api.settings.set({ zweifaktor_pflicht: an });
      toast.push("success", an
        ? "Zweiter Faktor ist jetzt Pflicht für Administratoren"
        : "Pflicht aufgehoben");
      reload();
    } catch (err) {
      // Der häufigste Fall: man hat selbst noch keinen. Das Backend sagt
      // das im Klartext, und genau der Text gehört hierher.
      toast.push("error", "Nicht geändert", (err as Error).message);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 text-primary" aria-hidden />
          Sicherheit der Anlage
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <Label id="zf-pflicht">Administratoren brauchen einen zweiten Faktor</Label>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              Ein Admin-Konto kann Quellen umstellen, Updates einspielen und
              Sicherungen herunterladen — und in denen stehen die Geheimnisse
              aller Konten. Gesperrt werden nur die Admin-Funktionen: anmelden
              und den zweiten Faktor einrichten geht weiter, sonst wäre das
              eine Aussperrung statt einer Hürde.
            </p>
          </div>
          <Switch
            labelledBy="zf-pflicht"
            checked={Boolean(data.zweifaktor_pflicht)}
            onChange={(an) => void umschalten(an)}
          />
        </div>
      </CardContent>
    </Card>
  );
}

export function WerkzeugeCard() {
  const toast = useToast();
  const { data, reload } = useAsync<AppSettings>(() => api.settings.get(), []);
  const [render, setRender] = React.useState<string | null>(null);
  const [ollama, setOllama] = React.useState<string | null>(null);
  const [modell, setModell] = React.useState<string | null>(null);

  if (!data) return <Skeleton className="h-64" />;

  // Erst beim Tippen vom Server abgekoppelt: so überschreibt ein Neuladen
  // im Hintergrund keine halb getippte Adresse.
  const renderWert = render ?? data.render_url ?? "";
  const ollamaWert = ollama ?? data.ollama_url ?? "";
  const modellWert = modell ?? data.ollama_modell ?? "";

  const speichern = async (felder: Partial<AppSettings>) => {
    try {
      await api.settings.set(felder);
      toast.push("success", "Gespeichert");
      setRender(null);
      setOllama(null);
      setModell(null);
      reload();
    } catch (err) {
      toast.push("error", "Speichern fehlgeschlagen", (err as Error).message);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Cpu className="h-4 w-4 text-primary" aria-hidden />
          Optionale Helfer
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="space-y-1.5">
          <Label htmlFor="render-url" className="flex items-center gap-1.5">
            <Globe className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
            Render-Dienst für die Wunschliste
          </Label>
          <p className="text-xs leading-relaxed text-muted-foreground">
            Manche Shops setzen den Preis erst per JavaScript ein. Im rohen
            HTML steht dann nichts, und SparBit sagt ehrlich „kann ich nicht
            lesen“. Wer es trotzdem braucht, stellt einen Render-Dienst
            daneben (browserless, ein eigener Playwright-Container) und trägt
            dessen Adresse hier ein. In der Adresse muss <code>{"{url}"}</code>
            {" "}vorkommen — dort setzt SparBit die Produktseite ein.
          </p>
          <Input
            id="render-url"
            value={renderWert}
            placeholder="http://browserless:3000/content?url={url}"
            onChange={(e) => setRender(e.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            Leer = aus. Je Artikel lässt sich dann einzeln wählen, ob er über
            den Dienst geholt wird.
          </p>
          <Button size="sm" variant="outline"
                  onClick={() => void speichern({ render_url: renderWert })}>
            Render-Dienst speichern
          </Button>
        </div>

        <div className="space-y-1.5 border-t border-border pt-4">
          <Label htmlFor="ollama-url" className="flex items-center gap-1.5">
            <Cpu className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
            Lokales Sprachmodell für Warengruppen
          </Label>
          <p className="text-xs leading-relaxed text-muted-foreground">
            Die Warengruppe entsteht aus Stichwörtern — nachvollziehbar, aber
            bei Titeln wie „Philips HD9200/90“ chancenlos. Für genau diesen
            Rest kann ein lokales Ollama einspringen. Es sieht nur, was die
            Stichwörter nicht erkannt haben, und darf nur aus zwölf
            vorgegebenen Gruppen wählen.
          </p>
          <Input
            id="ollama-url"
            value={ollamaWert}
            placeholder="http://127.0.0.1:11434"
            onChange={(e) => setOllama(e.target.value)}
          />
          <Label htmlFor="ollama-modell" className="pt-1">Modell</Label>
          <Input
            id="ollama-modell"
            value={modellWert}
            placeholder="llama3.2:3b"
            onChange={(e) => setModell(e.target.value)}
          />
          <p className="text-xs leading-relaxed text-muted-foreground">
            Leer = aus. <strong>Nur lokal gedacht:</strong> wer hier eine
            fremde Cloud einträgt, schickt ihr jeden unerkannten Deal-Titel.
            SparBit hält niemanden davon ab — es steht nur hier.
          </p>
          <Button size="sm" variant="outline"
                  onClick={() => void speichern({
                    ollama_url: ollamaWert, ollama_modell: modellWert,
                  })}>
            Modell speichern
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
