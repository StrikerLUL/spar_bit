import {
  Bell, Boxes, Gift, LayoutDashboard, Moon, Radio, ScrollText, Search,
  SlidersHorizontal, Sun, BarChart3, Monitor,
} from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import type { Theme } from "@/lib/theme";
import { cn } from "@/lib/utils";

interface Command {
  id: string;
  label: string;
  hint?: string;
  icon: React.ReactNode;
  run: () => void;
}

/** Schnellzugriff mit Strg/Cmd+K - Seiten wechseln, Thema umstellen. */
export function CommandPalette({
  open,
  onClose,
  setTheme,
}: {
  open: boolean;
  onClose: () => void;
  setTheme: (theme: Theme) => void;
}) {
  const navigate = useNavigate();
  const [query, setQuery] = React.useState("");
  const [index, setIndex] = React.useState(0);
  const inputRef = React.useRef<HTMLInputElement>(null);

  const commands = React.useMemo<Command[]>(() => {
    const go = (to: string) => () => { navigate(to); onClose(); };
    const theme = (t: Theme) => () => { setTheme(t); onClose(); };
    return [
      { id: "dash", label: "Dashboard", hint: "g d",
        icon: <LayoutDashboard className="h-4 w-4" />, run: go("/") },
      { id: "feed", label: "Feed", hint: "g f",
        icon: <Boxes className="h-4 w-4" />, run: go("/feed") },
      { id: "stats", label: "Statistiken", hint: "g s",
        icon: <BarChart3 className="h-4 w-4" />, run: go("/statistiken") },
      { id: "src", label: "Quellen", hint: "g q",
        icon: <Radio className="h-4 w-4" />, run: go("/quellen") },
      { id: "rules", label: "Regeln", hint: "g r",
        icon: <SlidersHorizontal className="h-4 w-4" />, run: go("/regeln") },
      { id: "notif", label: "Benachrichtigungen", hint: "g b",
        icon: <Bell className="h-4 w-4" />, run: go("/benachrichtigungen") },
      { id: "claim", label: "Claimer", hint: "g c",
        icon: <Gift className="h-4 w-4" />, run: go("/claimer") },
      { id: "sys", label: "Logs & System", hint: "g l",
        icon: <ScrollText className="h-4 w-4" />, run: go("/system") },
      { id: "gratis", label: "Nur Gratis-Funde zeigen",
        icon: <Gift className="h-4 w-4" />, run: go("/feed?gratis=1") },
      { id: "dark", label: "Dunkles Thema",
        icon: <Moon className="h-4 w-4" />, run: theme("dark") },
      { id: "light", label: "Helles Thema",
        icon: <Sun className="h-4 w-4" />, run: theme("light") },
      { id: "system", label: "Thema wie im System",
        icon: <Monitor className="h-4 w-4" />, run: theme("system") },
    ];
  }, [navigate, onClose, setTheme]);

  const treffer = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((c) => c.label.toLowerCase().includes(q));
  }, [commands, query]);

  React.useEffect(() => {
    if (open) {
      setQuery("");
      setIndex(0);
      window.setTimeout(() => inputRef.current?.focus(), 20);
    }
  }, [open]);

  React.useEffect(() => setIndex(0), [query]);

  if (!open) return null;

  const onKey = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setIndex((i) => (i + 1) % Math.max(1, treffer.length));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setIndex((i) => (i - 1 + treffer.length) % Math.max(1, treffer.length));
    } else if (event.key === "Enter") {
      event.preventDefault();
      treffer[index]?.run();
    } else if (event.key === "Escape") {
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-start justify-center pt-[12vh]">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm animate-fade-in"
           onClick={onClose} aria-hidden />
      <div role="dialog" aria-modal="true" aria-label="Schnellzugriff"
           onKeyDown={onKey}
           className="relative z-10 w-full max-w-lg overflow-hidden rounded-lg border border-border bg-card shadow-2xl animate-slide-up">
        <div className="flex items-center gap-3 border-b border-border px-4">
          <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Wohin? Tippen zum Filtern …"
            className="h-12 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
          <kbd className="shrink-0 rounded border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground">
            Esc
          </kbd>
        </div>
        <ul className="max-h-80 overflow-y-auto p-2">
          {treffer.length === 0 ? (
            <li className="px-3 py-6 text-center text-sm text-muted-foreground">
              Nichts gefunden.
            </li>
          ) : (
            treffer.map((command, i) => (
              <li key={command.id}>
                <button
                  type="button"
                  onMouseEnter={() => setIndex(i)}
                  onClick={command.run}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm transition-colors",
                    i === index ? "bg-accent text-foreground" : "text-muted-foreground",
                  )}
                >
                  <span className={i === index ? "text-primary" : ""}>{command.icon}</span>
                  <span className="flex-1">{command.label}</span>
                  {command.hint && (
                    <kbd className="rounded border border-border px-1.5 py-0.5 text-[10px]">
                      {command.hint}
                    </kbd>
                  )}
                </button>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}

/** Tastenkuerzel: Strg/Cmd+K oeffnet die Palette, "g" gefolgt von einem
 *  Buchstaben springt direkt, "/" springt in die Suche. */
export function useShortcuts(openPalette: () => void) {
  const navigate = useNavigate();
  const pending = React.useRef<number | null>(null);

  React.useEffect(() => {
    const ziele: Record<string, string> = {
      d: "/", f: "/feed", s: "/statistiken", q: "/quellen", r: "/regeln",
      b: "/benachrichtigungen", c: "/claimer", l: "/system",
    };

    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const tippt = target && (
        target.tagName === "INPUT" || target.tagName === "TEXTAREA" ||
        target.tagName === "SELECT" || target.isContentEditable);

      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        openPalette();
        return;
      }
      if (tippt || event.metaKey || event.ctrlKey || event.altKey) return;

      if (event.key === "/") {
        event.preventDefault();
        const suche = document.querySelector<HTMLInputElement>("[data-suchfeld]");
        if (suche) suche.focus();
        else navigate("/feed");
        return;
      }
      if (event.key === "?") {
        event.preventDefault();
        openPalette();
        return;
      }
      if (event.key === "g") {
        window.clearTimeout(pending.current ?? undefined);
        pending.current = window.setTimeout(() => { pending.current = null; }, 1200);
        return;
      }
      if (pending.current !== null && ziele[event.key.toLowerCase()]) {
        event.preventDefault();
        window.clearTimeout(pending.current);
        pending.current = null;
        navigate(ziele[event.key.toLowerCase()]);
      }
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate, openPalette]);
}
