import { useEffect, useState } from "react";
import { Settings as SettingsIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ErrorState, LoadingState, PageHeader } from "@/components/common";
import { useApiMutation, useApiQuery } from "@/hooks/useApi";
import { api } from "@/services/api";

type AllSettings = Record<string, Record<string, string | number>>;
const META: Record<string, { title: string; desc: string; fields: Record<string, string> }> = {
  general: { title: "General", desc: "Company details shown in the app.", fields: { company_name: "Company name", currency: "Currency code" } },
  inventory: { title: "Inventory", desc: "Defaults and thresholds used by the optimiser.", fields: {
    demand_window_days: "Demand history window (days)", default_lead_time_days: "Default lead time (days)",
    default_service_level: "Default service level (0–1)", overstock_days_of_cover: "Overstocked above (days of cover)" } },
  customers: { title: "Customer analytics", desc: "Assumptions behind the CLV estimate.", fields: { clv_lifespan_years: "Expected customer lifespan (years)", gross_margin: "Gross margin (0–1)" } },
  forecasting: { title: "Forecasting", desc: "Forecast display defaults.", fields: { default_horizon_days: "Default horizon (days)", interval_coverage: "Prediction interval coverage (0–1)" } },
};

function Section({ name, values }: { name: string; values: Record<string, string | number> }) {
  const [v, setV] = useState(values);
  useEffect(() => setV(values), [values]);
  const save = useApiMutation(() => api.put(`/admin/settings/${name}`, { values: v }), [["settings"], ["inventory"], ["customers"]], `${META[name].title} settings saved`);
  return (
    <Card>
      <CardHeader><CardTitle>{META[name].title}</CardTitle><CardDescription>{META[name].desc}</CardDescription></CardHeader>
      <CardContent className="space-y-3">
        {Object.entries(META[name].fields).map(([k, label]) => (
          <div key={k} className="space-y-1.5"><Label htmlFor={`${name}-${k}`} className="text-xs">{label}</Label>
            <Input id={`${name}-${k}`} type={typeof values[k] === "number" ? "number" : "text"} step="any" value={v[k] ?? ""}
              onChange={(e) => setV({ ...v, [k]: typeof values[k] === "number" ? Number(e.target.value) : e.target.value })} /></div>
        ))}
        <Button onClick={() => save.mutate(undefined)} loading={save.isPending}>Save</Button>
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
        <div className="grid gap-5 md:grid-cols-2">{Object.keys(META).map((s) => data[s] && <Section key={s} name={s} values={data[s]} />)}</div>
      )}
    </div>
  );
}
