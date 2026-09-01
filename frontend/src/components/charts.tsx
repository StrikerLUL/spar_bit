/** Diagramme als reines Inline-SVG - keine Chart-Bibliothek.
 *
 *  Farben kommen aus den --viz-* Variablen (siehe index.css). Es sind die
 *  Slots 1-3 der validierten Kategorie-Palette; die Reihenfolge ist die
 *  Sicherung gegen Farbfehlsichtigkeit und wird nicht umsortiert.
 *  Im Hellmodus liegt Slot 3 unter 3:1 Kontrast - deshalb tragen alle Serien
 *  hier immer eine sichtbare Direktbeschriftung, nie nur Farbe.
 */
import * as React from "react";
import { cn } from "@/lib/utils";

export interface SeriesSpec {
  key: string;
  label: string;
  /** CSS-Variable, z. B. "var(--viz-1)" */
  color: string;
  /** Nachkommastellen im Tooltip */
  digits?: number;
  suffix?: string;
}

export interface TimePoint {
  tag: string;
  [key: string]: string | number;
}

const PAD = { top: 14, right: 16, bottom: 24, left: 40 };

/** Achsenteilung, die auf ganze Zahlen faellt.
 *
 *  Ein fester Bruchteil (0, 1/4, 1/2 ...) erzeugt bei kleinen Maxima krumme
 *  Werte: bei Max 5 kaeme 1,25 heraus, gerundet als "1" beschriftet - die
 *  Linie laege dann woanders als ihr Etikett behauptet. Darum eine Schrittweite
 *  aus 1/2/5/10 waehlen und die Ticks daraus aufbauen.
 */
function achse(rohMax: number): { max: number; ticks: number[] } {
  const ziel = Math.max(1, rohMax);
  const grob = ziel / 4;
  const groesse = 10 ** Math.floor(Math.log10(grob));
  // Mindestschritt 1: die Werte hier sind Stueckzahlen, "0,5 Deals" gibt es nicht.
  const schritt = Math.max(1, [1, 2, 5, 10].map((f) => f * groesse)
    .find((s) => s >= grob) ?? 10 * groesse);

  const max = Math.ceil(ziel / schritt) * schritt;
  const ticks: number[] = [];
  for (let v = 0; v <= max + 1e-9; v += schritt) {
    ticks.push(Math.round(v * 1000) / 1000);
  }
  return { max, ticks };
}

const formatDay = (iso: string) =>
  new Date(iso + "T00:00:00").toLocaleDateString("de-DE",
    { day: "2-digit", month: "2-digit" });

/** Liniendiagramm mit Fadenkreuz und Tooltip. */
export function TimeSeries({
  points,
  series,
  height = 220,
}: {
  points: TimePoint[];
  series: SeriesSpec[];
  height?: number;
}) {
  const [hover, setHover] = React.useState<number | null>(null);
  const [width, setWidth] = React.useState(680);
  const box = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!box.current) return;
    const observer = new ResizeObserver(([entry]) =>
      setWidth(Math.max(280, entry.contentRect.width)));
    observer.observe(box.current);
    return () => observer.disconnect();
  }, []);

  if (!points.length) {
    return <div className="py-10 text-center text-sm text-muted-foreground">
      Noch keine Daten.
    </div>;
  }

  const innerW = width - PAD.left - PAD.right;
  const innerH = height - PAD.top - PAD.bottom;
  const { max: maxValue, ticks } = achse(Math.max(
    1, ...points.flatMap((p) => series.map((s) => Number(p[s.key]) || 0))));

  const x = (i: number) =>
    PAD.left + (points.length === 1 ? innerW / 2 : (i / (points.length - 1)) * innerW);
  const y = (v: number) => PAD.top + innerH - (v / maxValue) * innerH;

  const labelEvery = Math.max(1, Math.ceil(points.length / 7));

  const move = (event: React.MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const rel = event.clientX - rect.left - PAD.left;
    const index = Math.round((rel / innerW) * (points.length - 1));
    setHover(Math.min(points.length - 1, Math.max(0, index)));
  };

  const active = hover === null ? null : points[hover];

  return (
    <div ref={box} className="relative w-full">
      <svg
        width="100%"
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        onMouseMove={move}
        onMouseLeave={() => setHover(null)}
        role="img"
        aria-label="Zeitverlauf"
        className="overflow-visible"
      >
        {/* Zurueckhaltendes Raster - es soll die Daten nicht überstimmen. */}
        {ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={PAD.left} x2={width - PAD.right}
              y1={y(tick)} y2={y(tick)}
              stroke="var(--viz-grid)" strokeWidth={1}
            />
            <text
              x={PAD.left - 8} y={y(tick) + 4} textAnchor="end"
              className="fill-muted-foreground text-[10px] tabular"
            >
              {tick}
            </text>
          </g>
        ))}

        {points.map((point, i) =>
          i % labelEvery === 0 || i === points.length - 1 ? (
            <text
              key={point.tag} x={x(i)} y={height - 6} textAnchor="middle"
              className="fill-muted-foreground text-[10px]"
            >
              {formatDay(point.tag)}
            </text>
          ) : null,
        )}

        {series.map((spec) => {
          const path = points
            .map((p, i) => `${i ? "L" : "M"}${x(i)},${y(Number(p[spec.key]) || 0)}`)
            .join(" ");
          return (
            <path
              key={spec.key} d={path} fill="none" stroke={spec.color}
              strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"
            />
          );
        })}

        {hover !== null && (
          <>
            <line
              x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={PAD.top + innerH}
              stroke="var(--viz-grid)" strokeWidth={1} strokeDasharray="3 3"
            />
            {series.map((spec) => (
              <circle
                key={spec.key} cx={x(hover)}
                cy={y(Number(points[hover][spec.key]) || 0)}
                r={4.5} fill={spec.color}
                /* 2px Ring in Flaechenfarbe, damit sich Punkte nicht verkleben */
                stroke="var(--viz-surface)" strokeWidth={2}
              />
            ))}
          </>
        )}
      </svg>

      {/* Legende: bei mehreren Serien Pflicht, mit Wert als Direktbeschriftung -
          so haengt die Identitaet nie allein an der Farbe. */}
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5">
        {series.map((spec) => {
          const value = active ? Number(active[spec.key]) || 0 : null;
          const summe = points.reduce((acc, p) => acc + (Number(p[spec.key]) || 0), 0);
          return (
            <span key={spec.key} className="flex items-center gap-1.5 text-xs">
              <span className="h-2 w-2 shrink-0 rounded-full"
                    style={{ background: spec.color }} aria-hidden />
              <span className="text-muted-foreground">{spec.label}</span>
              <span className="tabular font-medium">
                {(value ?? summe).toFixed(spec.digits ?? 0)}{spec.suffix ?? ""}
              </span>
            </span>
          );
        })}
        <span className="ml-auto text-xs text-muted-foreground">
          {active ? formatDay(active.tag) : `Summe über ${points.length} Tage`}
        </span>
      </div>
    </div>
  );
}

