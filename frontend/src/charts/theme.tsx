/**
 * Chart theme shared by every Recharts chart.
 *
 * Colours come from the validated categorical palette (CSS variables in index.css,
 * separate light and dark steps). Rules followed:
 *  - hues are assigned in a FIXED order and follow the entity, never its rank;
 *  - text (axes, legends, tooltips) uses ink colours, never series colours;
 *  - one y-axis per chart; thin lines (2px), rounded bar ends, recessive grid.
 */
import type { ReactNode } from "react";
import { fmtNum } from "@/utils/format";

export const SERIES = Array.from({ length: 8 }, (_, i) => `var(--series-${i + 1})`);
export const seriesColor = (i: number) => SERIES[i % SERIES.length];

export const axisProps = {
  stroke: "var(--chart-grid)",
  tickLine: false,
  axisLine: false,
  tick: { fill: "var(--chart-axis)", fontSize: 11 },
} as const;

export const gridProps = { stroke: "var(--chart-grid)", strokeDasharray: "0", vertical: false } as const;

interface TooltipPayload { name?: string; value?: number | string; color?: string; dataKey?: string | number; payload?: Record<string, unknown> }

/** Accessible tooltip: series swatch + name in ink colour + formatted value. */
export function ChartTooltip({ active, payload, label, valueFormatter = (v: number) => fmtNum(v), labelFormatter }: {
  active?: boolean; payload?: TooltipPayload[]; label?: string | number;
  valueFormatter?: (v: number, name?: string) => string; labelFormatter?: (l: string) => ReactNode;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="min-w-[10rem] rounded-lg border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-lg">
      {label !== undefined && <p className="mb-1.5 font-medium">{labelFormatter ? labelFormatter(String(label)) : label}</p>}
      <div className="space-y-1">
        {payload.filter((p) => p.value !== null && p.value !== undefined).map((p, i) => (
          <div key={i} className="flex items-center justify-between gap-4">
            <span className="flex items-center gap-1.5 text-muted-foreground">
              <span className="h-2.5 w-2.5 rounded-sm" style={{ background: p.color }} />{p.name}
            </span>
            <span className="tabular font-medium">
              {Array.isArray(p.value) ? p.value.map((v) => valueFormatter(Number(v), p.name)).join(" – ") : valueFormatter(Number(p.value), p.name)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Legend rendered as HTML (ink-coloured text + colour swatch). */
export function ChartLegend({ items }: { items: { name: string; color: string; dashed?: boolean }[] }) {
  return (
    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {items.map((it) => (
        <span key={it.name} className="inline-flex items-center gap-1.5">
          <span className="h-0.5 w-4 rounded" style={{ background: it.dashed ? `repeating-linear-gradient(90deg, ${it.color} 0 4px, transparent 4px 7px)` : it.color, height: 3 }} />
          {it.name}
        </span>
      ))}
    </div>
  );
}
