"""
Sales analytics - every number on the dashboard is computed here, from the
database, at request time. Nothing is hard-coded.

Approach: aggregation happens in SQL (GROUP BY in the database, which is
fast and portable between PostgreSQL and SQLite). Joining the `calendar`
table gives us weekday / month / year / fiscal week without database-specific
date functions. pandas is only used for light post-processing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import Select, and_, distinct, func, select
from sqlalchemy.orm import Session

from app.models import CalendarDay, Category, Product, Sale, Store

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@dataclass(frozen=True)
class Filters:
    start: date | None = None
    end: date | None = None
    store_ids: tuple[int, ...] = field(default_factory=tuple)
    category_ids: tuple[int, ...] = field(default_factory=tuple)
    product_ids: tuple[int, ...] = field(default_factory=tuple)

    def shifted(self, start: date, end: date) -> Filters:
        return Filters(start, end, self.store_ids, self.category_ids, self.product_ids)


def data_bounds(db: Session) -> tuple[date | None, date | None]:
    lo, hi = db.execute(select(func.min(Sale.date), func.max(Sale.date))).one()
    return lo, hi


def resolve(db: Session, f: Filters) -> Filters:
    """Fill missing dates with the full data range."""
    lo, hi = data_bounds(db)
    return Filters(f.start or lo, f.end or hi, f.store_ids, f.category_ids, f.product_ids)


def _apply(stmt: Select, f: Filters, need_product: bool = False) -> Select:
    """Add WHERE clauses for the filters (joins Product only when needed)."""
    conds = []
    if f.start:
        conds.append(Sale.date >= f.start)
    if f.end:
        conds.append(Sale.date <= f.end)
    if f.store_ids:
        conds.append(Sale.store_id.in_(f.store_ids))
    if f.product_ids:
        conds.append(Sale.product_id.in_(f.product_ids))
    if f.category_ids:
        if not need_product:
            stmt = stmt.join(Product, Product.id == Sale.product_id)
        conds.append(Product.category_id.in_(f.category_ids))
    return stmt.where(and_(*conds)) if conds else stmt


def _totals(db: Session, f: Filters) -> dict:
    stmt = _apply(select(func.coalesce(func.sum(Sale.revenue), 0), func.coalesce(func.sum(Sale.units), 0),
                         func.count(Sale.id), func.count(distinct(Sale.product_id)),
                         func.count(distinct(Sale.store_id)), func.count(distinct(Sale.date))), f)
    rev, units, tx, prods, stores, days = db.execute(stmt).one()
    return {"revenue": float(rev), "units": int(units), "transactions": int(tx), "products": int(prods),
            "stores": int(stores), "days": int(days)}


def pct_change(cur: float, prev: float) -> float | None:
    if prev in (0, None):
        return None
    return round((cur - prev) / prev * 100, 2)


def kpis(db: Session, f: Filters) -> dict:
    f = resolve(db, f)
    cur = _totals(db, f)
    period_days = (f.end - f.start).days + 1 if f.start and f.end else 0
    prev_f = f.shifted(f.start - timedelta(days=period_days), f.start - timedelta(days=1)) if period_days else f
    prev = _totals(db, prev_f) if period_days else None
    fc = forecast_revenue(db, f, horizon=30)
    return {
        "total_revenue": round(cur["revenue"], 2),
        "total_orders": cur["transactions"],
        "units_sold": cur["units"],
        "avg_order_value": round(cur["revenue"] / cur["transactions"], 2) if cur["transactions"] else 0.0,
        "total_products": cur["products"],
        "num_stores": cur["stores"],
        "revenue_growth_pct": pct_change(cur["revenue"], prev["revenue"]) if prev else None,
        "previous_period": {"start": prev_f.start, "end": prev_f.end, "revenue": round(prev["revenue"], 2)} if prev else None,
        "forecasted_revenue_30d": fc["total"] if fc else None,
        "forecast_method": fc["method"] if fc else None,
        "period": {"start": f.start, "end": f.end, "days": period_days},
        "definitions": {
            "total_orders": "Sales transactions = store × product × day records with units sold > 0. "
                            "The M5 data has no basket/receipt IDs, so true customer orders are not available.",
            "avg_order_value": "Total revenue ÷ sales transactions.",
            "revenue_growth_pct": "Revenue in the selected period vs. the immediately preceding period of equal length.",
            "forecasted_revenue_30d": "Holt-Winters exponential smoothing (weekly seasonality) fitted on daily revenue "
                                      "for the current filters, projected 30 days past the last date with data.",
        },
    }


def daily_revenue(db: Session, f: Filters) -> pd.DataFrame:
    stmt = _apply(select(Sale.date, func.sum(Sale.revenue).label("revenue"), func.sum(Sale.units).label("units"))
                  .group_by(Sale.date).order_by(Sale.date), f)
    df = pd.DataFrame(db.execute(stmt).all(), columns=["date", "revenue", "units"])
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    # re-insert days without sales so time series are continuous
    full = pd.date_range(f.start or df.date.min(), f.end or df.date.max(), freq="D")
    return df.set_index("date").reindex(full, fill_value=0).rename_axis("date").reset_index()


_FC_CACHE: dict = {}


def forecast_revenue(db: Session, f: Filters, horizon: int = 30) -> dict | None:
    """Short revenue projection used for the KPI card (cached per filter set)."""
    f_hist = Filters(None, f.end, f.store_ids, f.category_ids, f.product_ids)
    lo, hi = data_bounds(db)
    key = (f_hist, horizon, hi, _row_count(db))
    if key in _FC_CACHE:
        return _FC_CACHE[key]
    hist = daily_revenue(db, resolve(db, f_hist))
    if len(hist) < 28:
        return None
    y = hist.set_index("date")["revenue"].astype(float).iloc[-365:].asfreq("D", fill_value=0.0)
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        model = ExponentialSmoothing(y, trend="add", damped_trend=True, seasonal="add", seasonal_periods=7,
                                     initialization_method="estimated").fit()
        pred = np.clip(model.forecast(horizon).to_numpy(), 0, None)
        method = "Holt-Winters exponential smoothing"
    except Exception:  # noqa: BLE001 - fall back to a transparent baseline
        pred = np.repeat(y.iloc[-28:].mean(), horizon)
        method = "28-day moving average"
    start = y.index[-1] + pd.Timedelta(days=1)
    out = {"total": round(float(pred.sum()), 2), "method": method,
           "series": [{"date": (start + pd.Timedelta(days=i)).date().isoformat(), "revenue": round(float(v), 2)}
                      for i, v in enumerate(pred)]}
    if len(_FC_CACHE) > 256:
        _FC_CACHE.clear()
    _FC_CACHE[key] = out
    return out


def _row_count(db: Session) -> int:
    return int(db.scalar(select(func.count(Sale.id))) or 0)


def revenue_over_time(db: Session, f: Filters) -> dict:
    f = resolve(db, f)
    days = (f.end - f.start).days + 1 if f.start else 0
    if days > 120:  # weekly buckets keep long ranges readable
        stmt = _apply(select(func.min(Sale.date).label("date"), func.sum(Sale.revenue), func.sum(Sale.units))
                      .join(CalendarDay, CalendarDay.date == Sale.date)
                      .group_by(CalendarDay.wm_yr_wk).order_by(func.min(Sale.date)), f)
        gran = "week"
    else:
        stmt = _apply(select(Sale.date, func.sum(Sale.revenue), func.sum(Sale.units))
                      .group_by(Sale.date).order_by(Sale.date), f)
        gran = "day"
    rows = [{"date": d.isoformat(), "revenue": round(float(r), 2), "units": int(u)} for d, r, u in db.execute(stmt).all()]
    return {"granularity": gran, "points": rows}


def monthly_comparison(db: Session, f: Filters) -> dict:
    """Revenue per calendar month, one series per year (year-over-year comparison)."""
    f = resolve(db, f)
    stmt = _apply(select(CalendarDay.year, CalendarDay.month, func.sum(Sale.revenue), func.sum(Sale.units))
                  .join(CalendarDay, CalendarDay.date == Sale.date)
                  .group_by(CalendarDay.year, CalendarDay.month), f)
    rows = db.execute(stmt).all()
    years = sorted({r[0] for r in rows})
    data = []
    for m in range(1, 13):
        point = {"month": MONTHS[m - 1]}
        for y, mm, rev, _ in rows:
            if mm == m:
                point[str(y)] = round(float(rev), 2)
        data.append(point)
    return {"years": [str(y) for y in years], "points": data}


def by_category(db: Session, f: Filters) -> list[dict]:
    f = resolve(db, f)
    stmt = (select(Category.name, func.sum(Sale.revenue), func.sum(Sale.units))
            .select_from(Sale).join(Product, Product.id == Sale.product_id)
            .join(Category, Category.id == Product.category_id).group_by(Category.name)
            .order_by(func.sum(Sale.revenue).desc()))
    rows = db.execute(_apply(stmt, f, need_product=True)).all()
    total = sum(float(r[1]) for r in rows) or 1
    return [{"category": n, "revenue": round(float(r), 2), "units": int(u), "share_pct": round(float(r) / total * 100, 2)}
            for n, r, u in rows]


def product_performance(db: Session, f: Filters) -> pd.DataFrame:
    """Revenue/units per product in the period plus change vs the previous equal-length period."""
    f = resolve(db, f)

    def q(ff: Filters):
        stmt = (select(Product.id, Product.sku, Product.name, Category.name, func.sum(Sale.revenue), func.sum(Sale.units))
                .select_from(Sale).join(Product, Product.id == Sale.product_id)
                .join(Category, Category.id == Product.category_id)
                .group_by(Product.id, Product.sku, Product.name, Category.name))
        return pd.DataFrame(db.execute(_apply(stmt, ff, need_product=True)).all(),
                            columns=["product_id", "sku", "name", "category", "revenue", "units"])

    cur = q(f)
    if cur.empty:
        return cur
    days = (f.end - f.start).days + 1
    prev = q(f.shifted(f.start - timedelta(days=days), f.start - timedelta(days=1)))
    cur = cur.merge(prev[["product_id", "revenue", "units"]].rename(columns={"revenue": "prev_revenue", "units": "prev_units"}),
                    on="product_id", how="left").fillna({"prev_revenue": 0, "prev_units": 0})
    cur["change_pct"] = np.where(cur.prev_revenue > 0, (cur.revenue - cur.prev_revenue) / cur.prev_revenue.replace(0, np.nan) * 100, np.nan)
    return cur.sort_values("revenue", ascending=False).reset_index(drop=True)


def _records(df: pd.DataFrame) -> list[dict]:
    out = df.copy()
    for c in ("revenue", "prev_revenue"):
        if c in out:
            out[c] = out[c].astype(float).round(2)
    if "change_pct" in out:
        out["change_pct"] = out["change_pct"].astype(float).round(2)
    return out.astype(object).where(out.notna(), None).to_dict("records")


def top_products(db: Session, f: Filters, n: int = 10) -> list[dict]:
    return _records(product_performance(db, f).head(n))


def worst_products(db: Session, f: Filters, n: int = 10) -> list[dict]:
    df = product_performance(db, f)
    return _records(df.sort_values("revenue").head(n)) if not df.empty else []


def store_performance(db: Session, f: Filters) -> list[dict]:
    f = resolve(db, f)

    def q(ff: Filters):
        stmt = (select(Store.id, Store.code, Store.name, Store.state, func.sum(Sale.revenue), func.sum(Sale.units),
                       func.count(distinct(Sale.date)))
                .select_from(Sale).join(Store, Store.id == Sale.store_id)
                .group_by(Store.id, Store.code, Store.name, Store.state))
        return {r[0]: r for r in db.execute(_apply(stmt, ff)).all()}

    cur = q(f)
    days = (f.end - f.start).days + 1
    prev = q(f.shifted(f.start - timedelta(days=days), f.start - timedelta(days=1)))
    out = []
    for sid, (_, code, name, state, rev, units, ndays) in cur.items():
        p = prev.get(sid)
        out.append({"store_id": sid, "code": code, "name": name, "state": state,
                    "revenue": round(float(rev), 2), "units": int(units),
                    "revenue_per_day": round(float(rev) / max(ndays, 1), 2),
                    "growth_pct": pct_change(float(rev), float(p[4])) if p else None})
    return sorted(out, key=lambda r: r["revenue"], reverse=True)


def by_weekday(db: Session, f: Filters) -> list[dict]:
    """Average revenue per day for each weekday (totals would be biased by how many Mondays fall in the range)."""
    f = resolve(db, f)
    stmt = _apply(select(CalendarDay.weekday, func.sum(Sale.revenue), func.sum(Sale.units), func.count(distinct(Sale.date)))
                  .join(CalendarDay, CalendarDay.date == Sale.date).group_by(CalendarDay.weekday), f)
    d = {w: (float(r), int(u), int(n)) for w, r, u, n in db.execute(stmt).all()}
    return [{"weekday": w[:3], "weekday_full": w, "avg_revenue": round(d[w][0] / d[w][2], 2) if w in d else 0,
             "avg_units": round(d[w][1] / d[w][2], 1) if w in d else 0} for w in WEEKDAYS]


def by_month(db: Session, f: Filters) -> list[dict]:
    """Average revenue per day in each calendar month (seasonality view)."""
    f = resolve(db, f)
    stmt = _apply(select(CalendarDay.month, func.sum(Sale.revenue), func.sum(Sale.units), func.count(distinct(Sale.date)))
                  .join(CalendarDay, CalendarDay.date == Sale.date).group_by(CalendarDay.month), f)
    d = {m: (float(r), int(u), int(n)) for m, r, u, n in db.execute(stmt).all()}
    return [{"month": MONTHS[m - 1], "total_revenue": round(d[m][0], 2) if m in d else 0,
             "avg_daily_revenue": round(d[m][0] / d[m][2], 2) if m in d else 0} for m in range(1, 13)]


def revenue_distribution(db: Session, f: Filters, bins: int = 20) -> dict:
    """Histogram of daily revenue (store-level days) for the current filters."""
    f = resolve(db, f)
    stmt = _apply(select(Sale.date, Sale.store_id, func.sum(Sale.revenue)).group_by(Sale.date, Sale.store_id), f)
    vals = np.array([float(r[2]) for r in db.execute(stmt).all()])
    if len(vals) == 0:
        return {"bins": [], "stats": None}
    counts, edges = np.histogram(vals, bins=bins)
    return {
        "unit": "Daily revenue per store",
        "bins": [{"range": f"{edges[i]:,.0f}–{edges[i + 1]:,.0f}", "from": round(float(edges[i]), 2),
                  "to": round(float(edges[i + 1]), 2), "count": int(c)} for i, c in enumerate(counts)],
        "stats": {"mean": round(float(vals.mean()), 2), "median": round(float(np.median(vals)), 2),
                  "std": round(float(vals.std(ddof=1)) if len(vals) > 1 else 0.0, 2), "n": int(len(vals))},
    }


def demand_trends(db: Session, f: Filters, n_products: int = 5) -> dict:
    """Weekly units for the top-N products (or the filtered products)."""
    f = resolve(db, f)
    top = product_performance(db, f).head(n_products)
    if top.empty:
        return {"products": [], "points": []}
    ids = tuple(int(i) for i in top.product_id)
    ff = Filters(f.start, f.end, f.store_ids, f.category_ids, ids)
    stmt = _apply(select(CalendarDay.wm_yr_wk, func.min(Sale.date), Sale.product_id, func.sum(Sale.units))
                  .join(CalendarDay, CalendarDay.date == Sale.date)
                  .group_by(CalendarDay.wm_yr_wk, Sale.product_id), ff)
    df = pd.DataFrame(db.execute(stmt).all(), columns=["wk", "date", "pid", "units"])
    names = dict(zip(top.product_id, top.name, strict=True))
    week_start = df.groupby("wk")["date"].min()
    piv = df.pivot_table(index="wk", columns="pid", values="units", aggfunc="sum").fillna(0)
    piv = piv.iloc[1:-1] if len(piv) > 3 else piv  # drop partial first/last weeks
    points = [{"date": week_start[wk].isoformat(), **{names[p]: int(row[p]) for p in piv.columns}}
              for wk, row in piv.iterrows()]
    return {"products": [names[i] for i in ids], "points": points}


def dashboard(db: Session, f: Filters) -> dict:
    f = resolve(db, f)
    return {
        "filters": {"start": f.start, "end": f.end, "store_ids": f.store_ids, "category_ids": f.category_ids,
                    "product_ids": f.product_ids},
        "kpis": kpis(db, f),
        "revenue_over_time": revenue_over_time(db, f),
        "monthly_comparison": monthly_comparison(db, f),
        "by_category": by_category(db, f),
        "top_products": top_products(db, f),
        "worst_products": worst_products(db, f),
        "stores": store_performance(db, f),
        "by_weekday": by_weekday(db, f),
        "by_month": by_month(db, f),
        "revenue_distribution": revenue_distribution(db, f),
        "demand_trends": demand_trends(db, f),
    }
