import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { SpracheProvider, gespeicherteSprache } from "./lib/i18n";
import { initTheme } from "./lib/theme";
import "./index.css";

// Vor dem ersten Rendern, damit die Seite nicht kurz im falschen Thema aufblitzt.
initTheme();
// Dasselbe fuer die Sprache: ohne lang-Attribut trennt der Browser
// englische Woerter nach deutschen Regeln, und ein Screenreader liest
// sie mit deutscher Aussprache vor.
document.documentElement.lang = gespeicherteSprache();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <SpracheProvider>
      <App />
    </SpracheProvider>
  </StrictMode>,
);
