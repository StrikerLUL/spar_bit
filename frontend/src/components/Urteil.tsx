import { Award, HelpCircle, ThumbsUp, TrendingDown, TrendingUp } from "lucide-react";
import { useSprache } from "@/lib/i18n";
import { Badge } from "@/components/ui";
import { cn } from "@/lib/utils";

/** Abzeichen für das Preisurteil.
 *
 *  Bewusst mit Symbol UND Wort: allein an der Farbe soll niemand erkennen
 *  müssen, ob ein Preis gut ist.
 */
const STUFEN: Record<string, {
  label: string;
  variante: "success" | "warning" | "destructive" | "outline" | "default";
  Symbol: typeof Award;
}> = {
  bestpreis: { label: "Bestpreis", variante: "success", Symbol: Award },
  sehr_gut: { label: "sehr gut", variante: "success", Symbol: ThumbsUp },
  gut: { label: "guter Preis", variante: "default", Symbol: ThumbsUp },
  normal: { label: "normal", variante: "outline", Symbol: TrendingDown },
  teurer: { label: "war günstiger", variante: "warning", Symbol: TrendingUp },
  uvp_fragwuerdig: { label: "UVP fragwürdig", variante: "destructive", Symbol: TrendingUp },
  unbekannt: { label: "kein Urteil", variante: "outline", Symbol: HelpCircle },
};

export function UrteilBadge({
  stufe,
  text,
  className,
}: {
  stufe: string | null;
  text?: string | null;
  className?: string;
}) {
  const { t } = useSprache();
  if (!stufe || stufe === "unbekannt") return null;
  const eintrag = STUFEN[stufe];
  if (!eintrag) return null;
  const { label, variante, Symbol } = eintrag;

  return (
    <Badge variant={variante} className={cn("shadow-sm", className)}
           title={text ?? t(label)}>
      {/* Das Symbol ist Zugabe: das Wort daneben sagt dasselbe, und
          zweimal dasselbe vorzulesen hilft niemandem. */}
      <Symbol className="h-3 w-3" aria-hidden />
      {t(label)}
    </Badge>
  );
}

export const urteilLabel = (stufe: string): string =>
  STUFEN[stufe]?.label ?? stufe;
