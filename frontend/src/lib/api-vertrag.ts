/* Der handgeschriebene Client gegen das echte OpenAPI-Schema.
 *
 * `api.ts` ist von Hand gepflegt - 950 Zeilen Typen, die das Backend
 * nicht kennt. Wird dort ein Feld umbenannt, fällt das erst im Browser
 * auf, und zwar als `undefined`: also als fehlender Wert, nicht als
 * Fehler. Genau diese Sorte Abweichung ist hier gemeint.
 *
 * Diese Datei erzeugt keinen Code. Sie behauptet auf Typ-Ebene, dass die
 * handgeschriebenen Formen zu den erzeugten passen - `tsc --noEmit`
 * prüft das bei jedem Lauf mit, und die CI prüft zusätzlich, dass die
 * erzeugten Typen selbst noch aktuell sind.
 *
 * Erneuern, wenn sich das Backend geändert hat:
 *
 *     python backend/tools/openapi_export.py frontend/openapi.json
 *     npm --prefix frontend run api:types
 *
 * Bewusst nicht alles: geprüft wird, was das UI verschickt. Bei den
 * Antworten beschreibt FastAPI meist nur `dict` - dort gäbe es nichts
 * zu vergleichen, und eine Prüfung, die immer wahr ist, ist keine.
 */
import type { components } from "@/lib/api-typen";
import type { RuleDraft } from "@/lib/api";

type Schema = components["schemas"];

/** Behauptet: `A` kann überall stehen, wo `B` erwartet wird.
 *
 *  Passt es nicht, ist das Ergebnis kein `true`, sondern ein Objekt mit
 *  den fehlenden Schlüsseln - deren Namen dann im Typfehler stehen. Das
 *  ist der ganze Zweck: „Type 'false' is not assignable" hilft niemandem,
 *  `{ fehlt: "warengruppen" }` schon.
 */
type Passt<A, B> = [Exclude<keyof B, keyof A>] extends [never]
  ? true
  : { fehlt: Exclude<keyof B, keyof A> };

/* Eine Regel, wie das UI sie anlegt, muss jedes Pflichtfeld von
 * RuleBody tragen. */
export type RegelPasst = Passt<RuleDraft, Schema["RuleBody"]>;
const regelGeprueft: RegelPasst = true;

/* Die Felder, die diese Runde dazugekommen sind. Sie stehen einzeln da,
 * weil ein vergessenes Feld sonst nur im UI fehlt und sonst nirgends
 * auffällt - und ein Schreibfehler im Namen hier sofort rot wird. */
export type NeueFelder = {
  warengruppen: Schema["RuleBody"]["warengruppen"];
  render: Schema["GeneralSettings"]["render_url"];
  ollama: Schema["GeneralSettings"]["ollama_url"];
  zweifaktor: Schema["GeneralSettings"]["zweifaktor_pflicht"];
  waehrung: Schema["GeneralSettings"]["waehrung_automatisch"];
};

export const vertragGeprueft = { regelGeprueft } as const;
