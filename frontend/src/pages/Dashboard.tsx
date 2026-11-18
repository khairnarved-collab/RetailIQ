import { useMemo, useState } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { BadgeDollarSign, CalendarRange, Package, RefreshCw, ShoppingCart, Sparkles, Store as StoreIcon, TrendingUp, Boxes } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ChartCard, ChartSkeleton, EmptyState, ErrorState, KpiCard, PageHeader, SimpleTable, SyntheticBanner } from "@/components/common";
import { MultiSelect } from "@/components/MultiSelect";
import { ChartLegend, ChartTooltip, axisProps, gridProps, seriesColor } from "@/charts/theme";
import { useApiQuery, useFilterOptions } from "@/hooks/useApi";
import { qs } from "@/services/api";
import type { Dashboard as DashboardData } from "@/services/types";
import { addDays, fmtCompact, fmtDate, fmtMoney, fmtMoneyCompact, fmtNum, fmtPct, fmtShortDate } from "@/utils/format";
import { cn } from "@/lib/utils";

const PRESETS: [string, number | null][] = [["30D", 30], ["90D", 90], ["6M", 182], ["1Y", 365], ["All", null]];

export default function Dashboard() {
  const { data: opts } = useFilterOptions();
  const [preset, setPreset] = useState<string>("90D");
  const [range, setRange] = useState<{ start?: string; end?: string }>({});
  const [stores, setStores] = useState<number[]>([]);
  const [cats, setCats] = useState<number[]>([]);
  const [prods, setProds] = useState<number[]>([]);

  // Effective date range: explicit dates win, otherwise the preset relative to the last date with data
  const max = opts?.date_max ?? undefined;
  const presetDays = PRESETS.find(([p]) => p === preset)?.[1];
  const end = range.end ?? max;
  const start = range.start ?? (max && presetDays ? addDays(max, -(presetDays - 1)) : opts?.date_min ?? undefined);

  const path = opts ? `/dashboard${qs({ start, end, stores, categories: cats, products: prods })}` : null;
  const { data, isLoading, isFetching, error, refetch } = useApiQuery<DashboardData>(["dashboard", path], path, { placeholderData: (p) => p });

  const productOptions = useMemo(() => (opts?.products ?? [])
    .filter((p) => cats.length === 0 || cats.includes(p.category_id))
    .map((p) => ({ value: p.id, label: p.name, hint: p.sku })), [opts, cats]);

  const reset = () => { setPreset("90D"); setRange({}); setStores([]); setCats([]); setProds([]); };
  const k = data?.kpis;
  const loading = isLoading || !data;

  if (opts && !opts.date_max) {
    return (
      <>
        <PageHeader title="Dashboard" />
        <EmptyState title="No sales data yet" description="Load the sample data (python -m scripts.seed) or upload a sales dataset in Data Management." />
      </>
    );
  }

  return (
    <div className="animate-fade-in">
      <PageHeader title="Business Dashboard"
        description={k ? <>Showing {fmtDate(k.period.start)} – {fmtDate(k.period.end)} · {k.period.days} days</> : "Loading…"}
        actions={<Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}><RefreshCw className={cn(isFetching && "animate-spin")} /> Refresh</Button>} />
      <SyntheticBanner show={!!opts?.synthetic_data} />

      {/* Filters: one row above all charts */}
      <Card className="mb-5">
        <CardContent className="grid gap-3 p-3 sm:p-4 md:grid-cols-2 xl:grid-cols-[auto_minmax(280px,1.3fr)_1fr_1fr_1fr_auto] xl:items-end">
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Period</Label>
            <Tabs value={range.start ? "" : preset} onValueChange={(v) => { setPreset(v); setRange({}); }}>
              <TabsList className="h-10 w-full justify-between sm:w-auto">
                {PRESETS.map(([p]) => <TabsTrigger key={p} value={p} className="px-2.5">{p}</TabsTrigger>)}
              </TabsList>
            </Tabs>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5"><Label htmlFor="d-start" className="text-xs text-muted-foreground">From</Label>
              <Input id="d-start" type="date" className="px-2" value={start ?? ""} min={opts?.date_min ?? undefined} max={end}
                onChange={(e) => e.target.value && setRange({ start: e.target.value, end })} /></div>
            <div className="space-y-1.5"><Label htmlFor="d-end" className="text-xs text-muted-foreground">To</Label>
              <Input id="d-end" type="date" className="px-2" value={end ?? ""} min={start} max={max}
                onChange={(e) => e.target.value && setRange({ start, end: e.target.value })} /></div>
          </div>
          <div className="space-y-1.5"><Label className="text-xs text-muted-foreground">Stores</Label>
            <MultiSelect placeholder="All stores" value={stores} onChange={setStores}
              options={(opts?.stores ?? []).map((s) => ({ value: s.id, label: `${s.code} · ${s.name}`, hint: s.state }))} /></div>
          <div className="space-y-1.5"><Label className="text-xs text-muted-foreground">Categories</Label>
            <MultiSelect placeholder="All categories" value={cats} onChange={(v) => { setCats(v); setProds([]); }}
              options={(opts?.categories ?? []).map((c) => ({ value: c.id, label: c.name }))} /></div>
          <div className="space-y-1.5"><Label className="text-xs text-muted-foreground">Products</Label>
            <MultiSelect placeholder="All products" value={prods} onChange={setProds} options={productOptions} /></div>
          <Button variant="ghost" onClick={reset} className="xl:mb-0">Reset</Button>
        </CardContent>
      </Card>

      {error && !data ? <ErrorState error={error} onRetry={() => refetch()} /> : (
        <div className={cn("space-y-5 transition-opacity", isFetching && !isLoading && "opacity-70")}>
          {/* KPI cards */}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <KpiCard label="Total Revenue" icon={<BadgeDollarSign />} loading={loading} value={fmtMoney(k?.total_revenue)} delta={k?.revenue_growth_pct ?? null} />
            <KpiCard label="Total Orders" icon={<ShoppingCart />} loading={loading} value={fmtNum(k?.total_orders)} hint={k?.definitions.total_orders} sub="sales transactions" />
            <KpiCard label="Units Sold" icon={<Package />} loading={loading} value={fmtNum(k?.units_sold)} />
            <KpiCard label="Average Order Value" icon={<TrendingUp />} loading={loading} value={fmtMoney(k?.avg_order_value, true)} hint={k?.definitions.avg_order_value} />
            <KpiCard label="Total Products" icon={<Boxes />} loading={loading} value={fmtNum(k?.total_products)} sub="with sales in period" />
            <KpiCard label="Number of Stores" icon={<StoreIcon />} loading={loading} value={fmtNum(k?.num_stores)} />
            <KpiCard label="Revenue Growth" icon={<CalendarRange />} loading={loading} value={fmtPct(k?.revenue_growth_pct)} hint={k?.definitions.revenue_growth_pct}
              sub={k?.previous_period ? `vs ${fmtMoneyCompact(k.previous_period.revenue)} in previous ${k.period.days} days` : undefined} />
            <KpiCard label="Forecasted Revenue (30d)" icon={<Sparkles />} loading={loading} value={fmtMoney(k?.forecasted_revenue_30d)} hint={k?.definitions.forecasted_revenue_30d}
              sub={k?.forecast_method ?? undefined} />
          </div>

          {loading ? (
            <div className="grid gap-5 lg:grid-cols-2">{Array.from({ length: 4 }).map((_, i) => <ChartSkeleton key={i} />)}</div>
          ) : data.kpis.total_orders === 0 ? (
            <EmptyState title="No sales match these filters" description="Widen the date range or clear some filters." action={<Button onClick={reset}>Reset filters</Button>} />
          ) : <Charts d={data} />}
        </div>
      )}
    </div>
  );
}

