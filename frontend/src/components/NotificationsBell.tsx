import { Bell, CheckCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useApiMutation, useApiQuery } from "@/hooks/useApi";
import { api } from "@/services/api";
import type { Notification } from "@/services/types";
import { fmtDateTime } from "@/utils/format";
import { cn } from "@/lib/utils";

const DOT: Record<string, string> = { critical: "bg-critical", warning: "bg-warning", success: "bg-success", info: "bg-primary" };

export function NotificationsBell() {
  const { data = [] } = useApiQuery<Notification[]>(["notifications"], "/notifications", { refetchInterval: 60_000 });
  const navigate = useNavigate();
  const unread = data.filter((n) => !n.is_read).length;
  const readAll = useApiMutation(() => api.post("/notifications/read-all"), [["notifications"]]);
  const readOne = useApiMutation((id: number) => api.post(`/notifications/${id}/read`), [["notifications"]]);
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={`Notifications${unread ? ` (${unread} unread)` : ""}`} className="relative">
          <Bell />
          {unread > 0 && <span className="absolute right-1.5 top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-critical px-1 text-[10px] font-semibold text-white">{unread}</span>}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0">
        <div className="flex items-center justify-between border-b px-3 py-2.5">
          <p className="text-sm font-semibold">Notifications</p>
          <Button variant="ghost" size="sm" disabled={!unread} onClick={() => readAll.mutate(undefined)}><CheckCheck /> Mark all read</Button>
        </div>
        <div className="max-h-96 overflow-y-auto">
          {data.length === 0 && <p className="px-3 py-8 text-center text-sm text-muted-foreground">No notifications yet</p>}
          {data.map((n) => (
            <button key={n.id} type="button" onClick={() => { readOne.mutate(n.id); if (n.link) navigate(n.link); }}
              className={cn("flex w-full gap-2.5 border-b px-3 py-2.5 text-left last:border-0 hover:bg-muted/60", !n.is_read && "bg-accent/40")}>
              <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", DOT[n.level] ?? "bg-primary")} />
              <span className="min-w-0">
                <span className="block text-sm font-medium">{n.title}</span>
                <span className="line-clamp-2 block text-xs text-muted-foreground">{n.message}</span>
                <span className="mt-0.5 block text-[11px] text-muted-foreground">{fmtDateTime(n.created_at)}</span>
              </span>
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
