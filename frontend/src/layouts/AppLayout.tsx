import { useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  BarChart3, Bot, Boxes, Database, FileText, Lightbulb, LineChart, LogOut, Menu, Microscope, Settings, User as UserIcon,
  Users, UsersRound,
} from "lucide-react";
import { Dialog, SheetContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { NotificationsBell } from "@/components/NotificationsBell";
import { useAuth } from "@/hooks/useAuth";
import { useApiQuery } from "@/hooks/useApi";
import { setCurrencyCode, currencyCode } from "@/utils/format";
import { cn } from "@/lib/utils";

interface NavItem { to: string; label: string; icon: ReactNode; admin?: boolean }
const NAV: { group: string; items: NavItem[] }[] = [
  { group: "Overview", items: [
    { to: "/app/dashboard", label: "Dashboard", icon: <BarChart3 /> },
    { to: "/app/insights", label: "Business Insights", icon: <Lightbulb /> },
    { to: "/app/assistant", label: "AI Assistant", icon: <Bot /> },
  ] },
  { group: "Analytics", items: [
    { to: "/app/eda", label: "Exploratory Analysis", icon: <Microscope /> },
    { to: "/app/customers", label: "Customer Intelligence", icon: <UsersRound /> },
  ] },
  { group: "Planning", items: [
    { to: "/app/forecasting", label: "Demand Forecasting", icon: <LineChart /> },
    { to: "/app/inventory", label: "Inventory Optimisation", icon: <Boxes /> },
  ] },
  { group: "Data", items: [
    { to: "/app/data", label: "Data Management", icon: <Database /> },
    { to: "/app/reports", label: "Reports", icon: <FileText /> },
  ] },
  { group: "Administration", items: [
    { to: "/app/admin/users", label: "Users", icon: <Users />, admin: true },
    { to: "/app/admin/settings", label: "Settings", icon: <Settings />, admin: true },
  ] },
];

function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const { user } = useAuth();
  return (
    <nav className="flex flex-col gap-5 px-3 py-4" aria-label="Main navigation">
      {NAV.map((g) => {
        const items = g.items.filter((i) => !i.admin || user?.role === "admin");
        if (!items.length) return null;
        return (
          <div key={g.group}>
            <p className="mb-1.5 px-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/80">{g.group}</p>
            <div className="flex flex-col gap-0.5">
              {items.map((i) => (
                <NavLink key={i.to} to={i.to} onClick={onNavigate}
                  className={({ isActive }) => cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors [&_svg]:size-[18px]",
                    isActive ? "bg-primary/10 text-primary" : "text-sidebar-foreground hover:bg-muted hover:text-foreground",
                  )}>
                  {i.icon}{i.label}
                </NavLink>
              ))}
            </div>
          </div>
        );
      })}
    </nav>
  );
}

export function initials(name?: string) {
  return (name ?? "?").split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase();
}

export default function AppLayout() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const loc = useLocation();
  // Apply the currency chosen in Settings before any page renders numbers
  const { data: appSettings } = useApiQuery<Record<string, Record<string, string | number>>>(["settings"], "/admin/settings", { staleTime: 5 * 60_000 });
  setCurrencyCode(appSettings?.general?.currency as string | undefined);
  const title = NAV.flatMap((g) => g.items).find((i) => loc.pathname.startsWith(i.to))?.label ?? "RetailIQ";

  return (
    <div className="flex min-h-[100dvh] w-full">
      {/* desktop sidebar */}
      <aside className="sticky top-0 hidden h-[100dvh] w-64 shrink-0 flex-col border-r bg-sidebar lg:flex">
        <div className="flex h-16 items-center border-b px-5"><Link to="/app/dashboard" aria-label="RetailIQ home"><Logo /></Link></div>
        <div className="flex-1 overflow-y-auto scrollbar-thin"><SidebarNav /></div>
        <div className="border-t p-3 text-[11px] leading-relaxed text-muted-foreground">Turn Retail Data Into Smarter Decisions.</div>
      </aside>

      {/* mobile drawer */}
      <Dialog open={open} onOpenChange={setOpen}>
        <SheetContent aria-describedby={undefined}>
          <DialogTitle className="sr-only">Navigation</DialogTitle>
          <div className="flex h-16 items-center border-b px-5"><Logo /></div>
          <div className="h-[calc(100%-4rem)] overflow-y-auto"><SidebarNav onNavigate={() => setOpen(false)} /></div>
        </SheetContent>
      </Dialog>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-2 border-b bg-background/85 px-3 backdrop-blur supports-[backdrop-filter]:bg-background/70 sm:px-5">
          <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open menu" onClick={() => setOpen(true)}><Menu /></Button>
          <Link to="/app/dashboard" className="lg:hidden" aria-label="RetailIQ home"><Logo compact /></Link>
          <p className="ml-1 truncate text-sm font-medium text-muted-foreground">{title}</p>
          <div className="ml-auto flex items-center gap-1">
            <ThemeToggle />
            <NotificationsBell />
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="ml-1 rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label="Account menu">
                  <Avatar><AvatarFallback>{initials(user?.full_name)}</AvatarFallback></Avatar>
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuLabel>
                  <span className="block truncate">{user?.full_name}</span>
                  <span className="block truncate text-xs font-normal text-muted-foreground">{user?.email} · {user?.role}</span>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => navigate("/app/profile")}><UserIcon /> Profile</DropdownMenuItem>
                {user?.role === "admin" && <DropdownMenuItem onClick={() => navigate("/app/admin/settings")}><Settings /> Settings</DropdownMenuItem>}
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => { logout(); navigate("/login"); }}><LogOut /> Log out</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1500px] flex-1 px-3 py-5 safe-bottom sm:px-5 lg:px-8 lg:py-7">
          <Outlet key={currencyCode()} />
        </main>
      </div>
    </div>
  );
}
