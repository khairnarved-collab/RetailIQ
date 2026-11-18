"""
Inventory optimisation.

For every store × product we combine the current stock position with the
demand forecast (or recent demand) to produce replenishment advice.

Notation
    μ   average daily demand    (last `demand_window_days` days, zero-sales days included)
    σ   std-dev of daily demand (same window)
    L   supplier lead time (days)
    R   review period (days between stock reviews / orders)
    z   service-level factor, z = Φ⁻¹(service level)   e.g. 95% -> 1.645

Formulas (classic textbook inventory theory, normal-demand approximation)
    Expected demand during lead time   D_L = Σ forecast over the next L days  (or μ·L)
    Safety stock                        SS  = z · σ · √L
    Reorder point                       ROP = D_L + SS
    Recommended stock level (target)    S   = expected demand over (L + R) + SS
    Recommended order                   Q   = S − on_hand   when on_hand ≤ ROP, else 0
                                              (rounded up to the pack size, at least the MOQ;
                                               with the "eoq" policy, at least the EOQ)
    Economic order quantity             EOQ = √(2 · annual demand · order cost / (unit cost · holding rate))
    Days of inventory remaining         on_hand / μ
    Stock-out risk                      P(lead-time demand > on_hand) = 1 − Φ((on_hand − D_L) / (σ·√L))

Status rules
    Critical     on_hand ≤ SS, or stock runs out before a new order could arrive (days left < L)
    Low Stock    on_hand ≤ ROP
    Overstocked  days of inventory > `overstock_days_of_cover`
    Healthy      otherwise

Assumptions: daily demand is roughly normal and independent day to day,
lead time is fixed, and the latest forecast (if any) is used for the
expected demand. All of these are shown in the UI next to the numbers.
"""
from __future__ import annotations

import math
from datetime import timedelta

import numpy as np
import pandas as pd
from scipy.stats import norm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Category,
    Forecast,
    ForecastRun,
    InventoryItem,
    Product,
    Sale,
    Store,
    Supplier,
)
from app.services import app_settings

STATUS_ORDER = {"Critical": 0, "Low Stock": 1, "Overstocked": 2, "Healthy": 3}


def _demand_stats(db: Session, window: int, store_ids=None, product_ids=None) -> pd.DataFrame:
    last = db.scalar(select(func.max(Sale.date)))
    if last is None:
        return pd.DataFrame(columns=["store_id", "product_id", "mu", "sigma"])
    start = last - timedelta(days=window - 1)
    stmt = select(Sale.store_id, Sale.product_id, Sale.date, Sale.units).where(Sale.date >= start)
    if store_ids:
        stmt = stmt.where(Sale.store_id.in_(store_ids))
    if product_ids:
        stmt = stmt.where(Sale.product_id.in_(product_ids))
    df = pd.DataFrame(db.execute(stmt).all(), columns=["store_id", "product_id", "date", "units"])
    if df.empty:
        return pd.DataFrame(columns=["store_id", "product_id", "mu", "sigma"])
    # sum over the window / window length => zero days count as zero demand
    g = df.groupby(["store_id", "product_id"])["units"]
    total = g.sum()
    sumsq = df.assign(sq=df.units ** 2).groupby(["store_id", "product_id"])["sq"].sum()
    mu = total / window
    var = (sumsq - window * mu ** 2) / (window - 1)
    out = pd.DataFrame({"mu": mu, "sigma": np.sqrt(var.clip(lower=0))}).reset_index()
    return out


def _latest_forecasts(db: Session) -> dict[tuple[int, int], list[float]]:
    """Most recent forecast run per (store, product) -> list of daily predicted units."""
    sub = (select(ForecastRun.store_id, ForecastRun.product_id, func.max(ForecastRun.id).label("rid"))
           .where(ForecastRun.store_id.is_not(None)).group_by(ForecastRun.store_id, ForecastRun.product_id).subquery())
    rows = db.execute(select(sub.c.store_id, sub.c.product_id, Forecast.date, Forecast.predicted_units)
                      .join(Forecast, Forecast.run_id == sub.c.rid).order_by(Forecast.date)).all()
    out: dict[tuple[int, int], list[float]] = {}
    for s, p, _, v in rows:
        out.setdefault((s, p), []).append(float(v))
    return out


