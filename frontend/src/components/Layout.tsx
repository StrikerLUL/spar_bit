import {
  AlertTriangle, BarChart3, Bell, Bookmark, Boxes, Command, Eye, Gauge, Gift,
  Lock, LogOut, Menu, Monitor, Moon, Radio, ScrollText, SlidersHorizontal, Sun,
  Tag, X,
} from "lucide-react";
import * as React from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { api, type ErwachsenStatus, type ProblemStatus } from "@/lib/api";
import { useSprache, type Sprache } from "@/lib/i18n";
import type { Theme } from "@/lib/theme";
import { useAsync } from "@/lib/useEvents";
import { cn } from "@/lib/utils";
import { Button, StatusDot } from "@/components/ui";

interface NavPunkt {
  to: string;
  label: string;
  icon: typeof Gauge;
  end?: boolean;
}

// In Gruppen statt einer flachen Liste: neun gleichrangige Punkte zwingen
// dazu, jedes Mal alle zu lesen. "Preisfehler" steht bewusst direkt unter
// der Uebersicht - es ist der Punkt, fuer den es dieses Programm gibt.
const NAV: Array<{ gruppe: string; punkte: NavPunkt[] }> = [
  {
    gruppe: "Finden",
    punkte: [
      { to: "/", label: "Übersicht", icon: Gauge, end: true },
      { to: "/preisfehler", label: "Preisfehler", icon: AlertTriangle },
      { to: "/feed", label: "Feed", icon: Boxes },
      { to: "/wunschliste", label: "Wunschliste", icon: Eye },
    ],
  },
  {
    gruppe: "Einstellen",
    punkte: [
      { to: "/regeln", label: "Regeln", icon: SlidersHorizontal },
      { to: "/benachrichtigungen", label: "Kanäle", icon: Bell },
      { to: "/quellen", label: "Quellen", icon: Radio },
    ],
  },
  {
    gruppe: "Nachsehen",
    punkte: [
      { to: "/statistiken", label: "Statistiken", icon: BarChart3 },
      { to: "/claimer", label: "Claimer", icon: Gift },
      { to: "/system", label: "Logs & System", icon: ScrollText },
    ],
  },
];

