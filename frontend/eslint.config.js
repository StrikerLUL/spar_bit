// Flat-Config. Bewusst knapp gehalten: der Linter soll Fehler finden,
// nicht ueber Formatierung streiten - dafuer ist der Code zu handgesetzt.
import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      // Ungenutzte Variablen sind ein Fehler - ausser sie heissen bewusst _x.
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_", caughtErrors: "none" },
      ],
      // any kommt an den Raendern (API-Antworten) vor; dort ist es ehrlich.
      "@typescript-eslint/no-explicit-any": "off",
      // Das geschuetzte Leerzeichen zwischen Zahl und Einheit ist Absicht -
      // "12,99 EUR" darf nicht umbrechen.
      "no-irregular-whitespace": ["error", { skipStrings: true, skipTemplates: true }],
      // setState im Effekt ist ein Hinweis auf vermeidbare Renderrunden, aber
      // kein Fehler. Die Stellen im Bestand synchronisieren geladene Daten in
      // ein Formular - das umzubauen waere Risiko ohne sichtbaren Gewinn.
      "react-hooks/set-state-in-effect": "warn",
    },
  },
);
