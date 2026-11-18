/**
 * Shared building blocks: page header, KPI card, loading / empty / error states,
 * status badges, the synthetic-data banner and a simple data table.
 */
import { useState, type ReactNode } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AlertCircle, AlertTriangle, CheckCircle2, CircleDot, FlaskConical, Inbox, Info, PackageX, RefreshCw, TrendingDown, TrendingUp } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { fmtPct } from "@/utils/format";

export function PageHeader({ title, description, actions, icon }: { title: string; description?: ReactNode; actions?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-col gap-3 sm:mb-6 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight sm:text-2xl">{icon}{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function KpiCard({ label, value, delta, hint, icon, loading, sub }: {
  label: string; value: ReactNode; delta?: number | null; hint?: string; icon?: ReactNode; loading?: boolean; sub?: ReactNode;
}) {
  const up = (delta ?? 0) >= 0;
  return (
    <Card className="relative overflow-hidden transition-shadow hover:shadow-md">
      <CardContent className="p-4 sm:p-5">
        <div className="flex items-start justify-between gap-2">
          <p className="text-xs font-medium text-muted-foreground sm:text-[13px]">
            {hint ? (
              <Tooltip>
                <TooltipTrigger className="cursor-help border-b border-dotted border-muted-foreground/50 text-left">{label}</TooltipTrigger>
                <TooltipContent>{hint}</TooltipContent>
              </Tooltip>
            ) : label}
          </p>
          {icon && <span className="rounded-lg bg-primary/10 p-1.5 text-primary [&_svg]:size-4">{icon}</span>}
        </div>
        {loading ? <Skeleton className="mt-2 h-7 w-24" /> : (
          <p className="tabular mt-1.5 truncate text-xl font-semibold tracking-tight sm:text-2xl">{value}</p>
        )}
        {delta !== undefined && !loading && (
          <p className={cn("mt-1 inline-flex items-center gap-1 text-xs font-medium", delta === null ? "text-muted-foreground" : up ? "text-success" : "text-critical")}>
            {delta !== null && (up ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />)}
            {delta === null ? "no comparison data" : `${fmtPct(delta)} vs prev. period`}
          </p>
        )}
        {sub && !loading && <p className="mt-1 truncate text-xs text-muted-foreground">{sub}</p>}
      </CardContent>
    </Card>
  );
}

export function LoadingState({ rows = 3, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-3", className)} aria-busy="true" aria-live="polite">
      {Array.from({ length: rows }).map((_, i) => <Skeleton key={i} className="h-24 w-full rounded-xl" />)}
      <span className="sr-only">Loading…</span>
    </div>
  );
}

export function ChartSkeleton({ height = 280 }: { height?: number }) {
  return <Skeleton className="w-full rounded-lg" style={{ height }} />;
}

export function EmptyState({ title, description, action, icon }: { title: string; description?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed px-6 py-12 text-center">
      <div className="mb-3 rounded-full bg-muted p-3 text-muted-foreground [&_svg]:size-6">{icon ?? <Inbox />}</div>
      <h3 className="font-semibold">{title}</h3>
      {description && <p className="mt-1 max-w-md text-sm text-muted-foreground">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const msg = error instanceof Error ? error.message : "Something went wrong";
  return (
    <div role="alert" className="flex flex-col items-center gap-3 rounded-xl border border-critical/30 bg-critical/5 px-6 py-10 text-center">
      <AlertCircle className="h-7 w-7 text-critical" />
      <div>
        <p className="font-semibold">Could not load this data</p>
        <p className="mt-1 text-sm text-muted-foreground">{msg}</p>
      </div>
      {onRetry && <Button variant="outline" size="sm" onClick={onRetry}><RefreshCw /> Try again</Button>}
    </div>
  );
}

export function SyntheticBanner({ show, text }: { show: boolean; text?: string }) {
  if (!show) return null;
  return (
    <div className="mb-4 flex items-start gap-2.5 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2.5 text-xs text-foreground sm:text-sm">
      <FlaskConical className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
      <span>{text ?? <>You are viewing <b>synthetic demonstration data</b> in M5 format. It is not real Walmart data; upload your own data or load the real M5 files to analyse a real business.</>}</span>
    </div>
  );
}

const STATUS: Record<string, { variant: "critical" | "warning" | "success" | "secondary"; icon: ReactNode }> = {
  Critical: { variant: "critical", icon: <PackageX /> },
  "Low Stock": { variant: "warning", icon: <AlertTriangle /> },
  Overstocked: { variant: "secondary", icon: <CircleDot /> },
  Healthy: { variant: "success", icon: <CheckCircle2 /> },
};
/** Status always ships with an icon + label (never colour alone). */
export function StatusBadge({ status }: { status: string }) {
  const s = STATUS[status] ?? { variant: "secondary" as const, icon: <Info /> };
  return <Badge variant={s.variant}>{s.icon}{status}</Badge>;
}

export function ChartCard({ title, description, children, actions, className, footer }: {
  title: string; description?: ReactNode; children: ReactNode; actions?: ReactNode; className?: string; footer?: ReactNode;
}) {
  return (
    <Card className={cn("min-w-0", className)}>
      <CardHeader className="flex-row items-start justify-between gap-2 space-y-0 pb-2">
        <div className="min-w-0">
          <CardTitle>{title}</CardTitle>
          {description && <CardDescription className="mt-1">{description}</CardDescription>}
        </div>
        {actions}
      </CardHeader>
      <CardContent>{children}</CardContent>
      {footer && <div className="border-t px-4 py-2.5 text-xs text-muted-foreground sm:px-5">{footer}</div>}
    </Card>
  );
}

export function SimpleTable({ columns, rows, align, maxHeight }: {
  columns: string[]; rows: ReactNode[][]; align?: ("left" | "right")[]; maxHeight?: number;
}) {
  return (
    <div style={maxHeight ? { maxHeight, overflowY: "auto" } : undefined} className="scrollbar-thin rounded-lg border">
      <Table>
        <TableHeader className="sticky top-0 z-10 bg-card">
          <TableRow>{columns.map((c, i) => <TableHead key={c + i} className={align?.[i] === "right" ? "text-right" : ""}>{c}</TableHead>)}</TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r, i) => (
            <TableRow key={i}>
              {r.map((cell, j) => <TableCell key={j} className={cn("whitespace-nowrap", align?.[j] === "right" && "tabular text-right")}>{cell}</TableCell>)}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

/** Button that asks for confirmation in a dialog before running a destructive action. */
export function ConfirmButton({ children, title, description, onConfirm, confirmLabel = "Delete", ...btn }: {
  children: ReactNode; title: string; description?: ReactNode; onConfirm: () => void; confirmLabel?: string;
} & React.ComponentProps<typeof Button>) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button {...btn} onClick={() => setOpen(true)}>{children}</Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>{title}</DialogTitle>{description && <DialogDescription>{description}</DialogDescription>}</DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="destructive" onClick={() => { setOpen(false); onConfirm(); }}>{confirmLabel}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
