import { useMemo, useState } from "react";
import { Check, ChevronDown, X } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export interface Option { value: number; label: string; hint?: string }

/** Searchable multi-select used by the dashboard filters. */
export function MultiSelect({ options, value, onChange, placeholder, className }: {
  options: Option[]; value: number[]; onChange: (v: number[]) => void; placeholder: string; className?: string;
}) {
  const [q, setQ] = useState("");
  const filtered = useMemo(() => options.filter((o) => (o.label + " " + (o.hint ?? "")).toLowerCase().includes(q.toLowerCase())), [options, q]);
  const toggle = (v: number) => onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v]);
  const label = value.length === 0 ? placeholder : value.length === 1 ? options.find((o) => o.value === value[0])?.label ?? "1 selected" : `${value.length} selected`;
  return (
    <Popover>
      <PopoverTrigger className={cn("flex h-10 w-full items-center justify-between gap-2 rounded-lg border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring", className)}>
        <span className={cn("truncate", value.length === 0 && "text-muted-foreground")}>{label}</span>
        <span className="flex items-center gap-1">
          {value.length > 0 && (
            <span role="button" tabIndex={0} aria-label="Clear selection" className="rounded p-0.5 hover:bg-muted"
              onClick={(e) => { e.stopPropagation(); onChange([]); }} onKeyDown={(e) => { if (e.key === "Enter") { e.stopPropagation(); onChange([]); } }}>
              <X className="h-3.5 w-3.5" />
            </span>
          )}
          <ChevronDown className="h-4 w-4 opacity-50" />
        </span>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] min-w-[16rem] p-2">
        <Input autoFocus placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} className="mb-2 h-9" />
        <div className="max-h-64 overflow-y-auto scrollbar-thin">
          {filtered.length === 0 && <p className="px-2 py-3 text-center text-sm text-muted-foreground">No matches</p>}
          {filtered.map((o) => {
            const on = value.includes(o.value);
            return (
              <button key={o.value} type="button" onClick={() => toggle(o.value)}
                className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm hover:bg-accent">
                <span className={cn("flex h-4 w-4 shrink-0 items-center justify-center rounded border", on ? "border-primary bg-primary text-primary-foreground" : "border-input")}>
                  {on && <Check className="h-3 w-3" />}
                </span>
                <span className="truncate">{o.label}</span>
                {o.hint && <span className="ml-auto shrink-0 text-xs text-muted-foreground">{o.hint}</span>}
              </button>
            );
          })}
        </div>
      </PopoverContent>
    </Popover>
  );
}
