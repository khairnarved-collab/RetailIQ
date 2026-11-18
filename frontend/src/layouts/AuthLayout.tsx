import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";

/** Split layout for login / sign-up / password pages. */
export default function AuthLayout({ title, subtitle, children, footer }: { title: string; subtitle?: string; children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="grid min-h-[100dvh] lg:grid-cols-2">
      <div className="flex flex-col px-5 py-6 sm:px-10">
        <div className="flex items-center justify-between">
          <Link to="/" aria-label="RetailIQ home"><Logo /></Link>
          <ThemeToggle />
        </div>
        <div className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-10">
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          {subtitle && <p className="mt-1.5 text-sm text-muted-foreground">{subtitle}</p>}
          <div className="mt-7">{children}</div>
          {footer && <div className="mt-6 text-center text-sm text-muted-foreground">{footer}</div>}
        </div>
      </div>
      <div className="relative hidden overflow-hidden bg-[#0b1220] lg:block">
        <div className="absolute inset-0 bg-grid opacity-[.07]" />
        <div className="absolute -right-24 -top-24 h-96 w-96 rounded-full bg-teal-500/30 blur-3xl" />
        <div className="absolute -bottom-32 left-10 h-96 w-96 rounded-full bg-sky-500/20 blur-3xl" />
        <div className="relative flex h-full flex-col justify-end p-12 text-white">
          <p className="text-3xl font-semibold leading-tight tracking-tight">Turn Retail Data Into<br />Smarter Decisions.</p>
          <p className="mt-4 max-w-md text-slate-300">Sales analytics, machine-learning demand forecasts and inventory recommendations, all calculated from your own data.</p>
          <div className="mt-8 grid max-w-md grid-cols-3 gap-3 text-sm">
            {[["5", "forecasting models"], ["RFM", "+ K-Means segments"], ["PDF·XLSX", "report exports"]].map(([a, b]) => (
              <div key={b} className="rounded-xl border border-white/10 bg-white/5 p-3">
                <p className="font-semibold">{a}</p><p className="text-xs text-slate-400">{b}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
