import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { BellRing, Boxes, Download, Info, Pencil, Plus, Search, Truck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState, ErrorState, LoadingState, PageHeader, SimpleTable, StatusBadge, SyntheticBanner } from "@/components/common";
import { useApiMutation, useApiQuery, useFilterOptions } from "@/hooks/useApi";
import { api, downloadFile, qs } from "@/services/api";
import type { InventoryItem, InventoryResponse, InvStatus } from "@/services/types";
import { currencySymbol, fmtMoney, fmtNum } from "@/utils/format";
import { cn } from "@/lib/utils";

const STATUSES: InvStatus[] = ["Critical", "Low Stock", "Overstocked", "Healthy"];
const TILE: Record<InvStatus, string> = { Critical: "border-critical/40 text-critical", "Low Stock": "border-warning/40 text-warning", Overstocked: "border-border text-muted-foreground", Healthy: "border-success/40 text-success" };
interface Supplier { id: number; name: string; contact_email: string | null; default_lead_time_days: number }

export default function Inventory() {
  const { data: opts } = useFilterOptions();
  const [store, setStore] = useState("all");
  const [cat, setCat] = useState("all");
  const [status, setStatus] = useState<InvStatus | "all">("all");
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [edit, setEdit] = useState<InventoryItem | null>(null);
  useEffect(() => { const t = setTimeout(() => setQ(search), 300); return () => clearTimeout(t); }, [search]);

  const path = `/inventory${qs({ store_id: store === "all" ? null : store, category_id: cat === "all" ? null : cat, status: status === "all" ? null : status, search: q })}`;
  const { data, isLoading, error, refetch } = useApiQuery<InventoryResponse>(["inventory", path], path, { placeholderData: (p) => p });
  const alerts = useApiMutation(() => api.post<{ created: boolean; message: string }>("/inventory/alerts"), [["notifications"]]);
  const exportCsv = async () => {
    try { const r = await api.post<{ id: number }>("/reports", { report_type: "inventory", format: "xlsx" }); await downloadFile(`/reports/${r.id}/download`); }
    catch (e) { toast.error((e as Error).message); }
  };

  return (
    <div className="animate-fade-in">
      <PageHeader title="Inventory Optimisation" icon={<Boxes className="h-6 w-6 text-primary" />}
        description="Replenishment advice for every store and product: safety stock, reorder point, recommended stock and stock-out risk."
        actions={<>
          <Button variant="outline" size="sm" loading={alerts.isPending} onClick={() => alerts.mutate(undefined, { onSuccess: (r) => toast[r.created ? "warning" : "success"](r.message) })}><BellRing /> Send alert</Button>
          <Button variant="outline" size="sm" onClick={exportCsv}><Download /> Export Excel</Button>
        </>} />
      <SyntheticBanner show={!!opts?.synthetic_data} text="Stock levels in the demo are SYNTHETIC (flagged 'synthetic'). Edit an item to enter real stock counts; edited items are flagged 'user'." />

      <Tabs defaultValue="positions">
        <TabsList><TabsTrigger value="positions">Stock positions</TabsTrigger><TabsTrigger value="suppliers"><Truck /> Suppliers</TabsTrigger><TabsTrigger value="method"><Info /> How it works</TabsTrigger></TabsList>
        <TabsContent value="positions" className="space-y-4">
          {data && (
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
              {STATUSES.map((s) => (
                <button key={s} onClick={() => setStatus(status === s ? "all" : s)}
                  className={cn("rounded-xl border bg-card p-4 text-left transition-all hover:shadow-md", status === s && "ring-2 ring-ring", TILE[s])}>
                  <StatusBadge status={s} />
                  <p className="tabular mt-2 text-2xl font-semibold text-foreground">{data.summary.counts[s]}</p>
                  <p className="text-xs text-muted-foreground">items · click to filter</p>
                </button>
              ))}
              <div className="rounded-xl border bg-card p-4"><p className="text-xs text-muted-foreground">Stock value (cost)</p><p className="tabular mt-2 text-xl font-semibold">{fmtMoney(data.summary.stock_value)}</p></div>
              <div className="rounded-xl border bg-card p-4"><p className="text-xs text-muted-foreground">Recommended orders</p><p className="tabular mt-2 text-xl font-semibold">{fmtNum(data.summary.units_to_order)} units</p><p className="text-xs text-muted-foreground">{fmtMoney(data.summary.recommended_order_value)} at cost</p></div>
            </div>
          )}
          <Card><CardContent className="grid gap-2 p-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="relative"><Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input placeholder="Search product or SKU" value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9" /></div>
            <Select value={store} onValueChange={setStore}><SelectTrigger aria-label="Store"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="all">All stores</SelectItem>{opts?.stores.map((s) => <SelectItem key={s.id} value={String(s.id)}>{s.code} · {s.name}</SelectItem>)}</SelectContent></Select>
            <Select value={cat} onValueChange={setCat}><SelectTrigger aria-label="Category"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="all">All categories</SelectItem>{opts?.categories.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>)}</SelectContent></Select>
            <Select value={status} onValueChange={(v) => setStatus(v as InvStatus | "all")}><SelectTrigger aria-label="Status"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="all">All statuses</SelectItem>{STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent></Select>
          </CardContent></Card>

          {isLoading ? <LoadingState rows={3} /> : error || !data ? <ErrorState error={error} onRetry={refetch} /> : data.items.length === 0 ? (
            <EmptyState title="No items match" description="Change the filters or search." />
          ) : (
            <Card>
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Product</TableHead><TableHead>Store</TableHead><TableHead>Status</TableHead>
                  <TableHead className="text-right">On hand</TableHead><TableHead className="text-right">Demand/day</TableHead>
                  <TableHead className="text-right">Days left</TableHead><TableHead className="text-right">Safety stock</TableHead>
                  <TableHead className="text-right">Reorder pt.</TableHead><TableHead className="text-right">Target</TableHead>
                  <TableHead className="text-right">Order qty</TableHead><TableHead className="text-right">Stock-out risk</TableHead><TableHead />
                </TableRow></TableHeader>
                <TableBody>
                  {data.items.slice(0, 300).map((i) => (
                    <TableRow key={i.id} className="cursor-pointer" onClick={() => setEdit(i)}>
                      <TableCell className="min-w-[13rem]"><p className="font-medium">{i.product_name}</p>
                        <p className="text-xs text-muted-foreground">{i.sku} · {i.supplier ?? "no supplier"} {i.on_hand_source !== "user" && <Badge variant="outline" className="ml-1 py-0 text-[10px]">{i.on_hand_source}</Badge>}</p></TableCell>
                      <TableCell className="whitespace-nowrap">{i.store_code}</TableCell>
                      <TableCell><StatusBadge status={i.status} /></TableCell>
                      <TableCell className="tabular text-right font-medium">{fmtNum(i.on_hand)}</TableCell>
                      <TableCell className="tabular text-right">{fmtNum(i.avg_daily_demand)}</TableCell>
                      <TableCell className={cn("tabular text-right", (i.days_of_inventory ?? 999) < i.lead_time_days && "font-semibold text-critical")}>{i.days_of_inventory === null ? "∞" : fmtNum(i.days_of_inventory)}</TableCell>
                      <TableCell className="tabular text-right">{fmtNum(i.safety_stock)}</TableCell>
                      <TableCell className="tabular text-right">{fmtNum(i.reorder_point)}</TableCell>
                      <TableCell className="tabular text-right">{fmtNum(i.recommended_stock_level)}</TableCell>
                      <TableCell className="tabular text-right font-semibold">{i.recommended_order_qty ? fmtNum(i.recommended_order_qty) : "–"}</TableCell>
                      <TableCell className="tabular text-right">{i.stockout_risk_pct.toFixed(0)}%</TableCell>
                      <TableCell><Button variant="ghost" size="icon" aria-label="Edit item"><Pencil /></Button></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {data.items.length > 300 && <p className="p-3 text-xs text-muted-foreground">Showing 300 of {data.items.length}. Use the filters or export to Excel for all rows.</p>}
            </Card>
          )}
        </TabsContent>
        <TabsContent value="suppliers"><Suppliers /></TabsContent>
        <TabsContent value="method"><Method notes={data?.assumptions.notes ?? []} /></TabsContent>
      </Tabs>
      {edit && <EditDialog item={edit} onClose={() => setEdit(null)} />}
    </div>
  );
}

function EditDialog({ item, onClose }: { item: InventoryItem; onClose: () => void }) {
  const { data: suppliers = [] } = useApiQuery<Supplier[]>(["suppliers"], "/suppliers");
  const [f, setF] = useState({
    on_hand: String(item.on_hand), lead_time_days: String(item.lead_time_days), review_period_days: String(item.review_period_days),
    service_level: String(Math.round(item.service_level * 1000) / 10), min_order_qty: String(item.min_order_qty), pack_size: String(item.pack_size),
    unit_cost: item.unit_cost === null ? "" : String(item.unit_cost), supplier_id: item.supplier_id ? String(item.supplier_id) : "none",
    replenishment_policy: item.replenishment_policy,
  });
  const save = useApiMutation((b: Record<string, unknown>) => api.patch<InventoryItem>(`/inventory/${item.id}`, b), [["inventory"]], "Inventory updated");
  const field = (k: keyof typeof f, label: string, hint?: string, step = "1") => (
    <div className="space-y-1.5"><Label htmlFor={k} className="text-xs">{label}</Label>
      <Input id={k} type="number" step={step} min="0" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}</div>
  );
  const submit = () => {
    const sl = Number(f.service_level) / 100;
    if (!(sl > 0.5 && sl < 1)) return toast.error("Service level must be between 50% and 99.99%");
    save.mutate({
      on_hand: Number(f.on_hand), lead_time_days: Number(f.lead_time_days), review_period_days: Number(f.review_period_days), service_level: sl,
      min_order_qty: Number(f.min_order_qty), pack_size: Number(f.pack_size), unit_cost: f.unit_cost === "" ? null : Number(f.unit_cost),
      supplier_id: f.supplier_id === "none" ? null : Number(f.supplier_id), replenishment_policy: f.replenishment_policy,
    }, { onSuccess: onClose });
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader><DialogTitle>{item.product_name} · {item.store_code}</DialogTitle>
          <DialogDescription>{item.recommendation}</DialogDescription></DialogHeader>
        <div className="grid grid-cols-2 gap-2 rounded-lg bg-muted/50 p-3 text-xs sm:grid-cols-4">
          <div><p className="text-muted-foreground">Avg demand</p><p className="font-semibold">{item.avg_daily_demand}/day ± {item.demand_std}</p></div>
          <div><p className="text-muted-foreground">Demand source</p><p className="font-semibold">{item.demand_source}</p></div>
          <div><p className="text-muted-foreground">Safety stock</p><p className="font-semibold">z {item.z} × σ × √L = {item.safety_stock}</p></div>
          <div><p className="text-muted-foreground">EOQ</p><p className="font-semibold">{item.eoq ?? "needs unit cost"}</p></div>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {field("on_hand", "Current stock (units)")}
          {field("lead_time_days", "Lead time (days)", "Supplier delivery time")}
          {field("review_period_days", "Review period (days)", "Days between orders")}
          {field("service_level", "Service level (%)", "e.g. 95 = 95% no stock-out", "0.1")}
          {field("min_order_qty", "Minimum order qty")}
          {field("pack_size", "Pack size", "Orders round up to this")}
          {field("unit_cost", `Unit cost (${currencySymbol()})`, undefined, "0.01")}
          <div className="space-y-1.5"><Label className="text-xs">Supplier</Label>
            <Select value={f.supplier_id} onValueChange={(v) => setF({ ...f, supplier_id: v })}><SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="none">None</SelectItem>{suppliers.map((s) => <SelectItem key={s.id} value={String(s.id)}>{s.name}</SelectItem>)}</SelectContent></Select></div>
          <div className="space-y-1.5"><Label className="text-xs">Replenishment policy</Label>
            <Select value={f.replenishment_policy} onValueChange={(v) => setF({ ...f, replenishment_policy: v })}><SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="order_up_to">Order up to target</SelectItem><SelectItem value="eoq">At least EOQ</SelectItem></SelectContent></Select></div>
        </div>
        <DialogFooter><Button variant="outline" onClick={onClose}>Cancel</Button><Button onClick={submit} loading={save.isPending}>Save & recalculate</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Suppliers() {
  const { data = [], isLoading } = useApiQuery<Supplier[]>(["suppliers"], "/suppliers");
  const [f, setF] = useState({ name: "", contact_email: "", default_lead_time_days: "7" });
  const add = useApiMutation(() => api.post("/suppliers", { name: f.name, contact_email: f.contact_email || null, default_lead_time_days: Number(f.default_lead_time_days) }), [["suppliers"]], "Supplier added");
  const valid = useMemo(() => f.name.trim().length >= 2 && Number(f.default_lead_time_days) >= 1, [f]);
  return (
    <div className="grid gap-5 lg:grid-cols-[1.5fr_1fr]">
      <Card><CardHeader><CardTitle>Suppliers</CardTitle></CardHeader><CardContent>
        {isLoading ? <LoadingState rows={2} /> : <SimpleTable columns={["Name", "Contact", "Default lead time"]}
          rows={data.map((s) => [<b key="n">{s.name}</b>, s.contact_email ?? "–", `${s.default_lead_time_days} days`])} />}
      </CardContent></Card>
      <Card><CardHeader><CardTitle>Add supplier</CardTitle><CardDescription>Then assign it to items from the stock table.</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          <Input placeholder="Supplier name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
          <Input placeholder="Contact email (optional)" type="email" value={f.contact_email} onChange={(e) => setF({ ...f, contact_email: e.target.value })} />
          <div className="space-y-1.5"><Label className="text-xs">Default lead time (days)</Label>
            <Input type="number" min="1" value={f.default_lead_time_days} onChange={(e) => setF({ ...f, default_lead_time_days: e.target.value })} /></div>
          <Button disabled={!valid} loading={add.isPending} onClick={() => add.mutate(undefined, { onSuccess: () => setF({ name: "", contact_email: "", default_lead_time_days: "7" }) })}><Plus /> Add supplier</Button>
        </CardContent></Card>
    </div>
  );
}

function Method({ notes }: { notes: string[] }) {
  const rows: [string, string][] = [
    ["Average daily demand (μ) and variability (σ)", "From the recent sales window; days without sales count as zero demand."],
    ["Expected demand during lead time", "Sum of the latest forecast over the lead time L, or μ × L if no forecast exists."],
    ["Safety stock", "z × σ × √L, where z comes from the service level (95% → 1.645)."],
    ["Reorder point", "Expected lead-time demand + safety stock."],
    ["Recommended stock level", "Expected demand over lead time + review period, plus safety stock."],
    ["Recommended order", "Target level − current stock, ordered only at or below the reorder point; rounded up to the pack size and at least the MOQ."],
    ["Days of inventory", "Current stock ÷ expected daily demand."],
    ["Stock-out risk", "Probability that lead-time demand exceeds current stock (normal approximation)."],
    ["Status", "Critical: below safety stock or runs out before an order arrives · Low: at or below reorder point · Overstocked: more days of cover than the configured limit · Healthy: otherwise."],
  ];
  return (
    <div className="grid gap-5 lg:grid-cols-[1.5fr_1fr]">
      <Card><CardHeader><CardTitle>Calculations</CardTitle></CardHeader><CardContent>
        <dl className="divide-y">{rows.map(([t, d]) => <div key={t} className="py-2.5"><dt className="text-sm font-medium">{t}</dt><dd className="text-sm text-muted-foreground">{d}</dd></div>)}</dl>
      </CardContent></Card>
      <Card><CardHeader><CardTitle>Assumptions</CardTitle></CardHeader><CardContent>
        <ul className="space-y-2 text-sm text-muted-foreground">{notes.map((n) => <li key={n}>• {n}</li>)}</ul>
      </CardContent></Card>
    </div>
  );
}