export function Layout({
  children,
  connected,
  username,
  onLogout,
  theme,
  setTheme,
  onOpenPalette,
}: {
  children: React.ReactNode;
  connected: boolean;
  username: string | null;
  onLogout: () => void;
  theme: Theme;
  setTheme: (theme: Theme) => void;
  onOpenPalette: () => void;
}) {
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const location = useLocation();
  const { t } = useSprache();

  // Der 18+-Punkt erscheint nur, wenn der Bereich freigeschaltet ist. Beim
  // Seitenwechsel neu geladen, damit das Umlegen des Schalters unter
  // "Logs & System" ohne Neuladen der Seite ankommt.
  const { data: erwachsen } = useAsync<ErwachsenStatus>(
    () => api.system.erwachsen(), [location.pathname]);

  // Beim Seitenwechsel das mobile Menü schliessen.
  React.useEffect(() => setMobileOpen(false), [location.pathname]);

  // Fokus in die Schublade holen, sobald sie aufgeht. Ohne das bleibt er
  // auf dem Knopf dahinter: wer mit der Tastatur bedient, tabbt dann durch
  // die verdeckte Seite und landet nie im Menü.
  const schubladeRef = React.useRef<HTMLElement | null>(null);
  React.useEffect(() => {
    if (!mobileOpen) return;
    const erstes = schubladeRef.current?.querySelector<HTMLElement>(
      "a, button, [tabindex]:not([tabindex='-1'])");
    erstes?.focus();
  }, [mobileOpen]);

  const gruppen = React.useMemo(() => {
    if (!erwachsen?.an) return NAV;
    return NAV.map((g) =>
      g.gruppe === "Finden"
        ? { ...g, punkte: [...g.punkte, { to: "/18plus", label: "18+", icon: Lock }] }
        : g);
  }, [erwachsen?.an]);

  const navItems = (
    <nav className="flex flex-col gap-5" aria-label={t("Menü öffnen")}>
      {gruppen.map(({ gruppe, punkte }) => (
        <div key={gruppe}>
          <p className="label mb-1.5 px-2.5" id={`nav-${gruppe}`}>{t(gruppe)}</p>
          <div className="flex flex-col gap-px" role="group"
               aria-labelledby={`nav-${gruppe}`}>
            {punkte.map(({ to, label, icon: Icon, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-2.5 rounded-sm border-l-2 py-1.5 pl-2 pr-2.5",
                    "text-[13px] transition-colors duration-100",
                    // Aktiv wird mit einer Kante links markiert statt mit einer
                    // Farbflaeche: die Flaeche konkurriert sonst mit allem
                    // anderen Farbigen auf der Seite, und farbig ist hier nur
                    // reserviert fuer Preise und Preisfehler.
                    isActive
                      ? "border-primary bg-accent font-medium text-foreground"
                      : "border-transparent text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                  )
                }
              >
                <Icon className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} />
                <span className="truncate">{t(label)}</span>
              </NavLink>
            ))}
          </div>
        </div>
      ))}
    </nav>
  );

  return (
    <div className="min-h-dvh">
      {/* Desktop-Sidebar */}
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-56 flex-col border-r border-border bg-card lg:flex">
        <Brand />
        <div className="px-3">
          <button
            type="button"
            onClick={onOpenPalette}
            aria-keyshortcuts="Meta+K Control+K"
            className="flex w-full items-center gap-2 rounded-sm border border-border px-2.5 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <Command className="h-3.5 w-3.5" aria-hidden />
            {t("Schnellzugriff öffnen")}
            <kbd className="ml-auto rounded border border-border px-1 py-0.5 text-[10px]">
              ⌘K
            </kbd>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-2.5 py-4">{navItems}</div>
        <Footer connected={connected} username={username} onLogout={onLogout}
                theme={theme} setTheme={setTheme} />
      </aside>

      {/* Mobile-Kopfzeile */}
      <header className="sticky top-0 z-40 flex items-center gap-3 border-b border-border bg-card px-4 py-2.5 lg:hidden">
        <Button variant="ghost" size="icon" onClick={() => setMobileOpen(true)}
          aria-label={t("Menü öffnen")}
          aria-expanded={mobileOpen} aria-controls="mobile-menue">
          <Menu className="h-5 w-5" />
        </Button>
        <div className="flex items-center gap-2">
          <Tag className="h-4 w-4 -rotate-90 text-primary" strokeWidth={2} />
          <span className="font-semibold tracking-tight">SparBit</span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <StatusDot status={connected ? "ok" : "error"} pulse={connected} />
          <span className="text-xs text-muted-foreground" role="status">
            {connected ? t("Verbunden") : t("Keine Verbindung")}
          </span>
        </div>
      </header>

      {/* Mobile-Schublade */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true"
             aria-label={t("Menü öffnen")} id="mobile-menue"
             onKeyDown={(e) => { if (e.key === "Escape") setMobileOpen(false); }}>
          <div className="absolute inset-0 bg-black/65 animate-fade-in"
            onClick={() => setMobileOpen(false)} aria-hidden />
          <aside ref={schubladeRef}
            className="absolute inset-y-0 left-0 flex w-64 max-w-[85vw] flex-col border-r border-border bg-card shadow-xl shadow-black/40">
            <div className="flex items-center justify-between pr-2">
              <Brand />
              <Button variant="ghost" size="icon" onClick={() => setMobileOpen(false)}
                aria-label={t("Menü schließen")}>
                <X className="h-5 w-5" />
              </Button>
            </div>
            <div className="flex-1 overflow-y-auto px-2.5 py-4">{navItems}</div>
            <Footer connected={connected} username={username} onLogout={onLogout}
                    theme={theme} setTheme={setTheme} />
          </aside>
        </div>
      )}

      <main className="lg:pl-56">
        <div className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
          <ProblemBanner />
          {children}
        </div>
      </main>
    </div>
  );
}

/** Wortmarke.
 *
 *  Kein Funkel-Symbol mehr: das Sparkles-Icon steht inzwischen fuer "hier
 *  war ein Generator am Werk" und sagt ueber dieses Programm nichts aus.
 *  Ein Preisschild sagt, worum es geht.
 */
const Brand = () => (
  <div className="flex h-14 items-center gap-2.5 border-b border-border px-4">
    <Tag className="h-4 w-4 shrink-0 -rotate-90 text-primary" strokeWidth={2} />
    <div className="leading-none">
      <p className="text-[15px] font-semibold tracking-tight">SparBit</p>
      <p className="mt-1 text-[10px] uppercase tracking-[0.13em] text-muted-foreground">
        Preiswächter
      </p>
    </div>
  </div>
);

const THEMES: Array<{ value: Theme; icon: typeof Sun; label: string }> = [
  { value: "light", icon: Sun, label: "Hell" },
  { value: "dark", icon: Moon, label: "Dunkel" },
  { value: "system", icon: Monitor, label: "Wie im System" },
];

// Die Sprachnamen stehen in ihrer eigenen Sprache. Wer die Oberflaeche
// gerade nicht lesen kann, sucht nach "English" und nicht nach "Englisch".
const SPRACHEN: Array<{ value: Sprache; kurz: string; label: string }> = [
  { value: "de", kurz: "DE", label: "Deutsch" },
  { value: "en", kurz: "EN", label: "English" },
];

