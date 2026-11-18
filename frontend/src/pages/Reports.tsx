import { useState } from "react";
import { toast } from "sonner";
import { CalendarDays, Download, FileSpreadsheet, FileText, FileType, LineChart, Package, ShoppingBag, Users, CalendarRange, Calendar } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { EmptyState, LoadingState, PageHeader } from "@/components/common";
import { useApiMutation, useApiQuery, useFilterOptions } from "@/hooks/useApi";
import { api, downloadFile } from "@/services/api";
import type { ReportRow } from "@/services/types";
import { fmtDateTime } from "@/utils/format";
import { cn } from "@/lib/utils";

const TYPES = [
  { id: "daily", label: "Daily sales", desc: "The last day with data vs the same weekday last week.", icon: <CalendarDays /> },
  { id: "weekly", label: "Weekly performance", desc: "The last 7 days: trends, top products, stores.", icon: <CalendarRange /> },
  { id: "monthly", label: "Monthly business", desc: "Month-to-date KPIs, categories, products, stores and recommendations.", icon: <Calendar /> },
  { id: "product", label: "Product performance", desc: "Every product's revenue and change over the period.", icon: <ShoppingBag /> },
  { id: "customer", label: "Customer analytics", desc: "RFM segments, clusters, most valuable customers.", icon: <Users /> },
  { id: "forecast", label: "Demand forecasting", desc: "Latest forecast runs, model comparison and predictions.", icon: <LineChart /> },
  { id: "inventory", label: "Inventory", desc: "Stock positions, alerts and reorder recommendations.", icon: <Package /> },
];
const FORMATS = [{ id: "pdf", label: "PDF", icon: <FileText /> }, { id: "xlsx", label: "Excel", icon: <FileSpreadsheet /> }, { id: "csv", label: "CSV", icon: <FileType /> }];

export default function Reports() {
  const { data: opts } = useFilterOptions();
  const [type, setType] = useState("monthly");
  const [fmt, setFmt] = useState("pdf");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const list = useApiQuery<ReportRow[]>(["reports"], "/reports");
  const gen = useApiMutation(() => api.post<ReportRow>("/reports", { report_type: type, format: fmt, start: start || null, end: end || null }), [["reports"]]);
  const dl = (id: number) => downloadFile(`/reports/${id}/download`).catch((e) => toast.error(e.message));
  const usesDates = ["monthly", "product", "daily"].includes(type);

  return (
    <div className="animate-fade-in">
      <PageHeader title="Reports" icon={<FileText className="h-6 w-6 text-primary" />} description="Professionally formatted reports with KPIs, charts, tables, findings and recommendations." />
      <div className="grid gap-5 xl:grid-cols-[1.4fr_1fr]">
        <Card>
          <CardHeader><CardTitle>Generate a report</CardTitle><CardDescription>Every figure is calculated when you click Generate.</CardDescription></CardHeader>
          <CardContent className="space-y-5">
            <div className="grid gap-2 sm:grid-cols-2">
              {TYPES.map((t) => (
                <button key={t.id} onClick={() => setType(t.id)}
                  className={cn("flex gap-3 rounded-xl border p-3 text-left transition-all hover:bg-muted/50", type === t.id && "border-primary bg-primary/5 ring-1 ring-primary")}>
                  <span className="h-fit rounded-lg bg-primary/10 p-2 text-primary [&_svg]:size-4">{t.icon}</span>
                  <span><span className="block text-sm font-medium">{t.label}</span><span className="block text-xs text-muted-foreground">{t.desc}</span></span>
                </button>
              ))}
            </div>
            <div className="grid gap-4 sm:grid-cols-[auto_1fr]">
              <div className="space-y-1.5"><Label className="text-xs text-muted-foreground">Format</Label>
                <div className="flex gap-1.5">{FORMATS.map((f) => (
                  <Button key={f.id} type="button" variant={fmt === f.id ? "default" : "outline"} size="sm" onClick={() => setFmt(f.id)}>{f.icon}{f.label}</Button>
                ))}</div></div>
              {usesDates && (
                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1.5"><Label htmlFor="r-s" className="text-xs text-muted-foreground">From (optional)</Label>
                    <Input id="r-s" type="date" value={start} min={opts?.date_min ?? undefined} max={opts?.date_max ?? undefined} onChange={(e) => setStart(e.target.value)} className="px-2" /></div>
                  <div className="space-y-1.5"><Label htmlFor="r-e" className="text-xs text-muted-foreground">To (optional)</Label>
                    <Input id="r-e" type="date" value={end} min={opts?.date_min ?? undefined} max={opts?.date_max ?? undefined} onChange={(e) => setEnd(e.target.value)} className="px-2" /></div>
                </div>
              )}
            </div>
            <Button size="lg" loading={gen.isPending} onClick={() => gen.mutate(undefined, {
              onSuccess: (r) => { toast.success("Report generated"); void dl(r.id); },
            })}><Download /> Generate & download</Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Report history</CardTitle><CardDescription>Previously generated files</CardDescription></CardHeader>
          <CardContent>
            {list.isLoading ? <LoadingState rows={2} /> : !list.data?.length ? <EmptyState title="No reports yet" description="Generate your first report." /> : (
              <div className="max-h-[520px] space-y-1.5 overflow-y-auto scrollbar-thin">
                {list.data.map((r) => (
                  <div key={r.id} className="flex items-center gap-3 rounded-lg border p-2.5">
                    <Badge variant="secondary" className="uppercase">{r.file_format}</Badge>
                    <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{r.title}</p><p className="text-xs text-muted-foreground">{fmtDateTime(r.created_at)}</p></div>
                    <Button variant="ghost" size="icon" disabled={r.available === false} onClick={() => dl(r.id)} aria-label="Download report"><Download /></Button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