def compute_position(item: dict, mu: float, sigma: float, forecast: list[float] | None, overstock_days: int) -> dict:
    """Pure function (easy to unit-test): all replenishment numbers for one item."""
    L = max(int(item["lead_time_days"]), 1)
    R = max(int(item["review_period_days"]), 0)
    sl = float(item["service_level"])
    on_hand = int(item["on_hand"])
    z = float(norm.ppf(sl))

    if forecast and len(forecast) >= L + R:
        d_L = float(sum(forecast[:L]))
        d_LR = float(sum(forecast[:L + R]))
        demand_source = "forecast"
        daily_expected = d_LR / max(L + R, 1)
    else:
        d_L, d_LR = mu * L, mu * (L + R)
        demand_source = "recent average"
        daily_expected = mu
    ss = z * sigma * math.sqrt(L)
    rop = d_L + ss
    target = d_LR + ss
    days_left = on_hand / daily_expected if daily_expected > 0 else math.inf

    if sigma > 0:
        risk = float(1 - norm.cdf((on_hand - d_L) / (sigma * math.sqrt(L))))
    else:
        risk = 1.0 if on_hand < d_L else 0.0

    annual = daily_expected * 365
    uc, hr, oc = item.get("unit_cost"), item.get("holding_cost_rate") or 0.25, item.get("order_cost") or 25.0
    eoq = math.sqrt(2 * annual * oc / (uc * hr)) if uc and uc > 0 and annual > 0 else None

    order = 0.0
    if on_hand <= rop:
        order = max(target - on_hand, 0)
        if item.get("replenishment_policy") == "eoq" and eoq:
            order = max(order, eoq)
        pack = max(int(item.get("pack_size") or 1), 1)
        order = math.ceil(order / pack) * pack
        order = max(order, int(item.get("min_order_qty") or 1)) if order > 0 else 0

    if daily_expected == 0 and on_hand > 0:
        status = "Overstocked"
    elif on_hand <= ss or days_left < L:
        status = "Critical"
    elif on_hand <= rop:
        status = "Low Stock"
    elif days_left > overstock_days:
        status = "Overstocked"
    else:
        status = "Healthy"

    name = item.get("product_name", "This product")
    if order > 0:
        rec = (f"Restock {int(order)} units: current stock {on_hand} vs. expected demand of {d_LR:.0f} units over the "
               f"next {L + R} days (lead time {L} + review {R}), plus {ss:.0f} units of safety stock for a "
               f"{sl:.0%} service level.")
    elif status == "Overstocked":
        excess = on_hand - target
        rec = (f"Overstocked: {on_hand} units cover about {days_left:.0f} days of demand"
               if math.isfinite(days_left) else f"No recent demand for {name} but {on_hand} units in stock")
        rec += f" ({max(excess, 0):.0f} above the recommended level). Pause orders; consider a promotion or transfer."
    else:
        rec = f"No order needed: stock is above the reorder point ({rop:.0f} units)."

    return {
        "avg_daily_demand": round(mu, 2), "demand_std": round(sigma, 2), "demand_source": demand_source,
        "expected_demand_lead_time": round(d_L, 1), "expected_demand_cycle": round(d_LR, 1),
        "safety_stock": round(ss, 1), "reorder_point": round(rop, 1), "recommended_stock_level": round(target, 1),
        "recommended_order_qty": int(order), "eoq": round(eoq, 1) if eoq else None,
        "days_of_inventory": round(days_left, 1) if math.isfinite(days_left) else None,
        "stockout_risk_pct": round(risk * 100, 1), "status": status, "recommendation": rec, "z": round(z, 3),
    }


def positions(db: Session, store_id: int | None = None, category_id: int | None = None,
              status: str | None = None, search: str | None = None) -> dict:
    cfg = app_settings.get_section(db, "inventory")
    stmt = (select(InventoryItem, Product, Store, Category, Supplier)
            .join(Product, Product.id == InventoryItem.product_id).join(Store, Store.id == InventoryItem.store_id)
            .join(Category, Category.id == Product.category_id)
            .outerjoin(Supplier, Supplier.id == InventoryItem.supplier_id))
    if store_id:
        stmt = stmt.where(InventoryItem.store_id == store_id)
    if category_id:
        stmt = stmt.where(Product.category_id == category_id)
    rows = db.execute(stmt).all()
    stats = _demand_stats(db, int(cfg["demand_window_days"]), [store_id] if store_id else None)
    stat_map = {(r.store_id, r.product_id): (r.mu, r.sigma) for r in stats.itertuples()}
    fc = _latest_forecasts(db)
    items = []
    for inv, prod, store, cat, sup in rows:
        mu, sigma = stat_map.get((inv.store_id, inv.product_id), (0.0, 0.0))
        base = {
            "id": inv.id, "store_id": store.id, "store_code": store.code, "store_name": store.name,
            "product_id": prod.id, "sku": prod.sku, "product_name": prod.name, "category": cat.name,
            "supplier_id": sup.id if sup else None, "supplier": sup.name if sup else None,
            "on_hand": inv.on_hand, "on_hand_source": inv.on_hand_source, "lead_time_days": inv.lead_time_days,
            "review_period_days": inv.review_period_days, "service_level": inv.service_level,
            "min_order_qty": inv.min_order_qty, "pack_size": inv.pack_size, "unit_cost": inv.unit_cost,
            "order_cost": inv.order_cost, "holding_cost_rate": inv.holding_cost_rate,
            "replenishment_policy": inv.replenishment_policy,
        }
        pos = compute_position(base, float(mu), float(sigma), fc.get((store.id, prod.id)), int(cfg["overstock_days_of_cover"]))
        items.append({**base, **pos, "stock_value": round(inv.on_hand * (inv.unit_cost or 0), 2),
                      "order_value": round(pos["recommended_order_qty"] * (inv.unit_cost or 0), 2)})
    if search:
        s = search.lower()
        items = [i for i in items if s in i["product_name"].lower() or s in i["sku"].lower()]
    counts = {k: 0 for k in STATUS_ORDER}
    for i in items:
        counts[i["status"]] += 1
    if status:
        items = [i for i in items if i["status"] == status]
    items.sort(key=lambda i: (STATUS_ORDER[i["status"]], -i["stockout_risk_pct"]))
    return {
        "items": items,
        "summary": {
            "counts": counts, "total_items": sum(counts.values()),
            "stock_value": round(sum(i["stock_value"] for i in items), 2),
            "recommended_order_value": round(sum(i["order_value"] for i in items), 2),
            "units_to_order": int(sum(i["recommended_order_qty"] for i in items)),
        },
        "assumptions": {
            "demand_window_days": cfg["demand_window_days"],
            "overstock_days_of_cover": cfg["overstock_days_of_cover"],
            "notes": [
                "Average demand and variability use the last "
                f"{cfg['demand_window_days']} days of sales, counting days without sales as zero demand.",
                "When a forecast exists for the store and product, expected demand comes from the latest forecast.",
                "Safety stock assumes roughly normal, independent daily demand and a fixed supplier lead time.",
                "Items marked 'synthetic' or 'assumed' do not have real stock counts. Update them to get real advice.",
            ],
        },
    }
