import { useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import { Crown, Repeat, ShoppingBag, UserCheck, Users, UsersRound, Wallet } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ChartCard, EmptyState, ErrorState, KpiCard, LoadingState, PageHeader, SimpleTable, SyntheticBanner } from "@/components/common";
import { ChartLegend, ChartTooltip, axisProps, gridProps, seriesColor } from "@/charts/theme";
import { useApiQuery } from "@/hooks/useApi";
import { qs } from "@/services/api";
import { fmtMoney, fmtNum } from "@/utils/format";

interface Seg { segment: string; customers: number; share_pct: number; revenue: number; revenue_share_pct: number; avg_recency_days: number; avg_frequency: number; avg_monetary: number; avg_clv: number; description: string; recommendations: string[] }
interface CustomerAnalysis {
  available: boolean; message?: string; dataset: { id: number; name: string; is_synthetic: boolean }; datasets: { id: number; name: string; is_synthetic: boolean; transactions: number }[];
  snapshot_date: string;
  kpis: { customers: number; orders: number; revenue: number; avg_spend_per_customer: number; avg_order_value: number; avg_orders_per_customer: number; repeat_purchase_rate_pct: number; retention_90d_pct: number | null; avg_clv: number };
  segments: Seg[];
  clusters: { k: number; method: string; silhouette_by_k: { k: number; silhouette: number }[]; profiles: { cluster: number; label: string; customers: number; avg_recency_days: number; avg_frequency: number; avg_monetary: number; avg_clv: number }[]; points: { recency: number; frequency: number; monetary: number; cluster: number; segment: string }[] };
  cohorts: { cohort: string; size: number; values: (number | null)[] }[];
  frequency_distribution: { orders: string; customers: number }[];
  top_customers: { customer: string; segment: string; orders: number; spend: number; recency_days: number; clv: number }[];
  assumptions: { clv_formula: string; clv_lifespan_years: number; gross_margin: number; note: string };
}

// Fixed colour per segment (identity follows the segment, not its rank)
const SEGMENTS = ["Champions", "Loyal Customers", "Potential Loyalists", "New Customers", "Need Attention", "At Risk", "Lost Customers"];
const segColor = (s: string) => seriesColor(Math.max(0, SEGMENTS.indexOf(s)));
const SHAPES = ["circle", "triangle", "square", "diamond", "star", "cross"] as const;

function retentionColor(v: number | null) {
  if (v === null) return "transparent";
  return `rgba(42,120,214,${0.08 + (Math.min(v, 100) / 100) * 0.85})`;
}