const Footer = ({
  connected,
  username,
  onLogout,
  theme,
  setTheme,
}: {
  connected: boolean;
  username: string | null;
  onLogout: () => void;
  theme: Theme;
  setTheme: (theme: Theme) => void;
}) => {
  const { sprache, setSprache, t } = useSprache();
  return (
  <div className="border-t border-border p-3">
    <div className="mb-2 flex items-center gap-2 px-2 text-xs text-muted-foreground"
         role="status">
      <StatusDot status={connected ? "ok" : "error"} pulse={connected} />
      {connected ? t("Verbunden") : t("Keine Verbindung")}
    </div>

    {/* Thema. role="group" statt loser Knoepfe: ein Screenreader liest
        sonst drei unverbundene Schalter vor, von denen zwei dasselbe
        Symbol tragen. */}
    <div className="mb-2 flex gap-px rounded-sm border border-border p-px"
         role="group" aria-label={t("Hell") + " / " + t("Dunkel")}>
      {THEMES.map(({ value, icon: Icon, label }) => (
        <button
          key={value}
          type="button"
          onClick={() => setTheme(value)}
          title={t(label)}
          aria-label={t(label)}
          aria-pressed={theme === value}
          className={cn(
            "flex flex-1 items-center justify-center rounded-[2px] py-1 transition-colors",
            theme === value
              ? "bg-accent text-foreground"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          <Icon className="h-3.5 w-3.5" aria-hidden />
        </button>
      ))}
    </div>

    <div className="mb-2 flex gap-px rounded-sm border border-border p-px"
         role="group" aria-label={t("Sprache")}>
      {SPRACHEN.map(({ value, kurz, label }) => (
        <button
          key={value}
          type="button"
          lang={value}
          onClick={() => setSprache(value)}
          title={label}
          aria-label={label}
          aria-pressed={sprache === value}
          className={cn(
            "flex-1 rounded-[2px] py-1 text-[11px] font-medium tracking-wide transition-colors",
            sprache === value
              ? "bg-accent text-foreground"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {kurz}
        </button>
      ))}
    </div>

    <div className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5">
      <span className="truncate text-sm text-muted-foreground">{username ?? "—"}</span>
      <Button variant="ghost" size="icon" onClick={onLogout} aria-label={t("Abmelden")}
        title={t("Abmelden")}>
        <LogOut className="h-4 w-4" aria-hidden />
      </Button>
    </div>
  </div>
  );
};

export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-4 border-b border-border pb-4">
      <div className="min-w-0 space-y-1">
        <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">{title}</h1>
        {description && (
          <p className="max-w-2xl text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {action}
    </div>
  );
}

export { Bookmark };


/** Warnt oben auf jeder Seite, wenn SparBit selbst nicht rund läuft.
 *
 *  Der gefährlichste Ausfall eines Wächters ist der stille: eine gesperrte
 *  Quelle sieht von außen aus wie "heute keine Deals". Darum steht das
 *  nicht nur in den Einstellungen, sondern überall im Weg.
 */
function ProblemBanner() {
  const { data, reload } = useAsync<ProblemStatus>(
    () => api.system.probleme(), []);
  const [zu, setZu] = React.useState(false);

  // Alle zwei Minuten nachsehen: ein Ausfall soll auffallen, ohne dass man
  // die Seite neu lädt - aber auch ohne dauernd zu fragen.
  React.useEffect(() => {
    const timer = window.setInterval(reload, 120_000);
    return () => window.clearInterval(timer);
  }, [reload]);

  const probleme = data?.probleme ?? [];
  if (!probleme.length || zu) return null;

  return (
    <div className="mb-6 rounded-lg border border-warning/40 bg-warning/10 p-4">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">
            {probleme.length === 1
              ? "SparBit läuft nicht rund"
              : `${probleme.length} Dinge laufen nicht rund`}
          </p>
          <ul className="mt-1.5 space-y-1">
            {probleme.slice(0, 4).map((p) => (
              <li key={`${p.art}:${p.betrifft}`} className="text-xs leading-relaxed">
                <span className="text-foreground/90">{p.text}</span>
                {p.rat && (
                  <span className="ml-1 text-muted-foreground">{p.rat}</span>
                )}
              </li>
            ))}
          </ul>
          <Link to="/system"
            className="mt-2 inline-block text-xs font-medium text-primary hover:underline">
            Unter Logs &amp; System ansehen
          </Link>
        </div>
        <button type="button" onClick={() => setZu(true)}
          aria-label="Hinweis schließen"
          className="shrink-0 rounded p-1 text-muted-foreground hover:text-foreground">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
