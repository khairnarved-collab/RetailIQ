import { useMemo, useState } from "react";
import { toast } from "sonner";
import {
  Area, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Award, Brain, Download, FileText, History, LineChart as LineIcon, Play, Target } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ChartCard, ChartSkeleton, EmptyState, KpiCard, PageHeader, SyntheticBanner } from "@/components/common";
import { ChartLegend, ChartTooltip, axisProps, gridProps, seriesColor } from "@/charts/theme";
import { useApiMutation, useApiQuery, useFilterOptions } from "@/hooks/useApi";
import { api, downloadFile, qs } from "@/services/api";
import type { ForecastResult } from "@/services/types";
import { fmtDate, fmtDateTime, fmtNum, fmtPct, fmtShortDate } from "@/utils/format";
import { cn } from "@/lib/utils";

const HORIZONS = [7, 14, 30, 60];
const MODEL_ORDER = ["seasonal_naive", "moving_average", "exp_smoothing", "random_forest", "xgboost"];
const modelColor = (name: string) => seriesColor(MODEL_ORDER.indexOf(name) + 1);

interface RunRow { id: number; product: { name: string; sku: string }; store: { code: string } | null; horizon: number; best_model_label: string; test: Record<string, number | null>; total_predicted_units: number; created_at: string }

export default function Forecasting() {
  const { data: opts } = useFilterOptions();
  const [product, setProduct] = useState<string>("");
  const [store, setStore] = useState<string>("all");
  const [horizon, setHorizon] = useState(30);
  const [result, setResult] = useState<ForecastResult | null>(null);
  const pid = product || (opts?.products[0] ? String(opts.products[0].id) : "");

  const history = useApiQuery<{ points: { date: string; units: number }[] }>(["fc-history", pid, store],
    pid ? `/forecasting/history${qs({ product_id: pid, store_id: store === "all" ? null : store, days: 180 })}` : null);
  const runs = useApiQuery<RunRow[]>(["fc-runs"], "/forecasting/runs");
  const run = useApiMutation(() => api.post<ForecastResult>("/forecasting/run", { product_id: Number(pid), store_id: store === "all" ? null : Number(store), horizon }),
    [["fc-runs"], ["inventory"]]);
  const loadRun = async (id: number) => {
    try { setResult(await api.get<ForecastResult>(`/forecasting/runs/${id}`)); window.scrollTo({ top: 0, behavior: "smooth" }); }
    catch (e) { toast.error((e as Error).message); }
  };

  const generate = () => run.mutate(undefined, {
    onSuccess: (r) => { setResult(r); toast.success(`Forecast ready: ${r.best_model_label} selected (${r.runtime_seconds}s)`); },
  });

  return (
    <div className="animate-fade-in">
      <PageHeader title="AI Demand Forecasting" icon={<LineIcon className="h-6 w-6 text-primary" />}
        description="Five models compared on time-based validation and test windows; the best one on validation forecasts the future." />
      <SyntheticBanner show={!!opts?.synthetic_data} />

      <Card className="mb-5">
        <CardContent className="grid gap-3 p-3 sm:p-4 md:grid-cols-2 xl:grid-cols-[1.4fr_1fr_auto_auto] xl:items-end">
          <div className="space-y-1.5"><Label className="text-xs text-muted-foreground">Product</Label>
            <Select value={pid} onValueChange={(v) => { setProduct(v); setResult(null); }}>
              <SelectTrigger><SelectValue placeholder="Choose a product" /></SelectTrigger>
              <SelectContent>{opts?.products.map((p) => <SelectItem key={p.id} value={String(p.id)}>{p.name} <span className="text-muted-foreground">· {p.sku}</span></SelectItem>)}</SelectContent>
            </Select></div>
          <div className="space-y-1.5"><Label className="text-xs text-muted-foreground">Store</Label>
            <Select value={store} onValueChange={(v) => { setStore(v); setResult(null); }}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="all">All stores (total demand)</SelectItem>
                {opts?.stores.map((s) => <SelectItem key={s.id} value={String(s.id)}>{s.code} · {s.name}</SelectItem>)}</SelectContent>
            </Select></div>
          <div className="space-y-1.5"><Label className="text-xs text-muted-foreground">Forecast period</Label>
            <Tabs value={String(horizon)} onValueChange={(v) => setHorizon(Number(v))}>
              <TabsList className="w-full">{HORIZONS.map((h) => <TabsTrigger key={h} value={String(h)} className="flex-1">{h} days</TabsTrigger>)}</TabsList>
            </Tabs></div>
          <Button onClick={generate} loading={run.isPending} disabled={!pid} size="lg" className="h-10"><Play /> Generate forecast</Button>
        </CardContent>
      </Card>

      {run.isPending && (
        <Card className="mb-5"><CardContent className="flex items-center gap-3 p-4 text-sm text-muted-foreground">
          <Brain className="h-5 w-5 animate-pulse text-primary" /> Training 5 models on time-based splits, scoring them, and computing SHAP explanations…
        </CardContent></Card>
      )}

      {result ? <ForecastView r={result} /> : (
        <div className="grid gap-5 lg:grid-cols-[1.6fr_1fr]">
          <ChartCard title="Recent demand" description="Daily units, last 180 days, for the selected product and store">
            {history.isLoading || !history.data ? <ChartSkeleton /> : (
              <div className="h-[280px]"><ResponsiveContainer>
                <LineChart data={history.data.points} margin={{ left: 0, right: 8, top: 8 }}>
                  <CartesianGrid {...gridProps} />
                  <XAxis dataKey="date" {...axisProps} tickFormatter={fmtShortDate} minTickGap={30} />
                  <YAxis {...axisProps} width={40} />
                  <Tooltip content={<ChartTooltip labelFormatter={(l) => fmtDate(l)} />} />
                  <Line dataKey="units" name="Units" stroke="var(--series-1)" strokeWidth={1.5} dot={false} />
                </LineChart>
              </ResponsiveContainer></div>
            )}
          </ChartCard>
          <RecentRuns runs={runs.data} onOpen={loadRun} />
        </div>
      )}
      {result && <div className="mt-5"><RecentRuns runs={runs.data} onOpen={loadRun} /></div>}
    </div>
  );
}