function Charts({ d }: { d: DashboardData }) {
  const money = (v: number) => fmtMoney(v);
  const catColor = (name: string) => seriesColor(["FOODS", "HOUSEHOLD", "HOBBIES"].indexOf(name) >= 0 ? ["FOODS", "HOUSEHOLD", "HOBBIES"].indexOf(name) : 3);
  return (
    <>
      <div className="grid gap-5 xl:grid-cols-3">
        <ChartCard className="xl:col-span-2" title="Revenue over time" description={`${d.revenue_over_time.granularity === "week" ? "Weekly" : "Daily"} revenue for the selected filters`}>
          <div className="h-[280px]">
            <ResponsiveContainer>
              <AreaChart data={d.revenue_over_time.points} margin={{ left: 0, right: 8, top: 8 }}>
                <defs>
                  <linearGradient id="rev-fill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--series-1)" stopOpacity={0.25} />
                    <stop offset="100%" stopColor="var(--series-1)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="date" {...axisProps} tickFormatter={fmtShortDate} minTickGap={28} />
                <YAxis {...axisProps} tickFormatter={fmtMoneyCompact} width={56} />
                <Tooltip content={<ChartTooltip valueFormatter={money} labelFormatter={(l) => fmtDate(l)} />} />
                <Area type="monotone" dataKey="revenue" name="Revenue" stroke="var(--series-1)" strokeWidth={2} fill="url(#rev-fill)" activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--chart-surface)" }} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>

        <ChartCard title="Revenue by category" description="Share of revenue in the period">
          <div className="h-[200px]">
            <ResponsiveContainer>
              <BarChart data={d.by_category} layout="vertical" margin={{ left: 8, right: 16 }}>
                <XAxis type="number" {...axisProps} tickFormatter={fmtMoneyCompact} />
                <YAxis type="category" dataKey="category" {...axisProps} width={84} />
                <Tooltip content={<ChartTooltip valueFormatter={money} />} />
                <Bar dataKey="revenue" name="Revenue" radius={[0, 4, 4, 0]} maxBarSize={28}>
                  {d.by_category.map((c) => <Cell key={c.category} fill={catColor(c.category)} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3 space-y-1.5">
            {d.by_category.map((c) => (
              <div key={c.category} className="flex items-center justify-between text-sm">
                <span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: catColor(c.category) }} />{c.category}</span>
                <span className="tabular text-muted-foreground">{fmtMoney(c.revenue)} · <b className="text-foreground">{c.share_pct.toFixed(1)}%</b></span>
              </div>
            ))}
          </div>
        </ChartCard>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <ChartCard title="Monthly sales comparison" description="Revenue per calendar month, by year">
          <div className="h-[260px]">
            <ResponsiveContainer>
              <BarChart data={d.monthly_comparison.points} margin={{ left: 0, right: 8, top: 8 }} barGap={2}>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="month" {...axisProps} />
                <YAxis {...axisProps} tickFormatter={fmtMoneyCompact} width={56} />
                <Tooltip content={<ChartTooltip valueFormatter={money} />} />
                {d.monthly_comparison.years.map((y, i) => <Bar key={y} dataKey={y} name={y} fill={seriesColor(i)} radius={[4, 4, 0, 0]} maxBarSize={22} />)}
              </BarChart>
            </ResponsiveContainer>
          </div>
          <ChartLegend items={d.monthly_comparison.years.map((y, i) => ({ name: y, color: seriesColor(i) }))} />
        </ChartCard>

        <ChartCard title="Product demand trends" description="Weekly units sold, top 5 products in the period">
          <div className="h-[260px]">
            <ResponsiveContainer>
              <LineChart data={d.demand_trends.points} margin={{ left: 0, right: 8, top: 8 }}>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="date" {...axisProps} tickFormatter={fmtShortDate} minTickGap={28} />
                <YAxis {...axisProps} tickFormatter={fmtCompact} width={44} />
                <Tooltip content={<ChartTooltip labelFormatter={(l) => `Week of ${fmtDate(l)}`} />} />
                {d.demand_trends.products.map((p, i) => <Line key={p} type="monotone" dataKey={p} name={p} stroke={seriesColor(i)} strokeWidth={2} dot={false} />)}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <ChartLegend items={d.demand_trends.products.map((p, i) => ({ name: p, color: seriesColor(i) }))} />
        </ChartCard>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <ChartCard title="Top 10 products" description="By revenue in the selected period">
          <ProductBars rows={d.top_products} color="var(--series-1)" />
        </ChartCard>
        <ChartCard title="Worst-performing products" description="Lowest revenue in the period, with change vs the previous period">
          <ProductBars rows={d.worst_products} color="var(--series-2)" showChange />
        </ChartCard>
      </div>

      <ChartCard title="Store-wise performance" description="Revenue by store; growth compares with the previous period of equal length">
        <div className="grid gap-5 lg:grid-cols-[1.2fr_1fr]">
          <div className="h-[280px]">
            <ResponsiveContainer>
              <BarChart data={d.stores} margin={{ left: 0, right: 8, top: 8 }}>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="code" {...axisProps} />
                <YAxis {...axisProps} tickFormatter={fmtMoneyCompact} width={56} />
                <Tooltip content={<ChartTooltip valueFormatter={money} labelFormatter={(l) => d.stores.find((s) => s.code === l)?.name ?? l} />} />
                <Bar dataKey="revenue" name="Revenue" fill="var(--series-1)" radius={[4, 4, 0, 0]} maxBarSize={36} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <SimpleTable maxHeight={280} columns={["Store", "Revenue", "Rev./day", "Growth"]} align={["left", "right", "right", "right"]}
            rows={d.stores.map((s) => [
              <span key="s"><b>{s.code}</b> <span className="text-muted-foreground">{s.name}</span></span>,
              fmtMoney(s.revenue), fmtMoney(s.revenue_per_day),
              <span key="g" className={s.growth_pct === null ? "text-muted-foreground" : s.growth_pct >= 0 ? "text-success" : "text-critical"}>{fmtPct(s.growth_pct)}</span>,
            ])} />
        </div>
      </ChartCard>

      <div className="grid gap-5 lg:grid-cols-3">
        <ChartCard title="Sales by weekday" description="Average revenue per day">
          <div className="h-[230px]">
            <ResponsiveContainer>
              <BarChart data={d.by_weekday} margin={{ left: 0, right: 8, top: 8 }}>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="weekday" {...axisProps} />
                <YAxis {...axisProps} tickFormatter={fmtMoneyCompact} width={52} />
                <Tooltip content={<ChartTooltip valueFormatter={money} />} />
                <Bar dataKey="avg_revenue" name="Avg revenue / day" fill="var(--series-1)" radius={[4, 4, 0, 0]} maxBarSize={32} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>
        <ChartCard title="Sales by month" description="Average revenue per day in each calendar month">
          <div className="h-[230px]">
            <ResponsiveContainer>
              <BarChart data={d.by_month} margin={{ left: 0, right: 8, top: 8 }}>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="month" {...axisProps} interval={0} tick={{ ...axisProps.tick, fontSize: 10 }} />
                <YAxis {...axisProps} tickFormatter={fmtMoneyCompact} width={52} />
                <Tooltip content={<ChartTooltip valueFormatter={money} />} />
                <Bar dataKey="avg_daily_revenue" name="Avg revenue / day" fill="var(--series-3)" radius={[4, 4, 0, 0]} maxBarSize={24} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>
        <ChartCard title="Revenue distribution" description={d.revenue_distribution.unit}
          footer={d.revenue_distribution.stats && <>Mean {fmtMoney(d.revenue_distribution.stats.mean)} · Median {fmtMoney(d.revenue_distribution.stats.median)} · n = {fmtNum(d.revenue_distribution.stats.n)}</>}>
          <div className="h-[200px]">
            <ResponsiveContainer>
              <BarChart data={d.revenue_distribution.bins} margin={{ left: 0, right: 8, top: 8 }} barCategoryGap={1}>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="from" {...axisProps} tickFormatter={fmtMoneyCompact} minTickGap={20} />
                <YAxis {...axisProps} width={40} tickFormatter={fmtCompact} />
                <Tooltip content={<ChartTooltip labelFormatter={(l) => { const b = d.revenue_distribution.bins.find((x) => String(x.from) === l); return b ? `${fmtMoney(b.from)} – ${fmtMoney(b.to)}` : l; }} />} />
                <Bar dataKey="count" name="Store-days" fill="var(--series-7)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>
      </div>
    </>
  );
}

