/**
 * Horizontal box plot drawn in SVG (Recharts has no box plot).
 * Box = Q1..Q3, line = median, whiskers = 1.5×IQR fences, label shows the outlier count.
 */
import { useState } from "react";
import { fmtNum } from "@/utils/format";

export interface BoxStat { column: string; group: string | null; lower_whisker: number; q1: number; median: number; q3: number; upper_whisker: number; min: number; max: number; outliers: number }

export function BoxPlot({ data }: { data: BoxStat[] }) {
  const [hover, setHover] = useState<number | null>(null);
  if (!data.length) return null;
  // Scale to the whiskers (plus margin) so a few extreme outliers don't squash the boxes;
  // outliers beyond the axis are shown as a marker at the edge.
  const lo = Math.min(...data.map((d) => d.lower_whisker));
  const hi = Math.max(...data.map((d) => d.upper_whisker)) * 1.15 || 1;
  const W = 560, rowH = 42, left = 104, right = 20, top = 8;
  const H = top + data.length * rowH + 26;
  const x = (v: number) => left + ((Math.min(v, hi) - lo) / (hi - lo || 1)) * (W - left - right);
  const ticks = Array.from({ length: 5 }, (_, i) => lo + ((hi - lo) * i) / 4);
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Box plot">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={top} y2={H - 22} stroke="var(--chart-grid)" />
            <text x={x(t)} y={H - 8} textAnchor="middle" fontSize="12" fill="var(--chart-axis)">{fmtNum(t)}</text>
          </g>
        ))}
        {data.map((d, i) => {
          const y = top + i * rowH + rowH / 2;
          return (
            <g key={i} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} className="cursor-default">
              <rect x={0} y={y - rowH / 2} width={W} height={rowH} fill={hover === i ? "var(--chart-grid)" : "transparent"} opacity={0.5} />
              <text x={left - 8} y={y + 4} textAnchor="end" fontSize="13" fill="currentColor" className="fill-foreground">{(d.group ?? d.column).slice(0, 16)}</text>
              <line x1={x(d.lower_whisker)} x2={x(d.upper_whisker)} y1={y} y2={y} stroke="var(--chart-axis)" strokeWidth={1.5} />
              <line x1={x(d.lower_whisker)} x2={x(d.lower_whisker)} y1={y - 6} y2={y + 6} stroke="var(--chart-axis)" strokeWidth={1.5} />
              <line x1={x(d.upper_whisker)} x2={x(d.upper_whisker)} y1={y - 6} y2={y + 6} stroke="var(--chart-axis)" strokeWidth={1.5} />
              <rect x={x(d.q1)} y={y - 10} width={Math.max(x(d.q3) - x(d.q1), 2)} height={20} rx={4} fill="var(--series-1)" fillOpacity={0.25} stroke="var(--series-1)" strokeWidth={1.5} />
              <line x1={x(d.median)} x2={x(d.median)} y1={y - 10} y2={y + 10} stroke="var(--series-1)" strokeWidth={2.5} />
              {d.outliers > 0 && <>
                <circle cx={x(d.max)} cy={y} r={4} fill="var(--series-2)" />
                <text x={x(d.max) - 8} y={y - 12} textAnchor="end" fontSize="11" fill="var(--chart-axis)">{d.outliers} outliers{d.max > hi ? ` (max ${fmtNum(d.max)})` : ""}</text>
              </>}
            </g>
          );
        })}
      </svg>
      {hover !== null && (
        <div className="pointer-events-none absolute right-2 top-2 rounded-lg border bg-popover px-3 py-2 text-xs shadow-lg">
          <p className="mb-1 font-medium">{data[hover].group ?? data[hover].column}</p>
          <p>Q1 {fmtNum(data[hover].q1)} · Median {fmtNum(data[hover].median)} · Q3 {fmtNum(data[hover].q3)}</p>
          <p>Whiskers {fmtNum(data[hover].lower_whisker)} – {fmtNum(data[hover].upper_whisker)} · {data[hover].outliers} outliers</p>
        </div>
      )}
    </div>
  );
}

/** Correlation heatmap: diverging blue (positive) / red (negative) with a neutral grey midpoint. */
export function CorrelationHeatmap({ columns, matrix }: { columns: string[]; matrix: (number | null)[][] }) {
  const color = (v: number | null) => {
    if (v === null) return "transparent";
    const a = Math.min(Math.abs(v), 1);
    // mix from neutral grey toward the pole colour
    const pole = v >= 0 ? [42, 120, 214] : [227, 73, 72];
    const mid = [160, 166, 176];
    const c = mid.map((m, i) => Math.round(m + (pole[i] - m) * a));
    return `rgba(${c[0]},${c[1]},${c[2]},${0.15 + 0.85 * a})`;
  };
  return (
    <div className="overflow-x-auto scrollbar-thin">
      <table className="border-separate border-spacing-0.5 text-xs">
        <thead>
          <tr><th />{columns.map((c) => <th key={c} className="h-24 w-12 align-bottom font-medium text-muted-foreground"><div className="w-12 origin-bottom-left -rotate-45 translate-x-5 whitespace-nowrap text-left">{c}</div></th>)}</tr>
        </thead>
        <tbody>
          {matrix.map((row, i) => (
            <tr key={columns[i]}>
              <th className="whitespace-nowrap pr-2 text-right font-medium text-muted-foreground">{columns[i]}</th>
              {row.map((v, j) => (
                <td key={j} title={`${columns[i]} × ${columns[j]}: r = ${v?.toFixed(2)}`} className="h-11 w-12 rounded text-center tabular"
                  style={{ background: color(v), color: v !== null && Math.abs(v) > 0.55 ? "white" : undefined }}>
                  {v === null ? "–" : v.toFixed(2)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
        <span>−1</span><span className="h-2 w-40 rounded" style={{ background: "linear-gradient(90deg, rgb(227,73,72), rgb(160,166,176), rgb(42,120,214))" }} /><span>+1</span>
        <span className="ml-2">Pearson correlation (association, not causation)</span>
      </div>
    </div>
  );
}
