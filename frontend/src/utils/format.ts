/**
 * Number / date formatting helpers used everywhere in the UI.
 *
 * The currency comes from the admin setting (Settings -> General -> Currency) and is applied
 * with setCurrencyCode(). INR uses the Indian numbering system (₹1,23,45,678 and 1.2Cr / 3.4L).
 */
let currency = "USD";
let locale = "en-US";
let money0 = new Intl.NumberFormat(locale, { style: "currency", currency, maximumFractionDigits: 0 });
let money2 = new Intl.NumberFormat(locale, { style: "currency", currency, maximumFractionDigits: 2 });
let num = new Intl.NumberFormat(locale, { maximumFractionDigits: 1 });
let compact = new Intl.NumberFormat(locale, { notation: "compact", maximumFractionDigits: 1 });
let symbol = "$";

export function setCurrencyCode(code: string | undefined | null) {
  const next = (code || "USD").toUpperCase();
  if (next === currency) return;
  try {
    const loc = next === "INR" ? "en-IN" : "en-US";
    const m0 = new Intl.NumberFormat(loc, { style: "currency", currency: next, maximumFractionDigits: 0 });
    currency = next;
    locale = loc;
    money0 = m0;
    money2 = new Intl.NumberFormat(loc, { style: "currency", currency: next, maximumFractionDigits: 2 });
    num = new Intl.NumberFormat(loc, { maximumFractionDigits: 1 });
    compact = new Intl.NumberFormat(loc, { notation: "compact", maximumFractionDigits: 1 });
    symbol = m0.formatToParts(0).find((p) => p.type === "currency")?.value ?? next;
  } catch {
    /* unknown currency code - keep the previous one */
  }
}
export const currencyCode = () => currency;
export const currencySymbol = () => symbol;

export const fmtMoney = (v?: number | null, decimals = false) =>
  v === null || v === undefined || Number.isNaN(v) ? "–" : (decimals ? money2 : money0).format(v);
export const fmtMoneyCompact = (v?: number | null) =>
  v === null || v === undefined ? "–" : symbol + compact.format(v);
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
