"""
Business insights engine.

Each insight separates three things clearly:
  * finding        - a statement backed by a number computed from the data
  * possible_causes - HYPOTHESES worth checking (never presented as fact);
                     where the data can support a hypothesis (e.g. low stock,
                     a price increase) we say so explicitly
  * recommendation - a suggested action

"Now" is the last date with sales data, so the analysis also works on
historical datasets.
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics import sales as sa
from app.inventory.optimizer import positions
from app.models import CalendarDay, Sale

WINDOW = 28


def _insight(kind, severity, title, finding, recommendation, metrics=None, causes=None, link=None):
    return {"category": kind, "severity": severity, "title": title, "finding": finding,
            "possible_causes": causes or [], "recommendation": recommendation, "metrics": metrics or {}, "link": link}


def _periods(db: Session):
    _, hi = sa.data_bounds(db)
    cur = sa.Filters(hi - timedelta(days=WINDOW - 1), hi)
    prev = sa.Filters(hi - timedelta(days=2 * WINDOW - 1), hi - timedelta(days=WINDOW))
    return cur, prev, hi


def _avg_price(db: Session, product_id: int, f: sa.Filters) -> float | None:
    v = db.scalar(select(func.sum(Sale.revenue) / func.nullif(func.sum(Sale.units), 0))
                  .where(Sale.product_id == product_id, Sale.date >= f.start, Sale.date <= f.end))
    return float(v) if v is not None else None


def generate(db: Session) -> dict:
    lo, hi = sa.data_bounds(db)
    if hi is None:
        return {"generated_for": None, "insights": [], "counts": {}}
    cur, prev, hi = _periods(db)
    out: list[dict] = []
    period = f"{cur.start:%d %b} – {cur.end:%d %b %Y}"

    # 1. overall trend
    tc, tp = sa._totals(db, cur), sa._totals(db, prev)
    ch = sa.pct_change(tc["revenue"], tp["revenue"])
    if ch is not None:
        out.append(_insight(
            "trend", "positive" if ch > 3 else "warning" if ch < -3 else "info",
            f"Revenue {'up' if ch >= 0 else 'down'} {abs(ch):.1f}% over the last {WINDOW} days",
            f"Revenue was ${tc['revenue']:,.0f} in {period} vs ${tp['revenue']:,.0f} in the previous {WINDOW} days.",
            "Review the product and store breakdown below to see which items drive the change.",
            {"current": round(tc["revenue"], 2), "previous": round(tp["revenue"], 2), "change_pct": ch}, link="/app/dashboard"))

    # inventory status (used as supporting evidence below)
    inv = positions(db)
    critical_by_product: dict[int, int] = {}
    for it in inv["items"]:
        if it["status"] in ("Critical", "Low Stock"):
            critical_by_product[it["product_id"]] = critical_by_product.get(it["product_id"], 0) + 1

    # 2/3. declining and growing products
    perf = sa.product_performance(db, cur)
    if not perf.empty:
        perf = perf[perf.prev_revenue > max(perf.prev_revenue.median() * 0.1, 50)]
        for r in perf.sort_values("change_pct").head(4).itertuples():
            if pd.isna(r.change_pct) or r.change_pct > -15:
                continue
            causes = []
            p_now, p_before = _avg_price(db, r.product_id, cur), _avg_price(db, r.product_id, prev)
            if p_now and p_before and p_now > p_before * 1.03:
                causes.append(f"Data: the average selling price rose {((p_now / p_before) - 1) * 100:.1f}% "
                              f"(${p_before:.2f} → ${p_now:.2f}) over the same period.")
            if critical_by_product.get(r.product_id):
                causes.append(f"Data: {critical_by_product[r.product_id]} store(s) currently hold low or critical stock "
                              "of this product, so availability may be limiting sales.")
            causes += ["Hypothesis: competitor pricing or a substitute product.",
                       "Hypothesis: lower promotional activity or a change in shelf placement."]
            out.append(_insight(
                "decline", "critical" if r.change_pct <= -30 else "warning",
                f"{r.name} sales fell {abs(r.change_pct):.0f}%",
                f"{r.name} ({r.sku}) generated ${r.revenue:,.0f} in the last {WINDOW} days vs ${r.prev_revenue:,.0f} "
                f"in the previous {WINDOW} days ({r.change_pct:+.1f}%).",
                "Review its pricing, availability and promotional activity; forecast its demand before the next order.",
                {"product_id": int(r.product_id), "change_pct": round(float(r.change_pct), 2),
                 "revenue": round(float(r.revenue), 2), "previous": round(float(r.prev_revenue), 2)},
                causes, link="/app/forecasting"))
        for r in perf.sort_values("change_pct", ascending=False).head(3).itertuples():
            if pd.isna(r.change_pct) or r.change_pct < 15:
                continue
            out.append(_insight(
                "growth", "positive", f"{r.name} is growing {r.change_pct:.0f}%",
                f"{r.name} revenue rose from ${r.prev_revenue:,.0f} to ${r.revenue:,.0f} ({r.change_pct:+.1f}%) "
                f"over the last {WINDOW} days.",
                "Growth opportunity: make sure stock keeps up with demand and consider featuring it in promotions.",
                {"product_id": int(r.product_id), "change_pct": round(float(r.change_pct), 2)},
                ["Hypothesis: rising customer demand or a successful promotion. Check the promotion calendar."],
                link="/app/inventory"))

    # 4. unusual daily changes (robust z-score against the trailing 28-day median)
    daily = sa.daily_revenue(db, sa.Filters(hi - timedelta(days=120), hi)).set_index("date")["revenue"]
    if len(daily) > 60:
        med = daily.shift(1).rolling(28).median()
        mad = (daily.shift(1) - med).abs().rolling(28).median() * 1.4826
        z = (daily - med) / mad.replace(0, np.nan)
        recent = z.iloc[-60:].dropna()
        events = {c.date: c.event_name_1 for c in db.scalars(
            select(CalendarDay).where(CalendarDay.date >= (hi - timedelta(days=60)), CalendarDay.event_name_1.is_not(None)))}
        anomalies = recent[recent.abs() > 3.5]
        for d, zv in anomalies.sort_values(key=np.abs, ascending=False).head(3).items():
            ev = events.get(d.date())
            out.append(_insight(
                "anomaly", "info" if ev else "warning",
                f"Unusual {'spike' if zv > 0 else 'drop'} in revenue on {d:%a %d %b %Y}",
                f"Revenue was ${daily[d]:,.0f} vs a typical ${med[d]:,.0f} for that period (robust z-score {zv:+.1f}).",
                "Check for data errors, store closures, promotions or local events on that day.",
                {"date": d.date().isoformat(), "revenue": round(float(daily[d]), 2), "baseline": round(float(med[d]), 2)},
                ([f"Data: this date is a calendar event ({ev})."] if ev else [])
                + ["Hypothesis: a promotion, a stock-out, weather or a data-entry issue."]))

    # 5. categories
    cats_now = {c["category"]: c for c in sa.by_category(db, cur)}
    cats_prev = {c["category"]: c for c in sa.by_category(db, prev)}
    if cats_now:
        growth = {k: sa.pct_change(v["revenue"], cats_prev.get(k, {}).get("revenue", 0)) for k, v in cats_now.items()}
        best = max(cats_now.values(), key=lambda c: c["revenue"])
        out.append(_insight(
            "category", "positive", f"{best['category'].title()} is the top category ({best['share_pct']:.0f}% of revenue)",
            f"{best['category'].title()} generated ${best['revenue']:,.0f} in the last {WINDOW} days"
            + (f", {growth[best['category']]:+.1f}% vs the previous period." if growth[best['category']] is not None else "."),
            "Protect availability in this category: it carries the largest share of revenue.",
            {"category_growth_pct": growth}, link="/app/dashboard"))
        fastest = max((k for k in growth if growth[k] is not None), key=lambda k: growth[k], default=None)
        if fastest and fastest != best["category"] and growth[fastest] > 5:
            out.append(_insight("category", "positive", f"{fastest.title()} is the fastest-growing category",
                                f"{fastest.title()} revenue changed {growth[fastest]:+.1f}% over the last {WINDOW} days.",
                                "Consider expanding range or space for this category.", {"growth_pct": growth[fastest]}))

    # 6. low-performing stores
    stores = sa.store_performance(db, cur)
    if len(stores) >= 3:
        med_rpd = float(np.median([s["revenue_per_day"] for s in stores]))
        for s in sorted(stores, key=lambda s: s["growth_pct"] if s["growth_pct"] is not None else 0)[:2]:
            weak_level = s["revenue_per_day"] < 0.75 * med_rpd
            weak_trend = s["growth_pct"] is not None and s["growth_pct"] < -5
            if not (weak_level or weak_trend):
                continue
            out.append(_insight(
                "store", "warning", f"Store {s['code']} ({s['name']}) is underperforming",
                f"{s['code']} averages ${s['revenue_per_day']:,.0f}/day vs a store median of ${med_rpd:,.0f}/day"
                + (f"; revenue changed {s['growth_pct']:+.1f}% vs the previous {WINDOW} days." if s["growth_pct"] is not None else "."),
                "Compare its product mix, stock availability and staffing with the best stores.",
                {"store_id": s["store_id"], "revenue_per_day": s["revenue_per_day"], "growth_pct": s["growth_pct"]},
                ["Hypothesis: a smaller store or catchment area (size is not in the data).",
                 "Hypothesis: local competition or availability problems."], link="/app/dashboard"))

    # 7. inventory shortages
    c = inv["summary"]["counts"]
    if c["Critical"] or c["Low Stock"]:
        worst = [i for i in inv["items"] if i["status"] == "Critical"][:3]
        out.append(_insight(
            "inventory", "critical" if c["Critical"] else "warning",
            f"{c['Critical']} critical and {c['Low Stock']} low-stock items",
            f"{c['Critical'] + c['Low Stock']} of {inv['summary']['total_items']} store-product items are at or below their "
            f"reorder point. Highest risk: " + "; ".join(f"{w['product_name']} @ {w['store_code']} "
                                                       f"({w['stockout_risk_pct']:.0f}% stock-out risk)" for w in worst) + ".",
            f"Place the recommended orders ({inv['summary']['units_to_order']:,} units, "
            f"${inv['summary']['recommended_order_value']:,.0f} at cost).",
            {"counts": c}, link="/app/inventory"))
    if c["Overstocked"]:
        out.append(_insight("inventory", "info", f"{c['Overstocked']} overstocked items",
                            f"{c['Overstocked']} items hold more than the configured days of cover.",
                            "Pause orders for these items; consider promotions or transfers between stores.",
                            {"overstocked": c["Overstocked"]}, link="/app/inventory"))

    # 8. seasonality: next month vs average
    if (hi - lo).days >= 365:
        months = sa.by_month(db, sa.Filters(lo, hi))
        vals = [m["avg_daily_revenue"] for m in months if m["avg_daily_revenue"]]
        nxt = (hi + timedelta(days=1)).month if (hi + timedelta(days=1)).month != hi.month else (hi.month % 12) + 1
        if vals:
            avg = float(np.mean(vals))
            v = months[nxt - 1]["avg_daily_revenue"]
            diff = (v / avg - 1) * 100 if avg else 0
            if abs(diff) >= 5:
                out.append(_insight(
                    "seasonality", "info", f"{sa.MONTHS[nxt - 1]} is historically {'busier' if diff > 0 else 'quieter'} than average",
                    f"Average daily revenue in {sa.MONTHS[nxt - 1]} has been {diff:+.1f}% vs the average month in the data "
                    f"({lo:%b %Y} – {hi:%b %Y}).",
                    "Adjust stock levels and staffing for the coming month; check forecasts for key products.",
                    {"month": sa.MONTHS[nxt - 1], "index_pct": round(diff, 1)},
                    ["Based on a limited number of past years; treat as an indication, not a certainty."],
                    link="/app/forecasting"))

    order = {"critical": 0, "warning": 1, "positive": 2, "info": 3}
    out.sort(key=lambda i: order[i["severity"]])
    counts = {k: sum(1 for i in out if i["severity"] == k) for k in order}
    return {"generated_for": {"start": cur.start, "end": cur.end, "comparison": {"start": prev.start, "end": prev.end}},
            "insights": out, "counts": counts}