function ProductBars({ rows, color, showChange }: { rows: DashboardData["top_products"]; color: string; showChange?: boolean }) {
  const data = rows.map((r) => ({ ...r, short: r.name.length > 22 ? r.name.slice(0, 21) + "…" : r.name }));
  return (
    <>
      <div style={{ height: Math.max(180, rows.length * 30) }}>
        <ResponsiveContainer>
          <BarChart data={data} layout="vertical" margin={{ left: 4, right: 16 }}>
            <XAxis type="number" {...axisProps} tickFormatter={fmtMoneyCompact} />
            <YAxis type="category" dataKey="short" {...axisProps} width={140} interval={0} />
            <Tooltip content={<ChartTooltip valueFormatter={(v) => fmtMoney(v)} />} />
            <Bar dataKey="revenue" name="Revenue" fill={color} radius={[0, 4, 4, 0]} maxBarSize={18} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      {showChange && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {rows.filter((r) => r.change_pct !== null).slice(0, 6).map((r) => (
            <span key={r.product_id} className={cn("rounded-full px-2 py-0.5 text-xs", (r.change_pct ?? 0) < 0 ? "bg-critical/10 text-critical" : "bg-success/10 text-success")}>
              {r.name.split(" ").slice(0, 2).join(" ")} {fmtPct(r.change_pct)}
            </span>
          ))}
        </div>
      )}
    </>
  );
}
