import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import { Download, Lightbulb, Microscope } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { ChartCard, ChartSkeleton, ErrorState, LoadingState, PageHeader, SimpleTable, SyntheticBanner } from "@/components/common";
import { BoxPlot, CorrelationHeatmap, type BoxStat } from "@/charts/BoxPlot";
import { ChartTooltip, axisProps, gridProps } from "@/charts/theme";
import { useApiQuery } from "@/hooks/useApi";
import { downloadFile, qs } from "@/services/api";
import { fmtCompact, fmtNum } from "@/utils/format";

interface Summary {
  meta: { source: string; label: string; total_rows: number; rows_used: number; sampled: boolean; is_synthetic?: boolean };
  columns: { name: string; numeric: boolean; dtype: string }[];
  describe: { numeric: Record<string, number | string | null>[]; categorical: Record<string, number | string | null>[] };
  correlation: { columns: string[]; matrix: (number | null)[][] };
  missing: { column: string; missing: number; missing_pct: number }[];
  outliers: { column: string; outliers: number; pct: number; lower_bound: number; upper_bound: number; extreme_3iqr: number }[];
  findings: { type: string; text: string }[];
}

function ColumnSelect({ value, onChange, options, label }: { value: string; onChange: (v: string) => void; options: string[]; label: string }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="w-full sm:w-48"><SelectValue placeholder="Choose column" /></SelectTrigger>
        <SelectContent>{options.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}</SelectContent>
      </Select>
    </div>
  );
}

