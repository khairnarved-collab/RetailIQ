import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { AlertTriangle, ArrowLeft, CheckCircle2, Download, Import, Microscope, Sparkles, Wand2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ErrorState, KpiCard, LoadingState, PageHeader, SimpleTable, SyntheticBanner } from "@/components/common";
import { useApiMutation, useApiQuery } from "@/hooks/useApi";
import { api, downloadFile } from "@/services/api";
import type { CleaningSummary, Dataset, Preview, QualityReport } from "@/services/types";
import { fmtDateTime, fmtNum } from "@/utils/format";
import { cn } from "@/lib/utils";

type Detail = Dataset & { quality: QualityReport | null; cleaned_quality: QualityReport | null; cleaning_summary: CleaningSummary | null; preview: Preview | null };

function PreviewTable({ p, max = 400 }: { p: Preview; max?: number }) {
  return <SimpleTable maxHeight={max} columns={p.columns} rows={p.rows.map((r) => r.map((v) => (v === null ? <span className="text-muted-foreground/60">null</span> : String(v))))} />;
}

function QualityView({ q }: { q: QualityReport }) {
  const score = q.quality_score;
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <KpiCard label="Rows" value={fmtNum(q.n_rows)} />
        <KpiCard label="Columns" value={fmtNum(q.n_cols)} />
        <KpiCard label="Missing values" value={fmtNum(q.total_missing)} />
        <KpiCard label="Duplicate rows" value={fmtNum(q.duplicate_rows)} />
        <Card><CardContent className="p-4 sm:p-5">
          <p className="text-xs font-medium text-muted-foreground sm:text-[13px]">Quality score</p>
          <p className="tabular mt-1.5 text-2xl font-semibold">{score}<span className="text-sm text-muted-foreground">/100</span></p>
          <Progress value={score} className="mt-2 h-1.5" indicatorClassName={score >= 85 ? "bg-success" : score >= 65 ? "bg-warning" : "bg-critical"} />
        </CardContent></Card>
      </div>
      <p className="text-sm text-muted-foreground">Detected type: <b className="text-foreground">{q.detected_kind_label}</b>
        {q.required_columns.length > 0 && <> · required columns: {q.required_columns.join(", ")}</>}</p>
      <SimpleTable maxHeight={460} columns={["Column", "Type", "Missing", "Unique", "Range", "Issues"]}
        rows={q.columns.map((c) => [
          <span key="n" className="font-medium">{c.name}</span>,
          <span key="t" className={cn(c.inferred_type.includes("text") && "text-warning")}>{c.inferred_type}</span>,
          `${fmtNum(c.missing)} (${c.missing_pct}%)`, fmtNum(c.unique),
          c.min !== undefined ? `${fmtNum(c.min)} – ${fmtNum(c.max)}` : <span key="r" className="text-muted-foreground">{c.sample_values.slice(0, 2).join(", ")}</span>,
          c.issues.length ? (
            <ul key="i" className="space-y-0.5 whitespace-normal text-xs">{c.issues.map((i) => <li key={i} className="flex gap-1"><AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-warning" />{i}</li>)}</ul>
          ) : <span key="ok" className="inline-flex items-center gap-1 text-xs text-success"><CheckCircle2 className="h-3 w-3" /> OK</span>,
        ])} />
    </div>
  );
}

export default function DatasetDetail() {
  const { id } = useParams();
  const { data, isLoading, error, refetch } = useApiQuery<Detail>(["dataset", id], `/datasets/${id}`);
  const [kind, setKind] = useState<string>("auto");
  const [rejected, setRejected] = useState<Preview | null>(null);
  const [tab, setTab] = useState("quality");

  const clean = useApiMutation(() => api.post<{ summary: CleaningSummary; rejected_preview: Preview }>(`/datasets/${id}/clean${kind !== "auto" ? `?kind=${kind}` : ""}`),
    [["dataset", id], ["datasets"]]);
  const imp = useApiMutation(() => api.post<{ imported_rows: number; notes: string[] }>(`/datasets/${id}/import`),
    [["dataset", id], ["datasets"], ["dashboard"], ["filters"], ["notifications"]]);

  if (isLoading) return <LoadingState rows={4} />;
  if (error || !data) return <ErrorState error={error} onRetry={refetch} />;
  const importable = ["sales_long", "customer_transactions"].includes(data.kind);
  const dl = (w: string) => downloadFile(`/datasets/${id}/download/${w}`).catch((e) => toast.error(e.message));

  return (
    <div className="animate-fade-in">
      <Button asChild variant="ghost" size="sm" className="mb-2 -ml-2"><Link to="/app/data"><ArrowLeft /> All datasets</Link></Button>
      <PageHeader title={data.name}
        description={<>{data.original_filename} · {data.kind_label} · uploaded {fmtDateTime(data.created_at)} · status <Badge variant="secondary">{data.status}</Badge></>}
        actions={<>
          <Button variant="outline" size="sm" onClick={() => dl("raw")}><Download /> Original</Button>
          {data.has_cleaned && <Button variant="outline" size="sm" onClick={() => dl("cleaned")}><Download /> Cleaned</Button>}
          {data.has_rejected && <Button variant="outline" size="sm" onClick={() => dl("rejected")}><Download /> Rejected rows</Button>}
          {data.kind !== "m5_sales" && <Button asChild variant="outline" size="sm"><Link to={`/app/eda?source=dataset:${data.id}`}><Microscope /> Explore (EDA)</Link></Button>}
        </>} />
      <SyntheticBanner show={data.is_synthetic} text={data.description ?? undefined} />

      {data.kind === "m5_sales" ? (
        <Card><CardContent className="p-5 text-sm text-muted-foreground">{data.description} This dataset was loaded by the M5 ingestion pipeline and feeds the dashboard, forecasting and inventory modules directly.</CardContent></Card>
      ) : (
        <>
          <Card className="mb-5">
            <CardHeader><CardTitle className="flex items-center gap-2"><Wand2 className="h-4 w-4 text-primary" /> Cleaning pipeline</CardTitle>
              <CardDescription>Standardises names, converts types, handles duplicates, validates required fields and flags outliers. Rows are never silently deleted: unusable rows go to a downloadable "rejected rows" file with the reason.</CardDescription></CardHeader>
            <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <Select value={kind} onValueChange={setKind}>
                <SelectTrigger className="sm:w-72" aria-label="Dataset type"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">Auto-detect type ({data.quality?.detected_kind_label})</SelectItem>
                  <SelectItem value="sales_long">Daily sales</SelectItem>
                  <SelectItem value="customer_transactions">Customer transactions</SelectItem>
                  <SelectItem value="generic">Generic table (EDA only)</SelectItem>
                </SelectContent>
              </Select>
              <Button loading={clean.isPending} onClick={() => clean.mutate(undefined, {
                onSuccess: (r) => { setRejected(r.rejected_preview); setTab("cleaning"); toast.success(`Cleaned: ${fmtNum(r.summary.rows_clean)} rows kept, ${fmtNum(r.summary.rows_rejected)} set aside`); },
              })}><Sparkles /> Run cleaning</Button>
              {importable && data.has_cleaned && (
                <Button variant="secondary" loading={imp.isPending} onClick={() => imp.mutate(undefined, {
                  onSuccess: (r) => { toast.success(`Imported ${fmtNum(r.imported_rows)} rows`); r.notes.forEach((n) => toast.info(n)); },
                })}><Import /> {data.status === "imported" ? "Re-import" : "Import into RetailIQ"}</Button>
              )}
            </CardContent>
          </Card>

          <Tabs value={tab} onValueChange={setTab}>
            <TabsList>
              <TabsTrigger value="quality">Quality report</TabsTrigger>
              <TabsTrigger value="cleaning" disabled={!data.cleaning_summary}>Cleaning summary</TabsTrigger>
              <TabsTrigger value="preview">Preview</TabsTrigger>
            </TabsList>
            <TabsContent value="quality">{data.quality ? <QualityView q={data.quality} /> : <p className="text-sm text-muted-foreground">No report.</p>}</TabsContent>
            <TabsContent value="cleaning">
              {data.cleaning_summary && (
                <div className="space-y-5">
                  <div className="grid grid-cols-3 gap-3">
                    <KpiCard label="Rows in" value={fmtNum(data.cleaning_summary.rows_in)} />
                    <KpiCard label="Clean rows" value={fmtNum(data.cleaning_summary.rows_clean)} />
                    <KpiCard label="Rejected (kept in file)" value={fmtNum(data.cleaning_summary.rows_rejected)} />
                  </div>
                  <Card><CardContent className="divide-y p-0">
                    {data.cleaning_summary.steps.map((s, i) => (
                      <div key={s.step} className="flex gap-3 p-4">
                        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">{i + 1}</span>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2"><p className="font-medium">{s.step}</p>
                            <Badge variant={s.affected ? "warning" : "success"}>{fmtNum(s.affected)} affected</Badge></div>
                          <p className="text-sm text-muted-foreground">{s.detail}</p>
                          {s.changes && Object.keys(s.changes).length > 0 && (
                            <div className="mt-2 flex flex-wrap gap-1.5">
                              {Object.entries(s.changes).map(([k, v]) => (
                                <span key={k} className="rounded-md bg-muted px-2 py-1 text-xs">
                                  <b className="font-medium">{k}</b> → {typeof v === "object" && v !== null
                                    ? Object.entries(v as Record<string, unknown>).map(([a, b]) => `${a.replace(/_/g, " ")}: ${String(b)}`).join(", ")
                                    : String(v)}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </CardContent></Card>
                  {data.cleaned_quality && <><h3 className="font-semibold">After cleaning</h3><QualityView q={data.cleaned_quality} /></>}
                  {rejected && rejected.rows.length > 0 && <><h3 className="font-semibold">Rejected rows (first 20)</h3><PreviewTable p={rejected} max={300} /></>}
                </div>
              )}
            </TabsContent>
            <TabsContent value="preview">
              {data.preview ? <><p className="mb-2 text-sm text-muted-foreground">First {data.preview.rows.length} rows of the {data.has_cleaned ? "cleaned" : "original"} data.</p><PreviewTable p={data.preview} /></> : <p className="text-sm text-muted-foreground">No preview available.</p>}
            </TabsContent>
          </Tabs>
        </>
      )}
    </div>
  );
}