export default function Customers() {
  const [ds, setDs] = useState<number | null>(null);
  const { data, isLoading, error, refetch } = useApiQuery<CustomerAnalysis>(["customers", ds], `/customers/analysis${qs({ dataset_id: ds })}`);

  if (isLoading) return <LoadingState rows={5} />;
  if (error || !data) return <ErrorState error={error} onRetry={refetch} />;
  if (!data.available) {
    return (
      <>
        <PageHeader title="Customer Intelligence" />
        <EmptyState icon={<UsersRound />} title="No customer-level data available" description={data.message}
          action={<Button asChild><Link to="/app/data">Upload customer transactions</Link></Button>} />
      </>
    );
  }
  const k = data.kpis;
  return (
    <div className="animate-fade-in">
      <PageHeader title="Customer Intelligence" description={<>RFM analysis and K-Means segmentation · snapshot {data.snapshot_date}</>}
        actions={data.datasets.length > 1 && (
          <Select value={String(data.dataset.id)} onValueChange={(v) => setDs(Number(v))}>
            <SelectTrigger className="w-72"><SelectValue /></SelectTrigger>
            <SelectContent>{data.datasets.map((d) => <SelectItem key={d.id} value={String(d.id)}>{d.name}</SelectItem>)}</SelectContent>
          </Select>
        )} />
      <SyntheticBanner show={data.dataset.is_synthetic} text="These customers are SYNTHETIC demonstration data, generated independently of the M5 sales data (M5 contains no customer information). Upload a real customer-transaction file to analyse real customers." />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        <KpiCard label="Customers" icon={<Users />} value={fmtNum(k.customers)} sub={`${fmtNum(k.orders)} orders`} />
        <KpiCard label="Avg. spend / customer" icon={<Wallet />} value={fmtMoney(k.avg_spend_per_customer)} />
        <KpiCard label="Purchase frequency" icon={<ShoppingBag />} value={`${k.avg_orders_per_customer}`} sub="orders per customer" />
        <KpiCard label="Repeat purchase rate" icon={<Repeat />} value={`${k.repeat_purchase_rate_pct}%`} hint="Share of customers with more than one order" />
        <KpiCard label="90-day retention" icon={<UserCheck />} value={k.retention_90d_pct === null ? "n/a" : `${k.retention_90d_pct}%`} hint="Customers active 91–180 days ago who bought again in the last 90 days" />
        <KpiCard label="Avg. CLV estimate" icon={<Crown />} value={fmtMoney(k.avg_clv)} hint={`${data.assumptions.clv_formula}. Lifespan ${data.assumptions.clv_lifespan_years} yrs, margin ${data.assumptions.gross_margin * 100}%.`} />
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <ChartCard title="Customer segment distribution" description="RFM segments: share of customers vs share of revenue">
          <div className="h-[280px]"><ResponsiveContainer>
            <BarChart data={data.segments} layout="vertical" margin={{ left: 8, right: 16 }} barGap={2}>
              <CartesianGrid {...gridProps} horizontal={false} vertical />
              <XAxis type="number" {...axisProps} unit="%" />
              <YAxis type="category" dataKey="segment" {...axisProps} width={124} interval={0} />
              <Tooltip content={<ChartTooltip valueFormatter={(v) => `${v.toFixed(1)}%`} />} />
              <Bar dataKey="share_pct" name="% of customers" fill="var(--series-1)" radius={[0, 4, 4, 0]} maxBarSize={12} />
              <Bar dataKey="revenue_share_pct" name="% of revenue" fill="var(--series-2)" radius={[0, 4, 4, 0]} maxBarSize={12} />
            </BarChart>
          </ResponsiveContainer></div>
          <ChartLegend items={[{ name: "% of customers", color: "var(--series-1)" }, { name: "% of revenue", color: "var(--series-2)" }]} />
        </ChartCard>

        <ChartCard title={`K-Means clusters (k = ${data.clusters.k})`} description="Recency vs. total spend for a sample of customers; shape and colour = cluster">
          <div className="h-[280px]"><ResponsiveContainer>
            <ScatterChart margin={{ left: 0, right: 12, top: 8 }}>
              <CartesianGrid {...gridProps} vertical />
              <XAxis type="number" dataKey="recency" name="Recency (days)" {...axisProps} />
              <YAxis type="number" dataKey="monetary" name="Spend" {...axisProps} tickFormatter={(v) => fmtMoney(v)} width={60} scale="log" domain={["auto", "auto"]} />
              <ZAxis range={[30, 30]} />
              <Tooltip content={({ active, payload }) => active && payload?.length ? (
                <div className="rounded-lg border bg-popover px-3 py-2 text-xs shadow-lg">
                  <p className="font-medium">{data.clusters.profiles.find((p) => p.cluster === payload[0].payload.cluster)?.label}</p>
                  <p>Recency {payload[0].payload.recency} days · {payload[0].payload.frequency} orders · {fmtMoney(payload[0].payload.monetary)}</p>
                  <p className="text-muted-foreground">RFM segment: {payload[0].payload.segment}</p>
                </div>) : null} />
              {data.clusters.profiles.map((p, i) => (
                <Scatter key={p.cluster} name={p.label} data={data.clusters.points.filter((pt) => pt.cluster === p.cluster)}
                  fill={seriesColor(i)} fillOpacity={0.65} shape={SHAPES[i % SHAPES.length]} />
              ))}
            </ScatterChart>
          </ResponsiveContainer></div>
          <ChartLegend items={data.clusters.profiles.map((p, i) => ({ name: `${SHAPES[i % SHAPES.length]} · ${p.label}`, color: seriesColor(i) }))} />
        </ChartCard>
      </div>

      <h2 className="mb-3 mt-7 text-lg font-semibold">Segments and recommended actions</h2>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {data.segments.map((s) => (
          <Card key={s.segment} className="flex flex-col">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between gap-2">
                <CardTitle className="flex items-center gap-2"><span className="h-3 w-3 rounded-sm" style={{ background: segColor(s.segment) }} />{s.segment}</CardTitle>
                <span className="tabular text-sm text-muted-foreground">{fmtNum(s.customers)} · {s.share_pct}%</span>
              </div>
              <CardDescription>{s.description}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-1 flex-col gap-3">
              <div className="grid grid-cols-3 gap-2 rounded-lg bg-muted/50 p-2.5 text-center text-xs">
                <div><p className="text-muted-foreground">Recency</p><p className="tabular font-semibold">{s.avg_recency_days.toFixed(0)}d</p></div>
                <div><p className="text-muted-foreground">Orders</p><p className="tabular font-semibold">{s.avg_frequency.toFixed(1)}</p></div>
                <div><p className="text-muted-foreground">Avg CLV</p><p className="tabular font-semibold">{fmtMoney(s.avg_clv)}</p></div>
              </div>
              <p className="text-xs text-muted-foreground">{s.revenue_share_pct}% of revenue ({fmtMoney(s.revenue)})</p>
              <ul className="space-y-1.5 text-sm">{s.recommendations.map((r) => <li key={r} className="flex gap-2"><span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-primary" />{r}</li>)}</ul>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <ChartCard title="Monthly cohort retention" description="% of each first-purchase cohort that bought again N months later">
          <div className="overflow-x-auto scrollbar-thin">
            <table className="w-full border-separate border-spacing-0.5 text-[11px]">
              <thead><tr><th className="px-1 text-left font-medium text-muted-foreground">Cohort</th><th className="px-1 font-medium text-muted-foreground">Size</th>
                {Array.from({ length: 12 }).map((_, i) => <th key={i} className="w-9 font-medium text-muted-foreground">M{i}</th>)}</tr></thead>
              <tbody>{data.cohorts.map((c) => (
                <tr key={c.cohort}>
                  <td className="whitespace-nowrap px-1 font-medium">{c.cohort}</td><td className="tabular px-1 text-center text-muted-foreground">{c.size}</td>
                  {Array.from({ length: 12 }).map((_, i) => {
                    const v = c.values[i] ?? null;
                    return <td key={i} className="tabular h-7 rounded text-center" style={{ background: retentionColor(v), color: v !== null && v > 55 ? "white" : undefined }}>{v === null ? "" : Math.round(v)}</td>;
                  })}
                </tr>
              ))}</tbody>
            </table>
          </div>
        </ChartCard>
        <ChartCard title="Purchase frequency" description="Number of customers by number of orders">
          <div className="h-[300px]"><ResponsiveContainer>
            <BarChart data={data.frequency_distribution} margin={{ left: 0, right: 8, top: 8 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="orders" {...axisProps} minTickGap={8} />
              <YAxis {...axisProps} width={40} />
              <Tooltip content={<ChartTooltip labelFormatter={(l) => `${l} order(s)`} />} />
              <Bar dataKey="customers" name="Customers" fill="var(--series-3)" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer></div>
        </ChartCard>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <ChartCard title="Most valuable customers" description="Ranked by total spend">
          <SimpleTable maxHeight={420} columns={["Customer", "Segment", "Orders", "Spend", "Last order", "CLV est."]} align={["left", "left", "right", "right", "right", "right"]}
            rows={data.top_customers.map((c) => [<b key="c">{c.customer}</b>, c.segment, c.orders, fmtMoney(c.spend), `${c.recency_days}d ago`, fmtMoney(c.clv)])} />
        </ChartCard>
        <ChartCard title="Cluster profiles" description={data.clusters.method}
          footer={<>Silhouette by k: {data.clusters.silhouette_by_k.map((s) => `k=${s.k}: ${s.silhouette}`).join(" · ")}</>}>
          <SimpleTable columns={["Cluster", "Customers", "Recency", "Orders", "Spend"]} align={["left", "right", "right", "right", "right"]}
            rows={data.clusters.profiles.map((p, i) => [<span key="l" className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: seriesColor(i) }} />{p.label}</span>,
              fmtNum(p.customers), `${p.avg_recency_days.toFixed(0)}d`, p.avg_frequency.toFixed(1), fmtMoney(p.avg_monetary)])} />
        </ChartCard>
      </div>
      <p className="mt-4 text-xs text-muted-foreground">{data.assumptions.note}</p>
    </div>
  );
}