export default function Eda() {
  const [params, setParams] = useSearchParams();
  const source = params.get("source") ?? "sales";
  const { data: sources = [] } = useApiQuery<{ id: string; label: string; is_synthetic?: boolean }[]>(["eda-sources"], "/eda/sources");
  const { data, isLoading, error, refetch } = useApiQuery<Summary>(["eda", source], `/eda/summary${qs({ source })}`);

  const numeric = useMemo(() => data?.columns.filter((c) => c.numeric).map((c) => c.name) ?? [], [data]);
  const categorical = useMemo(() => data?.columns.filter((c) => !c.numeric && !c.dtype.includes("datetime")).map((c) => c.name) ?? [], [data]);
  const [col, setCol] = useState("");
  const [by, setBy] = useState("none");
  const [x, setX] = useState("");
  const [y, setY] = useState("");
  useEffect(() => {
    if (numeric.length) { setCol(numeric.includes("revenue") ? "revenue" : numeric[0]); setX(numeric.includes("unit_price") ? "unit_price" : numeric[0]); setY(numeric.includes("units") ? "units" : numeric[1] ?? numeric[0]); }
    setBy(categorical.includes("category") ? "category" : "none");
  }, [numeric, categorical]);

  const hist = useApiQuery<{ bins: { from: number; to: number; label: string; count: number }[]; mean: number; median: number }>(
    ["eda-hist", source, col], col ? `/eda/histogram${qs({ source, column: col })}` : null);
  const box = useApiQuery<BoxStat[]>(["eda-box", source, col, by], col ? `/eda/box${qs({ source, columns: col, by: by === "none" ? null : by })}` : null);
  const scatter = useApiQuery<{ points: { x: number; y: number }[]; pearson_r: number | null; trend: { slope: number; intercept: number } | null }>(
    ["eda-scatter", source, x, y], x && y ? `/eda/scatter${qs({ source, x, y })}` : null);

  const png = (kind: string) => downloadFile(`/eda/plot.png${qs({ source, kind })}`, `eda_${kind}.png`).catch((e) => toast.error(e.message));

  return (
    <div className="animate-fade-in">
      <PageHeader title="Exploratory Data Analysis" icon={<Microscope className="h-6 w-6 text-primary" />}
        description="Statistics, distributions, relationships and data quality, generated automatically from the selected data."
        actions={
          <Select value={source} onValueChange={(v) => setParams({ source: v })}>
            <SelectTrigger className="w-full sm:w-80" aria-label="Data source"><SelectValue /></SelectTrigger>
            <SelectContent>{sources.map((s) => <SelectItem key={s.id} value={s.id}>{s.label}</SelectItem>)}</SelectContent>
          </Select>
        } />
      {isLoading ? <LoadingState rows={4} /> : error || !data ? <ErrorState error={error} onRetry={refetch} /> : (
        <div className="space-y-5">
          <SyntheticBanner show={source === "sales" ? true : !!data.meta.is_synthetic} text={source === "sales" ? undefined : "This dataset is labelled as SYNTHETIC demonstration data."} />
          <p className="text-sm text-muted-foreground">
            Analysing <b className="text-foreground">{fmtNum(data.meta.rows_used)}</b> rows of {data.meta.label}
            {data.meta.sampled && <> (a reproducible random sample of {fmtNum(data.meta.total_rows)} rows)</>}.
          </p>

          <Card className="border-primary/20 bg-primary/[.03]">
            <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2"><Lightbulb className="h-4 w-4 text-primary" /> Key findings</CardTitle></CardHeader>
            <CardContent>
              <ul className="space-y-2">
                {data.findings.map((f, i) => (
                  <li key={i} className="flex gap-2.5 text-sm"><Badge variant="secondary" className="mt-0.5 h-fit capitalize">{f.type}</Badge><span>{f.text}</span></li>
                ))}
              </ul>
              <p className="mt-3 text-xs text-muted-foreground">Every finding is calculated from the data shown. Correlations describe association only.</p>
            </CardContent>
          </Card>

          <Tabs defaultValue="visual">
            <TabsList>
              <TabsTrigger value="visual">Visualise</TabsTrigger>
              <TabsTrigger value="stats">Descriptive statistics</TabsTrigger>
              <TabsTrigger value="corr">Correlation</TabsTrigger>
              <TabsTrigger value="quality">Missing & outliers</TabsTrigger>
            </TabsList>

            <TabsContent value="visual" className="space-y-5">
              <div className="grid gap-5 lg:grid-cols-2">
                <ChartCard title="Distribution (histogram)" description={hist.data ? `Mean ${fmtNum(hist.data.mean)} · median ${fmtNum(hist.data.median)}` : undefined}
                  actions={<ColumnSelect label="Column" value={col} onChange={setCol} options={numeric} />}>
                  {hist.isLoading || !hist.data ? <ChartSkeleton height={260} /> : (
                    <div className="h-[260px]"><ResponsiveContainer>
                      <BarChart data={hist.data.bins} barCategoryGap={1} margin={{ left: 0, right: 8, top: 8 }}>
                        <CartesianGrid {...gridProps} />
                        <XAxis dataKey="label" {...axisProps} minTickGap={16} />
                        <YAxis {...axisProps} width={44} tickFormatter={fmtCompact} />
                        <Tooltip content={<ChartTooltip labelFormatter={(l) => { const b = hist.data!.bins.find((v) => v.label === l); return b ? `${fmtNum(b.from)} – ${fmtNum(b.to)}` : l; }} />} />
                        <Bar dataKey="count" name="Rows" fill="var(--series-1)" radius={[3, 3, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer></div>
                  )}
                </ChartCard>
                <ChartCard title="Box plot" description="Median, quartiles, 1.5×IQR whiskers and outliers"
                  actions={<div className="space-y-1.5"><Label className="text-xs text-muted-foreground">Group by</Label>
                    <Select value={by} onValueChange={setBy}><SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
                      <SelectContent><SelectItem value="none">No grouping</SelectItem>{categorical.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent></Select></div>}>
                  {box.isLoading || !box.data ? <ChartSkeleton height={220} /> : <BoxPlot data={box.data} />}
                </ChartCard>
              </div>
              <ChartCard title="Scatter plot" description={scatter.data?.pearson_r != null ? `Pearson r = ${scatter.data.pearson_r.toFixed(3)} (sample of up to 1,500 points)` : "Relationship between two numeric columns"}
                actions={<div className="flex flex-wrap gap-2"><ColumnSelect label="X axis" value={x} onChange={setX} options={numeric} /><ColumnSelect label="Y axis" value={y} onChange={setY} options={numeric} /></div>}>
                {scatter.isLoading || !scatter.data ? <ChartSkeleton height={300} /> : (
                  <div className="h-[320px]"><ResponsiveContainer>
                    <ScatterChart margin={{ left: 0, right: 12, top: 8 }}>
                      <CartesianGrid {...gridProps} vertical />
                      <XAxis type="number" dataKey="x" name={x} {...axisProps} tickFormatter={fmtCompact} domain={["auto", "auto"]} />
                      <YAxis type="number" dataKey="y" name={y} {...axisProps} tickFormatter={fmtCompact} width={44} domain={["auto", "auto"]} />
                      <ZAxis range={[28, 28]} />
                      <Tooltip cursor={{ strokeDasharray: "3 3" }} content={({ active, payload }) => active && payload?.length ? (
                        <div className="rounded-lg border bg-popover px-3 py-2 text-xs shadow-lg">{x}: <b>{fmtNum(payload[0].payload.x)}</b><br />{y}: <b>{fmtNum(payload[0].payload.y)}</b></div>) : null} />
                      <Scatter data={scatter.data.points} fill="var(--series-1)" fillOpacity={0.45} stroke="var(--chart-surface)" strokeWidth={1} />
                      {scatter.data.trend && (() => {
                        const xs = scatter.data.points.map((p) => p.x); const x0 = Math.min(...xs), x1 = Math.max(...xs);
                        const t = scatter.data.trend;
                        return <ReferenceLine segment={[{ x: x0, y: t.intercept + t.slope * x0 }, { x: x1, y: t.intercept + t.slope * x1 }]} stroke="var(--series-2)" strokeWidth={2} strokeDasharray="5 4" ifOverflow="extendDomain" />;
                      })()}
                    </ScatterChart>
                  </ResponsiveContainer></div>
                )}
              </ChartCard>
              <Card><CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-sm text-muted-foreground">Download publication-quality static charts rendered with Matplotlib + Seaborn.</p>
                <div className="flex flex-wrap gap-2">
                  {[["heatmap", "Correlation heatmap"], ["distribution", "Distributions"], ["boxplot", "Box plots"]].map(([k, l]) => (
                    <Button key={k} variant="outline" size="sm" onClick={() => png(k)}><Download /> {l}</Button>
                  ))}
                </div>
              </CardContent></Card>
            </TabsContent>

            <TabsContent value="stats" className="space-y-5">
              <ChartCard title="Numeric columns">
                <SimpleTable columns={["Column", "Count", "Mean", "Median", "Mode", "Std dev", "Min", "Q1", "Q3", "Max", "Skew"]}
                  align={["left", ...Array(10).fill("right")]}
                  rows={data.describe.numeric.map((r) => [<b key="c">{r.column}</b>, ...["count", "mean", "median", "mode", "std", "min", "q1", "q3", "max", "skewness"].map((k) => fmtNum(r[k] as number))])} />
              </ChartCard>
              {data.describe.categorical.length > 0 && (
                <ChartCard title="Text and date columns">
                  <SimpleTable columns={["Column", "Type", "Count", "Unique", "Most frequent (mode)", "Frequency / range"]}
                    rows={data.describe.categorical.map((r) => [<b key="c">{r.column}</b>, String(r.type), fmtNum(r.count as number), fmtNum(r.unique as number),
                      String(r.top ?? r.min ?? "–"), r.type === "date" ? `${r.min} → ${r.max}` : fmtNum(r.top_freq as number)])} />
                </ChartCard>
              )}
            </TabsContent>

            <TabsContent value="corr">
              <ChartCard title="Correlation matrix" description="Pearson correlation between numeric columns">
                {data.correlation.columns.length < 2 ? <p className="text-sm text-muted-foreground">Need at least two numeric columns.</p>
                  : <CorrelationHeatmap columns={data.correlation.columns} matrix={data.correlation.matrix} />}
              </ChartCard>
            </TabsContent>

            <TabsContent value="quality" className="grid gap-5 lg:grid-cols-2">
              <ChartCard title="Missing values by column">
                <div style={{ height: Math.max(200, data.missing.length * 26) }}><ResponsiveContainer>
                  <BarChart data={data.missing} layout="vertical" margin={{ left: 8, right: 16 }}>
                    <XAxis type="number" {...axisProps} unit="%" domain={[0, (max: number) => Math.max(5, Math.ceil(max))]} />
                    <YAxis type="category" dataKey="column" {...axisProps} width={110} interval={0} />
                    <Tooltip content={<ChartTooltip valueFormatter={(v) => `${v.toFixed(2)}%`} />} />
                    <Bar dataKey="missing_pct" name="Missing" fill="var(--series-2)" radius={[0, 4, 4, 0]} maxBarSize={16} />
                  </BarChart>
                </ResponsiveContainer></div>
              </ChartCard>
              <ChartCard title="Outlier analysis" description="IQR method: values beyond Q1 − 1.5×IQR or Q3 + 1.5×IQR">
                <SimpleTable columns={["Column", "Outliers", "%", "Fences", "Extreme (3×IQR)"]} align={["left", "right", "right", "right", "right"]}
                  rows={data.outliers.map((o) => [<b key="c">{o.column}</b>, fmtNum(o.outliers), `${o.pct}%`, `${fmtNum(o.lower_bound)} – ${fmtNum(o.upper_bound)}`, fmtNum(o.extreme_3iqr)])} />
              </ChartCard>
            </TabsContent>
          </Tabs>
        </div>
      )}
    </div>
  );
}
