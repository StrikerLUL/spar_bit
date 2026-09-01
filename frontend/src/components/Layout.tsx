import {
  BarChart3, Bell, Bookmark, Boxes, Command, Gift, LayoutDashboard, LogOut,
  Menu, Monitor, Moon, Radio, ScrollText, SlidersHorizontal, Sparkles, Sun, X,
} from "lucide-react";
import * as React from "react";
import { NavLink, useLocation } from "react-router-dom";
import type { Theme } from "@/lib/theme";
import { cn } from "@/lib/utils";
import { Button, StatusDot } from "@/components/ui";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/feed", label: "Feed", icon: Boxes },
  { to: "/statistiken", label: "Statistiken", icon: BarChart3 },
  { to: "/quellen", label: "Quellen", icon: Radio },
  { to: "/regeln", label: "Regeln", icon: SlidersHorizontal },
  { to: "/benachrichtigungen", label: "Benachrichtigungen", icon: Bell },
  { to: "/claimer", label: "Claimer", icon: Gift },
  { to: "/system", label: "Logs & System", icon: ScrollText },
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

  // Beim Seitenwechsel das mobile Menü schliessen.
  React.useEffect(() => setMobileOpen(false), [location.pathname]);

  const navItems = (
    <nav className="flex flex-col gap-0.5">
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            cn(
              "group flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium",
              "transition-colors duration-150",
              isActive
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:bg-accent hover:text-foreground",
            )
          }
        >
          {({ isActive }) => (
            <>
              <Icon className={cn("h-4 w-4 shrink-0 transition-transform",
                                  !isActive && "group-hover:scale-110")} />
              <span className="truncate">{label}</span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );

  return (
    <div className="min-h-dvh">
      {/* Desktop-Sidebar */}
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-60 flex-col border-r border-border bg-card/40 backdrop-blur-xl lg:flex">
        <Brand />
        <div className="px-3">
          <button
            type="button"
            onClick={onOpenPalette}
            className="flex w-full items-center gap-2 rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <Command className="h-3.5 w-3.5" />
            Schnellzugriff
            <kbd className="ml-auto rounded border border-border px-1 py-0.5 text-[10px]">
              ⌘K
            </kbd>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-3 py-4">{navItems}</div>
        <Footer connected={connected} username={username} onLogout={onLogout}
                theme={theme} setTheme={setTheme} />
      </aside>

      {/* Mobile-Kopfzeile */}
      <header className="sticky top-0 z-40 flex items-center gap-3 border-b border-border bg-background/85 px-4 py-3 backdrop-blur-xl lg:hidden">
        <Button variant="ghost" size="icon" onClick={() => setMobileOpen(true)}
          aria-label="Menü öffnen">
          <Menu className="h-5 w-5" />
        </Button>
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-primary" />
          <span className="font-semibold tracking-tight">SparBit</span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <StatusDot status={connected ? "ok" : "error"} pulse={connected} />
          <span className="text-xs text-muted-foreground">
            {connected ? "live" : "offline"}
          </span>
        </div>
      </header>

      {/* Mobile-Schublade */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/70 backdrop-blur-sm animate-fade-in"
            onClick={() => setMobileOpen(false)} aria-hidden />
          <aside className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-border bg-card shadow-2xl animate-slide-up">
            <div className="flex items-center justify-between pr-2">
              <Brand />
              <Button variant="ghost" size="icon" onClick={() => setMobileOpen(false)}
                aria-label="Menü schließen">
                <X className="h-5 w-5" />
              </Button>
            </div>
            <div className="flex-1 overflow-y-auto px-3 py-4">{navItems}</div>
            <Footer connected={connected} username={username} onLogout={onLogout}
                    theme={theme} setTheme={setTheme} />
          </aside>
        </div>
      )}

      <main className="lg:pl-60">
        <div className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
          {children}
        </div>
      </main>
    </div>
  );
}

const Brand = () => (
  <div className="flex h-16 items-center gap-2.5 px-5">
    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/15">
      <Sparkles className="h-4 w-4 text-primary" />
    </div>
    <div className="leading-tight">
      <p className="font-semibold tracking-tight">SparBit</p>
      <p className="text-[11px] text-muted-foreground">Deal-Zentrale</p>
    </div>
  </div>
);

const THEMES: Array<{ value: Theme; icon: typeof Sun; label: string }> = [
  { value: "light", icon: Sun, label: "Hell" },
  { value: "dark", icon: Moon, label: "Dunkel" },
  { value: "system", icon: Monitor, label: "System" },
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
}) => (
  <div className="border-t border-border p-3">
    <div className="mb-2 flex items-center gap-2 px-2 text-xs text-muted-foreground">
      <StatusDot status={connected ? "ok" : "error"} pulse={connected} />
      {connected ? "Live verbunden" : "Verbindung getrennt"}
    </div>

    <div className="mb-2 flex gap-1 rounded-md bg-muted/40 p-1">
      {THEMES.map(({ value, icon: Icon, label }) => (
        <button
          key={value}
          type="button"
          onClick={() => setTheme(value)}
          title={label}
          aria-label={`Thema: ${label}`}
          aria-pressed={theme === value}
          className={cn(
            "flex flex-1 items-center justify-center rounded py-1.5 transition-colors",
            theme === value
              ? "bg-card text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          <Icon className="h-3.5 w-3.5" />
        </button>
      ))}
    </div>

    <div className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5">
      <span className="truncate text-sm text-muted-foreground">{username ?? "—"}</span>
      <Button variant="ghost" size="icon" onClick={onLogout} aria-label="Abmelden"
        title="Abmelden">
        <LogOut className="h-4 w-4" />
      </Button>
    </div>
  </div>
);

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
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4 sm:mb-8">
      <div className="min-w-0 space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h1>
        {description && (
          <p className="max-w-2xl text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {action}
    </div>
  );
}

export { Bookmark };
