/** UI-Primitive: eigene Komponenten, keine Fremdabhaengigkeit.
 *
 *  Flach gehalten. Karten haben eine Kante, keinen Schatten - ein Schatten
 *  behauptet, dass etwas ueber etwas anderem schwebt, und das stimmt bei
 *  einer Karte in einem Raster nicht. Schatten gibt es nur bei Dialog,
 *  Menue und Toast, wo es tatsaechlich so ist.
 */
import * as React from "react";
import { cn } from "@/lib/utils";

// --- Card ----------------------------------------------------------------

export const Card = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & { hover?: boolean }
>(({ className, hover, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "rounded-md border border-border bg-card text-card-foreground",
      "transition-colors duration-100",
      hover && "hover:border-muted-foreground/35",
      className,
    )}
    {...props}
  />
));
Card.displayName = "Card";

export const CardHeader = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("flex flex-col gap-1.5 p-5 sm:p-6", className)} {...props} />
);

export const CardTitle = ({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) => (
  <h3 className={cn("text-base font-semibold leading-tight tracking-tight", className)} {...props} />
);

export const CardDescription = ({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) => (
  <p className={cn("text-sm leading-relaxed text-muted-foreground", className)} {...props} />
);

export const CardContent = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("p-5 pt-0 sm:p-6 sm:pt-0", className)} {...props} />
);

export const CardFooter = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("flex items-center gap-2 p-5 pt-0 sm:p-6 sm:pt-0", className)} {...props} />
);

// --- Button --------------------------------------------------------------

type ButtonVariant = "default" | "secondary" | "outline" | "ghost" | "destructive"
  | "signal" | "link";
type ButtonSize = "sm" | "md" | "lg" | "icon";

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  default:
    "bg-primary text-primary-foreground hover:bg-primary/85 " +
    "focus-visible:ring-primary/50",
  secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
  outline: "border border-border bg-transparent hover:bg-accent hover:text-accent-foreground",
  ghost: "bg-transparent hover:bg-accent hover:text-accent-foreground",
  destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/85",
  signal: "bg-signal text-signal-foreground hover:bg-signal/85",
  link: "bg-transparent text-primary underline-offset-4 hover:underline",
};

const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: "h-8 gap-1.5 px-3 text-xs",
  md: "h-9.5 gap-2 px-4 text-sm",
  lg: "h-11 gap-2 px-6 text-sm",
  icon: "h-9 w-9",
};

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "md", loading, disabled, children, ...props }, ref) => (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex select-none items-center justify-center whitespace-nowrap rounded-md",
        "font-medium transition-colors duration-100",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60 focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        "disabled:pointer-events-none disabled:opacity-50",
        BUTTON_VARIANTS[variant],
        BUTTON_SIZES[size],
        size !== "icon" && "h-9",
        className,
      )}
      {...props}
    >
      {loading && <Spinner className="h-3.5 w-3.5" />}
      {children}
    </button>
  ),
);
Button.displayName = "Button";

export const Spinner = ({ className }: { className?: string }) => (
  <svg className={cn("animate-spin", className)} viewBox="0 0 24 24" fill="none" aria-hidden>
    <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3.5" />
    <path className="opacity-90" fill="currentColor"
      d="M12 2a10 10 0 0 1 10 10h-3.5A6.5 6.5 0 0 0 12 5.5z" />
  </svg>
);

// --- Badge ---------------------------------------------------------------

type BadgeVariant = "default" | "secondary" | "outline" | "success" | "warning"
  | "destructive" | "signal";

// Rahmen in der Akzentfarbe statt nur getoenter Flaeche: auf einem Bild
// hinter dem Abzeichen bleibt so die Form erkennbar.
const BADGE_VARIANTS: Record<BadgeVariant, string> = {
  default: "border-primary/35 bg-primary/12 text-primary",
  secondary: "border-transparent bg-secondary text-secondary-foreground",
  outline: "border-border text-muted-foreground",
  success: "border-success/40 bg-success/12 text-success",
  warning: "border-warning/40 bg-warning/12 text-warning",
  destructive: "border-destructive/40 bg-destructive/12 text-destructive",
  signal: "border-transparent bg-signal text-signal-foreground",
};

export const Badge = ({
  className,
  variant = "default",
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { variant?: BadgeVariant }) => (
  <span
    className={cn(
      "inline-flex items-center gap-1 rounded-sm border px-1.5 py-px",
      "text-[10.5px] font-semibold uppercase tracking-[0.04em] leading-[1.45]",
      BADGE_VARIANTS[variant],
      className,
    )}
    {...props}
  />
);

// --- Input / Textarea / Select ------------------------------------------

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1",
        "text-sm transition-colors",
        "placeholder:text-muted-foreground/70",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:border-ring/60",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      "flex min-h-20 w-full rounded-md border border-input bg-background px-3 py-2",
      "text-sm transition-colors placeholder:text-muted-foreground/70",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:border-ring/60",
      "disabled:cursor-not-allowed disabled:opacity-50",
      className,
    )}
    {...props}
  />
));
Textarea.displayName = "Textarea";

/** Nativer Select mit eigenem Pfeil.
 *  Der Pfeil ist ein echtes SVG-Element statt eines Data-URI-Hintergrunds -
 *  Data-URIs mit Leerzeichen ueberleben Tailwinds Klassen-Scanner nicht und
 *  fielen deshalb lautlos auf den hellen Browser-Standard zurueck.
 *  `[&>option]` faerbt die Optionsliste mit, sonst zeigt sie das
 *  Betriebssystem hell an. */
