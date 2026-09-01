import * as React from "react";

export type Theme = "dark" | "light" | "system";
const KEY = "sparbit-theme";

function systemPrefersLight(): boolean {
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ?? false;
}

function apply(theme: Theme): void {
  const light = theme === "light" || (theme === "system" && systemPrefersLight());
  const root = document.documentElement;
  root.classList.toggle("light", light);
  root.classList.toggle("dark", !light);
  root.style.colorScheme = light ? "light" : "dark";
}

export function useTheme() {
  const [theme, setTheme] = React.useState<Theme>(() => {
    try {
      const stored = localStorage.getItem(KEY);
      if (stored === "dark" || stored === "light" || stored === "system") return stored;
    } catch {
      /* privater Modus o. Ae. - dann eben die Vorgabe */
    }
    return "dark";
  });

  React.useEffect(() => {
    apply(theme);
    try {
      localStorage.setItem(KEY, theme);
    } catch {
      /* nicht schlimm, gilt dann nur fuer diese Sitzung */
    }
    if (theme !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: light)");
    const onChange = () => apply("system");
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [theme]);

  return { theme, setTheme };
}

/** Sofort beim Laden anwenden, damit es nicht kurz hell aufblitzt. */
export function initTheme(): void {
  try {
    const stored = localStorage.getItem(KEY) as Theme | null;
    apply(stored ?? "dark");
  } catch {
    apply("dark");
  }
}
