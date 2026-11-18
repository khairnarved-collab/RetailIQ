import { Link } from "react-router-dom";
import { AlertOctagon, AlertTriangle, ArrowRight, Info, Lightbulb, RefreshCw, TrendingUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState, ErrorState, LoadingState, PageHeader, SyntheticBanner } from "@/components/common";
import { useApiQuery, useFilterOptions } from "@/hooks/useApi";
import type { Insight } from "@/services/types";
import { fmtDate } from "@/utils/format";
import { cn } from "@/lib/utils";

const SEV = {
  critical: { icon: <AlertOctagon />, cls: "border-l-critical", badge: "critical" as const, label: "Critical" },
  warning: { icon: <AlertTriangle />, cls: "border-l-warning", badge: "warning" as const, label: "Needs attention" },
  positive: { icon: <TrendingUp />, cls: "border-l-success", badge: "success" as const, label: "Opportunity" },
  info: { icon: <Info />, cls: "border-l-primary", badge: "default" as const, label: "Information" },
};

interface Resp { generated_for: { start: string; end: string; comparison: { start: string; end: string } } | null; insights: Insight[]; counts: Record<string, number> }

export default function Insights() {
  const { data: opts } = useFilterOptions();
  const { data, isLoading, error, refetch, isFetching } = useApiQuery<Resp>(["insights"], "/insights");
  return (
    <div className="animate-fade-in">
      <PageHeader title="Business Insights" icon={<Lightbulb className="h-6 w-6 text-primary" />}
        description={data?.generated_for ? <>Last 28 days ({fmtDate(data.generated_for.start)} – {fmtDate(data.generated_for.end)}) compared with the 28 days before.</> : "Automatically generated from your data"}
        actions={<Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}><RefreshCw className={cn(isFetching && "animate-spin")} /> Re-analyse</Button>} />
      <SyntheticBanner show={!!opts?.synthetic_data} />
      {isLoading ? <LoadingState rows={4} /> : error || !data ? <ErrorState error={error} onRetry={refetch} /> : data.insights.length === 0 ? (
        <EmptyState title="No insights yet" description="Load sales data to generate insights." />
      ) : (
        <>
          <div className="mb-5 flex flex-wrap gap-2">
            {(Object.keys(SEV) as (keyof typeof SEV)[]).map((k) => <Badge key={k} variant={SEV[k].badge} className="px-3 py-1 text-sm">{SEV[k].icon}{data.counts[k] ?? 0} {SEV[k].label}</Badge>)}
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            {data.insights.map((i, idx) => {
              const s = SEV[i.severity];
              const data_ = i.possible_causes.filter((c) => c.startsWith("Data:"));
              const hyp = i.possible_causes.filter((c) => !c.startsWith("Data:"));
              return (
                <Card key={idx} className={cn("border-l-4", s.cls)}>
                  <CardContent className="space-y-3 p-5">
                    <div className="flex items-start justify-between gap-3">
                      <h3 className="font-semibold leading-snug">{i.title}</h3>
                      <Badge variant={s.badge} className="shrink-0">{s.icon}{s.label}</Badge>
                    </div>
                    <div><p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Finding (measured)</p><p className="mt-0.5 text-sm">{i.finding}</p></div>
                    {data_.length > 0 && (
                      <div><p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Supporting data</p>
                        <ul className="mt-0.5 space-y-0.5 text-sm">{data_.map((c) => <li key={c}>• {c.replace(/^Data:\s*/, "")}</li>)}</ul></div>
                    )}
                    {hyp.length > 0 && (
                      <div className="rounded-lg bg-muted/50 p-2.5"><p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Possible explanations (not proven)</p>
                        <ul className="mt-0.5 space-y-0.5 text-sm text-muted-foreground">{hyp.map((c) => <li key={c}>• {c.replace(/^Hypothesis:\s*/, "")}</li>)}</ul></div>
                    )}
                    <div className="flex flex-col gap-2 border-t pt-3 sm:flex-row sm:items-center sm:justify-between">
                      <p className="text-sm"><b>Recommendation:</b> {i.recommendation}</p>
                      {i.link && <Button asChild variant="ghost" size="sm" className="shrink-0"><Link to={i.link}>Open <ArrowRight /></Link></Button>}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
          <p className="mt-5 text-xs text-muted-foreground">Findings are calculated from the data. Explanations are hypotheses to investigate: the data shows what changed and what is correlated, not why.</p>
        </>
      )}
    </div>
  );
}
