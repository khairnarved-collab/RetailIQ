import { useRef, useState, type DragEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Database, Download, FileSpreadsheet, FlaskConical, Trash2, UploadCloud } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ConfirmButton, EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/common";
import { useApiMutation, useApiQuery } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";
import { api, downloadFile } from "@/services/api";
import type { Dataset } from "@/services/types";
import { fmtDateTime, fmtNum } from "@/utils/format";
import { cn } from "@/lib/utils";

const MAX_MB = 25;
const STATUS_VARIANT: Record<string, "secondary" | "warning" | "success" | "default"> = {
  uploaded: "secondary", profiled: "warning", cleaned: "default", imported: "success",
};

export default function DataManagement() {
  const { user } = useAuth();
  const nav = useNavigate();
  const { data, isLoading, error, refetch } = useApiQuery<Dataset[]>(["datasets"], "/datasets");
  const { data: samples = [] } = useApiQuery<{ name: string; description: string; size_bytes: number }[]>(["samples"], "/datasets/samples");
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const upload = useApiMutation(async () => {
    const fd = new FormData();
    fd.append("file", file as File);
    if (name.trim()) fd.append("name", name.trim());
    return api.upload<Dataset>("/datasets/upload", fd);
  }, [["datasets"], ["eda-sources"]]);

  const del = useApiMutation((id: number) => api.del(`/datasets/${id}`), [["datasets"], ["eda-sources"]], "Dataset deleted");

  const pick = (f?: File | null) => {
    if (!f) return;
    const ext = f.name.split(".").pop()?.toLowerCase();
    if (!["csv", "xlsx", "xls"].includes(ext ?? "")) return toast.error("Only CSV or Excel files (.csv, .xlsx, .xls) are supported");
    if (f.size > MAX_MB * 1024 * 1024) return toast.error(`File is larger than ${MAX_MB} MB`);
    setFile(f);
    if (!name) setName(f.name.replace(/\.[^.]+$/, ""));
  };
  const onDrop = (e: DragEvent) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files?.[0]); };
  const submit = () => upload.mutate(undefined, {
    onSuccess: (d) => { toast.success(`Uploaded: ${fmtNum(d.n_rows)} rows × ${d.n_cols} columns`); setFile(null); setName(""); nav(`/app/data/${d.id}`); },
  });

  return (
    <div className="animate-fade-in">
      <PageHeader title="Data Management" description="Upload CSV or Excel files, check their quality, clean them, and import them into RetailIQ." />
      <div className="grid gap-5 lg:grid-cols-[1.3fr_1fr]">
        <Card>
          <CardHeader><CardTitle>Upload a dataset</CardTitle>
            <CardDescription>Supported: daily sales (date, store, product, units, optional price/category), customer transactions (customer_id, order_id, order_date, amount) or any table for EDA.</CardDescription></CardHeader>
          <CardContent className="space-y-4">
            <div onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={onDrop}
              onClick={() => inputRef.current?.click()} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
              className={cn("flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-10 text-center transition-colors",
                drag ? "border-primary bg-primary/5" : "hover:border-primary/50 hover:bg-muted/40")}>
              <UploadCloud className="h-9 w-9 text-primary" />
              <p className="mt-3 font-medium">{file ? file.name : "Drop a file here or click to browse"}</p>
              <p className="mt-1 text-xs text-muted-foreground">{file ? `${(file.size / 1024).toFixed(0)} KB` : `CSV, XLSX or XLS · up to ${MAX_MB} MB`}</p>
              <input ref={inputRef} type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={(e) => pick(e.target.files?.[0])} />
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input placeholder="Dataset name (optional)" value={name} onChange={(e) => setName(e.target.value)} />
              <Button onClick={submit} disabled={!file} loading={upload.isPending} className="sm:w-40"><UploadCloud /> Upload & profile</Button>
            </div>
            {upload.isPending && <Progress value={70} className="h-1.5" />}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><FlaskConical className="h-4 w-4 text-warning" /> Sample files</CardTitle>
            <CardDescription>Download a clearly labelled synthetic file, then upload it to try the full pipeline.</CardDescription></CardHeader>
          <CardContent className="space-y-2.5">
            {samples.map((s) => (
              <div key={s.name} className="flex items-center gap-3 rounded-lg border p-3">
                <FileSpreadsheet className="h-5 w-5 shrink-0 text-primary" />
                <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{s.name}</p><p className="text-xs text-muted-foreground">{s.description}</p></div>
                <Button size="icon" variant="ghost" aria-label={`Download ${s.name}`}
                  onClick={() => downloadFile(`/datasets/samples/${s.name}`, s.name).catch((e) => toast.error(e.message))}><Download /></Button>
              </div>
            ))}
            <p className="pt-1 text-xs text-muted-foreground">The real M5 Walmart files (Kaggle login required) are loaded with the command-line ingestion pipeline; see the README.</p>
          </CardContent>
        </Card>
      </div>

      <Card className="mt-5">
        <CardHeader><CardTitle>Dataset history</CardTitle><CardDescription>Every dataset uploaded or loaded, with its processing status.</CardDescription></CardHeader>
        <CardContent>
          {isLoading ? <LoadingState rows={2} /> : error ? <ErrorState error={error} onRetry={refetch} /> : !data?.length ? (
            <EmptyState icon={<Database />} title="No datasets yet" description="Upload your first file above." />
          ) : (
            <div className="rounded-lg border">
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Name</TableHead><TableHead>Type</TableHead><TableHead className="text-right">Rows</TableHead>
                  <TableHead>Status</TableHead><TableHead>Uploaded</TableHead><TableHead className="text-right">Actions</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {data.map((d) => (
                    <TableRow key={d.id}>
                      <TableCell className="min-w-[14rem]">
                        <Link to={`/app/data/${d.id}`} className="font-medium hover:text-primary hover:underline">{d.name}</Link>
                        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">{d.original_filename}{d.is_synthetic && <Badge variant="warning">synthetic</Badge>}</div>
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-sm">{d.kind_label}</TableCell>
                      <TableCell className="tabular text-right">{fmtNum(d.n_rows)}</TableCell>
                      <TableCell><Badge variant={STATUS_VARIANT[d.status] ?? "secondary"}>{d.status}</Badge></TableCell>
                      <TableCell className="whitespace-nowrap text-sm text-muted-foreground">{fmtDateTime(d.created_at)}</TableCell>
                      <TableCell className="whitespace-nowrap text-right">
                        <Button asChild variant="outline" size="sm"><Link to={`/app/data/${d.id}`}>Open</Link></Button>
                        {user?.role === "admin" && d.kind !== "m5_sales" && (
                          <ConfirmButton variant="ghost" size="icon" aria-label="Delete dataset" className="ml-1 text-critical"
                            title={`Delete "${d.name}"?`} description="The uploaded file, cleaned outputs and any customer records imported from it are removed. Sales rows already merged into the warehouse stay."
                            onConfirm={() => del.mutate(d.id)}><Trash2 /></ConfirmButton>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