/** Waagerechte Balken fuer benannte Kategorien (Quellen, Haendler).
 *  Ein Merkmal, eine Farbe - die Balkenlaenge zeigt die Groesse, die Farbe
 *  muss sie nicht nochmal zeigen. */
export function BarList({
  items,
  suffix = "",
  emptyText = "Noch keine Daten.",
}: {
  items: Array<{ label: string; value: number; sub?: string }>;
  suffix?: string;
  emptyText?: string;
}) {
  if (!items.length) {
    return <p className="py-8 text-center text-sm text-muted-foreground">{emptyText}</p>;
  }
  const max = Math.max(...items.map((i) => i.value), 1);

  return (
    <ul className="space-y-2.5">
      {items.map((item) => (
        <li key={item.label} className="space-y-1">
          <div className="flex items-baseline justify-between gap-3 text-xs">
            <span className="truncate">{item.label}</span>
            <span className="shrink-0 text-muted-foreground">
              {item.sub && <span className="mr-2">{item.sub}</span>}
              <span className="tabular font-medium text-foreground">
                {item.value}{suffix}
              </span>
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: `${(item.value / max) * 100}%`,
                       background: "var(--viz-1)" }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Sparkline fuer den Preisverlauf eines Deals. Eine Serie, keine Achsen -
 *  die Zahlen stehen daneben im Text. */
export function Sparkline({
  values,
  height = 44,
  className,
}: {
  values: number[];
  height?: number;
  className?: string;
}) {
  if (values.length < 2) {
    return (
      <p className={cn("text-xs text-muted-foreground", className)}>
        Noch kein Verlauf — SparBit hat diesen Preis erst einmal gesehen.
      </p>
    );
  }
  const width = 240;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const x = (i: number) => (i / (values.length - 1)) * (width - 4) + 2;
  const y = (v: number) => height - 4 - ((v - min) / span) * (height - 10);

  const line = values.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join(" ");
  const area = `${line} L${x(values.length - 1)},${height} L${x(0)},${height} Z`;
  const gefallen = values[values.length - 1] <= values[0];

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className={cn("w-full", className)}
         preserveAspectRatio="none" role="img" aria-label="Preisverlauf">
      <path d={area} fill={gefallen ? "var(--viz-3)" : "var(--viz-2)"}
            opacity={0.12} />
      <path d={line} fill="none" strokeWidth={2} strokeLinecap="round"
            strokeLinejoin="round"
            stroke={gefallen ? "var(--viz-3)" : "var(--viz-2)"} />
      <circle cx={x(values.length - 1)} cy={y(values[values.length - 1])} r={3.5}
              fill={gefallen ? "var(--viz-3)" : "var(--viz-2)"}
              stroke="var(--viz-surface)" strokeWidth={2} />
    </svg>
  );
}
