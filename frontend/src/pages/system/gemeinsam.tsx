/* Kleinteile, die sich mehrere Karten der Systemseite teilen.
 *
 * Sie standen alle in System.tsx, weil sie dort entstanden sind. Nach
 * dem Aufteilen der Seite haben sie keinen eigenen Ort - also hier.
 */
export const LEVEL_STYLES: Record<string, string> = {
  DEBUG: "text-muted-foreground/70",
  INFO: "text-foreground/80",
  WARNING: "text-warning",
  ERROR: "text-destructive",
  CRITICAL: "text-destructive font-semibold",
};

export const Row = ({ label, value }: { label: string; value: string }) => (
  <div className="flex items-baseline justify-between gap-3">
    <span className="text-muted-foreground">{label}</span>
    <span className="truncate text-right font-medium" title={value}>{value}</span>
  </div>
);
