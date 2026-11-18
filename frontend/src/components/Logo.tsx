import { useId } from "react";
import { cn } from "@/lib/utils";

/** RetailIQ logo: rising bars + a trend line ending in an "insight" spark. */
export function LogoMark({ className }: { className?: string }) {
  // unique gradient id per instance: a duplicate id inside a hidden element breaks the fill in Chrome/Safari
  const gid = `riq-g-${useId().replace(/:/g, "")}`;
  return (
    <svg viewBox="0 0 64 64" className={cn("h-8 w-8 shrink-0", className)} aria-hidden="true">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#14b8a6" />
          <stop offset="1" stopColor="#0f5f73" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="15" fill={`url(#${gid})`} />
      <rect x="14" y="34" width="8" height="16" rx="2.5" fill="#fff" fillOpacity=".55" />
      <rect x="28" y="26" width="8" height="24" rx="2.5" fill="#fff" fillOpacity=".8" />
      <rect x="42" y="18" width="8" height="32" rx="2.5" fill="#fff" />
      <path d="M13 27 L27 19 L35 22 L49 11" fill="none" stroke="#fde68a" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="49" cy="11" r="3.6" fill="#fde68a" />
    </svg>
  );
}

export function Logo({ className, compact = false }: { className?: string; compact?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <LogoMark />
      {!compact && (
        <span className="text-lg font-bold tracking-tight">
          Retail<span className="text-primary">IQ</span>
        </span>
      )}
    </span>
  );
}
