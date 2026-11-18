/** Number / date formatting helpers used everywhere in the UI. */
const usd0 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const usd2 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
const num = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });
const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });

export const fmtMoney = (v?: number | null, decimals = false) =>
  v === null || v === undefined || Number.isNaN(v) ? "–" : (decimals ? usd2 : usd0).format(v);
export const fmtMoneyCompact = (v?: number | null) =>
  v === null || v === undefined ? "–" : "$" + compact.format(v);
export const fmtNum = (v?: number | null) => (v === null || v === undefined || Number.isNaN(v) ? "–" : num.format(v));
export const fmtCompact = (v?: number | null) => (v === null || v === undefined ? "–" : compact.format(v));
export const fmtPct = (v?: number | null, signed = true) =>
  v === null || v === undefined || Number.isNaN(v) ? "n/a" : `${signed && v > 0 ? "+" : ""}${v.toFixed(1)}%`;

export const fmtDate = (iso?: string | null, opts: Intl.DateTimeFormatOptions = { day: "2-digit", month: "short", year: "numeric" }) => {
  if (!iso) return "–";
  const d = new Date(iso.length === 10 ? iso + "T00:00:00" : iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-GB", opts);
};
export const fmtShortDate = (iso: string) => fmtDate(iso, { day: "2-digit", month: "short" });
export const fmtDateTime = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "–";

/** Shift an ISO date by N days. */
export const addDays = (iso: string, days: number) => {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
};