export const Select = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(({ className, children, ...props }, ref) => (
  <div className="relative w-full">
    <select
      ref={ref}
      className={cn(
        "flex h-9 w-full appearance-none rounded-md border border-input",
        "bg-secondary px-3 py-1 pr-9 text-sm text-foreground transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
        "disabled:cursor-not-allowed disabled:opacity-50",
        "[&>option]:bg-popover [&>option]:text-popover-foreground",
        className,
      )}
      {...props}
    >
      {children}
    </select>
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  </div>
));
Select.displayName = "Select";

export const Label = ({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) => (
  <label
    className={cn("text-sm font-medium leading-none text-foreground/90", className)}
    {...props}
  />
);

// --- Switch --------------------------------------------------------------

export const Switch = ({
  checked,
  onChange,
  disabled,
  label,
  className,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
  label?: string;
  className?: string;
}) => (
  <button
    type="button"
    role="switch"
    aria-checked={checked}
    aria-label={label}
    disabled={disabled}
    onClick={() => onChange(!checked)}
    className={cn(
      "relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full",
      "border-2 border-transparent transition-colors duration-200",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60 focus-visible:ring-offset-2 focus-visible:ring-offset-background",
      "disabled:cursor-not-allowed disabled:opacity-50",
      checked ? "bg-primary" : "bg-input",
      className,
    )}
  >
    <span
      className={cn(
        "pointer-events-none block h-4.5 w-4.5 rounded-full bg-white shadow-lg",
        "transition-transform duration-200 ease-out",
        checked ? "translate-x-5" : "translate-x-0.5",
      )}
      style={{ height: "1.125rem", width: "1.125rem" }}
    />
  </button>
);

// --- Slider --------------------------------------------------------------

export const Slider = ({
  value,
  min,
  max,
  step = 1,
  onChange,
  className,
}: {
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (value: number) => void;
  className?: string;
}) => {
  const percent = max > min ? ((value - min) / (max - min)) * 100 : 0;
  return (
    <input
      type="range"
      min={min}
      max={max}
      step={step}
      value={value}
      onChange={(event) => onChange(Number(event.target.value))}
      className={cn(
        "h-1.5 w-full cursor-pointer appearance-none rounded-full outline-none",
        "[&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4",
        "[&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full",
        "[&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:shadow-md",
        "[&::-webkit-slider-thumb]:transition-transform hover:[&::-webkit-slider-thumb]:scale-110",
        "[&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:border-0",
        "[&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-primary",
        className,
      )}
      style={{
        background:
          `linear-gradient(to right, hsl(var(--primary)) ${percent}%, hsl(var(--input)) ${percent}%)`,
      }}
    />
  );
};

// --- Dialog --------------------------------------------------------------

export const Dialog = ({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  wide?: boolean;
}) => {
  React.useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
      <div
        className="absolute inset-0 bg-black/65 animate-fade-in"
        onClick={onClose}
        aria-hidden
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cn(
          "relative z-10 flex max-h-[92vh] w-full flex-col overflow-hidden",
          "rounded-t-lg border border-border bg-card shadow-xl shadow-black/40",
          "animate-slide-up sm:rounded-md",
          wide ? "sm:max-w-4xl" : "sm:max-w-lg",
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-border p-5 sm:p-6">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
            {description && (
              <p className="mt-1 text-sm text-muted-foreground">{description}</p>
            )}
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Schließen"
            className="-mr-2 -mt-1 shrink-0">
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor"
              strokeWidth="2" strokeLinecap="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto p-5 sm:p-6">{children}</div>
        {footer && (
          <div className="flex flex-wrap justify-end gap-2 border-t border-border bg-background/40 p-4 sm:px-6">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
};

// --- Diverses ------------------------------------------------------------

export const Skeleton = ({ className }: { className?: string }) => (
  <div className={cn("animate-pulse rounded-md bg-muted/60", className)} />
);

export const EmptyState = ({
  icon,
  title,
  description,
  action,
}: {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) => (
  <div className="flex flex-col items-center justify-center gap-3 px-6 py-16 text-center">
    {icon && <div className="text-muted-foreground/50">{icon}</div>}
    <div className="space-y-1">
      <p className="font-medium">{title}</p>
      {description && (
        <p className="mx-auto max-w-md text-sm text-muted-foreground">{description}</p>
      )}
    </div>
    {action}
  </div>
);

/** Ampel-Punkt fuer Quellen-Health. */
export const StatusDot = ({
  status,
  pulse,
}: {
  status: "ok" | "warn" | "error" | "off";
  pulse?: boolean;
}) => {
  const colours = {
    ok: "bg-success",
    warn: "bg-warning",
    error: "bg-destructive",
    off: "bg-muted-foreground/40",
  };
  // Quadrat statt Kreis, und kein auslaufender Ring: ein Radarblip im
  // Augenwinkel zieht staendig Aufmerksamkeit auf eine Information, die
  // sich minutenlang nicht aendert. Das Pulsieren bleibt, aber dezent.
  return (
    <span
      className={cn("inline-block h-2 w-2 shrink-0 rounded-[1px]", colours[status],
                    pulse && status !== "off" && "animate-pulse-dot")}
    />
  );
};
