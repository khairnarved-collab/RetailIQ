import { useEffect, useState } from "react";
import { toast } from "sonner";
import { FlaskConical, RotateCcw, Settings as SettingsIcon, Trash2 } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ConfirmButton } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ErrorState, LoadingState, PageHeader } from "@/components/common";
import { useApiMutation, useApiQuery } from "@/hooks/useApi";
import { api } from "@/services/api";

type AllSettings = Record<string, Record<string, string | number>>;
const META: Record<string, { title: string; desc: string; fields: Record<string, string> }> = {
  general: { title: "General", desc: "Company name and the currency used for every amount in the app and reports.", fields: { company_name: "Company name", currency: "Currency" } },
  inventory: { title: "Inventory", desc: "Defaults and thresholds used by the optimiser.", fields: {
    demand_window_days: "Demand history window (days)", default_lead_time_days: "Default lead time (days)",
    default_service_level: "Default service level (0–1)", overstock_days_of_cover: "Overstocked above (days of cover)" } },
  customers: { title: "Customer analytics", desc: "Assumptions behind the CLV estimate.", fields: { clv_lifespan_years: "Expected customer lifespan (years)", gross_margin: "Gross margin (0–1)" } },
  forecasting: { title: "Forecasting", desc: "Forecast display defaults.", fields: { default_horizon_days: "Default horizon (days)", interval_coverage: "Prediction interval coverage (0–1)" } },
};

function Section({ name, values }: { name: string; values: Record<string, string | number> }) {
  const [v, setV] = useState(values);
  useEffect(() => setV(values), [values]);
  const save = useApiMutation(() => api.put(`/admin/settings/${name}`, { values: v }), [["settings"], ["inventory"], ["customers"], ["insights"]], `${META[name].title} settings saved`);
  return (
    <Card>
      <CardHeader><CardTitle>{META[name].title}</CardTitle><CardDescription>{META[name].desc}</CardDescription></CardHeader>
      <CardContent className="space-y-3">
        {Object.entries(META[name].fields).map(([k, label]) => k === "currency" ? (
          <div key={k} className="space-y-1.5"><Label className="text-xs">{label}</Label>
            <Select value={String(v[k] ?? "USD")} onValueChange={(val) => setV({ ...v, [k]: val })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {[["INR", "₹ Indian Rupee (INR)"], ["USD", "$ US Dollar (USD)"], ["EUR", "€ Euro (EUR)"], ["GBP", "£ British Pound (GBP)"], ["AED", "UAE Dirham (AED)"], ["SGD", "Singapore Dollar (SGD)"]]
                  .map(([c, l]) => <SelectItem key={c} value={c}>{l}</SelectItem>)}
              </SelectContent>
            </Select>
            <p className="text-[11px] text-muted-foreground">Changes the symbol and number format only; amounts are not converted.</p></div>
        ) : (
          <div key={k} className="space-y-1.5"><Label htmlFor={`${name}-${k}`} className="text-xs">{label}</Label>
            <Input id={`${name}-${k}`} type={typeof values[k] === "number" ? "number" : "text"} step="any" value={v[k] ?? ""}
              onChange={(e) => setV({ ...v, [k]: typeof values[k] === "number" ? Number(e.target.value) : e.target.value })} /></div>
        ))}
        <Button onClick={() => save.mutate(undefined)} loading={save.isPending}>Save</Button>
      </CardContent>
    </Card>
  );
}

function DemoData() {
  const { data, refetch } = useApiQuery<{ demo_sales_rows: number; other_sales_rows: number; demo_customer_datasets: number; demo_present: boolean }>(["demo-data"], "/admin/demo-data");
  const inv = [["demo-data"], ["dashboard"], ["filters"], ["inventory"], ["customers"], ["insights"], ["datasets"], ["eda"], ["fc-runs"]];
  const remove = useApiMutation(() => api.post<{ removed_sales_rows: number }>("/admin/demo-data/remove"), inv);
  const restore = useApiMutation(() => api.post<{ restored_sales_rows: number }>("/admin/demo-data/restore"), inv);
  return (
    <Card className="md:col-span-2">
      <CardHeader><CardTitle className="flex items-center gap-2"><FlaskConical className="h-4 w-4 text-warning" /> Demo data</CardTitle>
        <CardDescription>The workspace starts with SYNTHETIC demo data. Remove it to analyse only the data you uploaded; your uploads are never touched. You can restore it at any time.</CardDescription></CardHeader>
      <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted-foreground">{data ? <>Demo sales rows: <b className="text-foreground">{data.demo_sales_rows.toLocaleString()}</b> · Your sales rows: <b className="text-foreground">{data.other_sales_rows.toLocaleString()}</b></> : "Loading…"}</p>
        <div className="flex gap-2">
          <ConfirmButton variant="destructive" disabled={!data?.demo_present} title="Remove the demo data?"
            description="All SYNTHETIC demo sales, products, stores, stock, forecasts and demo customers are deleted. Data you uploaded stays."
            confirmLabel="Remove demo data"
            onConfirm={() => remove.mutate(undefined, { onSuccess: (r) => { toast.success(`Removed ${r.removed_sales_rows.toLocaleString()} demo sales rows`); refetch(); } })}>
            <Trash2 /> Remove demo data</ConfirmButton>
          <Button variant="outline" disabled={!!data?.demo_present} loading={restore.isPending}
            onClick={() => restore.mutate(undefined, { onSuccess: (r) => { toast.success(`Restored ${r.restored_sales_rows.toLocaleString()} demo sales rows`); refetch(); } })}>
            <RotateCcw /> Restore demo data</Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function AdminSettings() {
  const { data, isLoading, error, refetch } = useApiQuery<AllSettings>(["settings"], "/admin/settings");
  return (
    <div className="animate-fade-in">
      <PageHeader title="Application settings" icon={<SettingsIcon className="h-6 w-6 text-primary" />} description="Business assumptions used across RetailIQ. Changes apply immediately." />
      {isLoading ? <LoadingState /> : error || !data ? <ErrorState error={error} onRetry={refetch} /> : (
        <div className="grid gap-5 md:grid-cols-2">
          {Object.keys(META).map((s) => data[s] && <Section key={s} name={s} values={data[s]} />)}
          <DemoData />
        </div>
      )}
    </div>
  );
}