function RecentRuns({ runs, onOpen }: { runs?: RunRow[]; onOpen: (id: number) => void }) {
  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2"><History className="h-4 w-4" /> Recent forecasts</CardTitle></CardHeader>
      <CardContent>
        {!runs?.length ? <EmptyState title="No forecasts yet" description="Choose a product and generate your first forecast." /> : (
          <div className="max-h-[300px] space-y-1.5 overflow-y-auto scrollbar-thin">
            {runs.map((r) => (
              <button key={r.id} onClick={() => onOpen(r.id)} className="flex w-full items-center gap-3 rounded-lg border p-2.5 text-left text-sm hover:bg-muted/50">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{r.product.name} <span className="text-muted-foreground">· {r.store?.code ?? "All stores"} · {r.horizon}d</span></p>
                  <p className="text-xs text-muted-foreground">{r.best_model_label} · test WAPE {fmtNum(r.test?.wape ?? null)}% · {fmtDateTime(r.created_at)}</p>
                </div>
                <span className="tabular text-sm font-semibold">{fmtNum(r.total_predicted_units)}</span>
              </button>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ForecastView({ r }: { r: ForecastResult }) {
  const best = r.models.find((m) => m.is_selected)!;
  const [shown, setShown] = useState<string[]>([r.best_model, "seasonal_naive"]);
  const chart = useMemo(() => [
    ...r.history.map((h) => ({ date: h.date, actual: h.actual })),
    ...r.forecast.map((f, i) => ({ date: f.date, predicted: f.predicted, band: [f.lower, f.upper] as [number, number], ...(i === 0 ? {} : {}) })),
  ], [r]);
  const lastActual = r.history[r.history.length - 1]?.date;
  const download = () => downloadFile(`/forecasting/runs/${r.run_id}/download`).catch((e) => toast.error(e.message));
  const report = async () => {
    try {
      const rep = await api.post<{ id: number }>("/reports", { report_type: "forecast", format: "pdf", run_id: r.run_id });
      await downloadFile(`/reports/${rep.id}/download`);
    } catch (e) { toast.error((e as Error).message); }
  };
  const metric = (v: number | null | undefined, pct = false) => (v === null || v === undefined ? "–" : pct ? `${v.toFixed(1)}%` : v.toFixed(2));

  return (
    <div className="space-y-5 animate-fade-in">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted-foreground"><b className="text-foreground">{r.product.name}</b> · {r.store ? `${r.store.code} ${r.store.name}` : "All stores"} · next {r.horizon} days · run #{r.run_id}</p>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={download}><Download /> Download CSV</Button>
          <Button variant="outline" size="sm" onClick={report}><FileText /> PDF report</Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard label="Selected model" icon={<Award />} value={<span className="text-lg">{r.best_model_label}</span>} sub={`lowest validation WAPE (${metric(best.validation.wape, true)})`} />
        <KpiCard label={`Predicted units (${r.horizon}d)`} icon={<Target />} value={fmtNum(r.summary.total_predicted_units)} sub={`${fmtNum(r.summary.avg_daily_units)}/day · ${fmtPct(r.summary.change_vs_recent_pct)} vs last 28 days`} />
        <KpiCard label="Test MAE" value={`${metric(best.test.mae)} units/day`} hint="Mean absolute error on the final hold-out window, which was not used to choose the model." />
        <KpiCard label="Test WAPE / bias" value={metric(best.test.wape, true)} sub={`bias ${metric(best.test.bias, true)} (${(best.test.bias ?? 0) > 0 ? "over" : "under"}-forecasting)`}
          hint="WAPE = total absolute error ÷ total actual sales. Bias > 0 means the model over-forecasts." />
      </div>

      <ChartCard title="Actual vs. forecast" description={`Last ${r.history.length} days of actual sales, then the ${r.horizon}-day forecast with an ${Math.round(r.interval.coverage * 100)}% prediction interval`}
        footer={r.interval.method}>
        <div className="h-[320px]"><ResponsiveContainer>
          <ComposedChart data={chart} margin={{ left: 0, right: 8, top: 8 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="date" {...axisProps} tickFormatter={fmtShortDate} minTickGap={30} />
            <YAxis {...axisProps} width={40} />
            <Tooltip content={<ChartTooltip labelFormatter={(l) => fmtDate(l)} valueFormatter={(v) => fmtNum(v)} />} />
            <Area dataKey="band" name="80% interval" stroke="none" fill="var(--series-2)" fillOpacity={0.18} />
            <Line dataKey="actual" name="Actual" stroke="var(--series-1)" strokeWidth={1.5} dot={false} />
            <Line dataKey="predicted" name="Forecast" stroke="var(--series-2)" strokeWidth={2} dot={false} strokeDasharray="5 3" />
            {lastActual && <ReferenceLine x={lastActual} stroke="var(--chart-axis)" strokeDasharray="3 3" label={{ value: "today", fill: "var(--chart-axis)", fontSize: 10, position: "insideTopRight" }} />}
          </ComposedChart>
        </ResponsiveContainer></div>
        <ChartLegend items={[{ name: "Actual", color: "var(--series-1)" }, { name: "Forecast", color: "var(--series-2)", dashed: true }, { name: "80% prediction interval", color: "color-mix(in srgb, var(--series-2) 35%, transparent)" }]} />
      </ChartCard>

      <div className="grid gap-5 2xl:grid-cols-[1.4fr_1fr]">
        <ChartCard title="Model comparison" description={`Validation ${r.splits.validation[0]} → ${r.splits.validation[1]} (model selection) · Test ${r.splits.test[0]} → ${r.splits.test[1]} (honest accuracy)`}
          footer={<>Selection rule: {r.selection_metric}. Training data: {r.splits.train[0]} → {r.splits.train[1]}. {best.mape_note}</>}>
          <div className="rounded-lg border">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Model</TableHead><TableHead className="text-right">Val. WAPE</TableHead><TableHead className="text-right">Test MAE</TableHead>
                <TableHead className="text-right">Test RMSE</TableHead><TableHead className="text-right">Test MAPE</TableHead><TableHead className="text-right">Test WAPE</TableHead><TableHead className="text-right">Bias</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {[...r.models].sort((a, b) => (a.validation.wape ?? 1e9) - (b.validation.wape ?? 1e9)).map((m) => (
                  <TableRow key={m.name} className={cn(m.is_selected && "bg-primary/5")}>
                    <TableCell className="whitespace-nowrap font-medium"><span className="mr-2 inline-block h-2.5 w-2.5 rounded-sm" style={{ background: modelColor(m.name) }} />{m.label}{m.is_selected && <Badge className="ml-2">selected</Badge>}</TableCell>
                    <TableCell className="tabular text-right">{metric(m.validation.wape, true)}</TableCell>
                    <TableCell className="tabular text-right">{metric(m.test.mae)}</TableCell>
                    <TableCell className="tabular text-right">{metric(m.test.rmse)}</TableCell>
                    <TableCell className="tabular text-right">{m.test.mape === null ? <span className="text-muted-foreground" title={m.mape_note ?? ""}>n/a</span> : metric(m.test.mape, true)}</TableCell>
                    <TableCell className="tabular text-right">{metric(m.test.wape, true)}</TableCell>
                    <TableCell className="tabular text-right">{metric(m.test.bias, true)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </ChartCard>

        <ChartCard title="Back-test on the test window" description="Each model's forecast for days it never saw"
          actions={<div className="flex flex-wrap justify-end gap-1">{MODEL_ORDER.filter((m) => r.models.some((x) => x.name === m)).map((m) => (
            <button key={m} onClick={() => setShown(shown.includes(m) ? shown.filter((x) => x !== m) : [...shown, m])}
              className={cn("rounded-full border px-2 py-0.5 text-[11px]", shown.includes(m) ? "border-transparent bg-muted font-medium" : "text-muted-foreground")}>
              <span className="mr-1 inline-block h-2 w-2 rounded-full" style={{ background: modelColor(m) }} />{r.models.find((x) => x.name === m)?.label.split(" (")[0]}
            </button>))}</div>}>
          <div className="h-[260px]"><ResponsiveContainer>
            <LineChart data={r.backtest} margin={{ left: 0, right: 8, top: 8 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="date" {...axisProps} tickFormatter={fmtShortDate} minTickGap={24} />
              <YAxis {...axisProps} width={40} />
              <Tooltip content={<ChartTooltip labelFormatter={(l) => fmtDate(l)} />} />
              <Line dataKey="actual" name="Actual" stroke="var(--series-1)" strokeWidth={2} dot={{ r: 2 }} />
              {shown.map((m) => <Line key={m} dataKey={m} name={r.models.find((x) => x.name === m)?.label} stroke={modelColor(m)} strokeWidth={1.5} dot={false} strokeDasharray="4 3" />)}
            </LineChart>
          </ResponsiveContainer></div>
        </ChartCard>
      </div>

      {r.shap ? (
        <div className="grid gap-5 lg:grid-cols-2">
          <ChartCard title="What drives the forecast (SHAP)" description={`Mean |SHAP| importance · ${r.shap.model_label}`} footer={r.shap.note ?? r.shap.summary}>
            <div style={{ height: r.shap.importance.length * 26 + 20 }}><ResponsiveContainer>
              <BarChart data={r.shap.importance} layout="vertical" margin={{ left: 8, right: 24 }}>
                <XAxis type="number" {...axisProps} unit="%" />
                <YAxis type="category" dataKey="label" {...axisProps} width={170} interval={0} />
                <Tooltip content={<ChartTooltip valueFormatter={(v) => `${v.toFixed(1)}% of total impact`} />} />
                <Bar dataKey="share_pct" name="Share of impact" fill="var(--series-7)" radius={[0, 4, 4, 0]} maxBarSize={16} />
              </BarChart>
            </ResponsiveContainer></div>
          </ChartCard>
          <ChartCard title={`Drivers of the first forecast day (${fmtDate(r.shap.first_forecast_day.date)})`}
            description={`Positive values push demand up, negative values pull it down (${r.shap.first_forecast_day.scale})`}
            footer="SHAP explains the model's behaviour. It shows association learned from data, not proof of cause and effect.">
            <div style={{ height: r.shap.first_forecast_day.contributions.length * 30 + 20 }}><ResponsiveContainer>
              <BarChart data={r.shap.first_forecast_day.contributions.map((c) => ({ ...c, name: `${c.label} = ${fmtNum(c.value)}` }))} layout="vertical" margin={{ left: 8, right: 24 }}>
                <CartesianGrid {...gridProps} horizontal={false} vertical />
                <XAxis type="number" {...axisProps} />
                <YAxis type="category" dataKey="name" {...axisProps} width={200} interval={0} />
                <ReferenceLine x={0} stroke="var(--chart-axis)" />
                <Tooltip content={<ChartTooltip valueFormatter={(v) => (v > 0 ? "+" : "") + v.toFixed(3)} />} />
                <Bar dataKey="contribution" name="Contribution" radius={4} maxBarSize={16}>
                  {r.shap.first_forecast_day.contributions.map((c) => <Cell key={c.feature} fill={c.contribution >= 0 ? "var(--series-1)" : "var(--series-8)"} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer></div>
          </ChartCard>
        </div>
      ) : null}

      <Card><CardHeader className="pb-2"><CardTitle>Methodology & assumptions</CardTitle>
        <CardDescription>How this forecast was produced. The accuracy figures come from real hold-out data.</CardDescription></CardHeader>
        <CardContent><ul className="space-y-1.5 text-sm text-muted-foreground">
          <li>• Time-based splits (never random): train → validation ({r.eval_window_days} days) → test ({r.eval_window_days} days). Lag and rolling features only use past values, which prevents data leakage.</li>
          <li>• Features: lags (1, 7, 14, 28 days), 7/28-day rolling mean and volatility, day of week, month, holidays and events, SNAP days, price and promotions.</li>
          {r.assumptions.map((a) => <li key={a}>• {a}</li>)}
          <li>• Runtime: {r.runtime_seconds}s.</li>
        </ul></CardContent></Card>
    </div>
  );
}
