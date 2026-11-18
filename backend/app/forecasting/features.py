"""
Feature engineering for demand forecasting.

LEAKAGE RULE: a feature for day t may only use target values up to day t-1.
All lag / rolling features are therefore computed on the series shifted by
one day. Calendar, event and price features are allowed for day t because
they are known in advance (planned prices, holiday calendar).

The same definitions are used in two places, and they MUST match:
  * `build_training_frame` - vectorised pandas version for model training
  * `features_for_next_day` - single-row version used by the recursive
     multi-step forecast (predict t+1, append, predict t+2, ...)
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CalendarDay, Price, Sale, Store
from app.services.sample_data import SNAP_DAYS, build_events, wm_week_id

LAGS = (1, 7, 14, 28)
EVENT_TYPES = ("National", "Cultural", "Religious", "Sporting")

FEATURE_LABELS = {
    "lag_1": "Sales yesterday", "lag_7": "Sales same weekday last week", "lag_14": "Sales 2 weeks ago",
    "lag_28": "Sales 4 weeks ago", "roll_mean_7": "Average sales, last 7 days",
    "roll_mean_28": "Average sales, last 28 days", "roll_std_7": "Sales volatility, last 7 days",
    "dow": "Day of week", "is_weekend": "Weekend", "month": "Month", "day_of_month": "Day of month",
    "week_of_year": "Week of year", "is_event": "Holiday / special event", "event_tomorrow": "Event tomorrow (pre-holiday)",
    "event_National": "National holiday", "event_Cultural": "Cultural event", "event_Religious": "Religious event",
    "event_Sporting": "Sporting event", "snap": "SNAP benefit day", "price": "Selling price",
    "price_ratio": "Price vs. 4-week average", "is_promo": "Promotion (price cut)",
}
FEATURES = list(FEATURE_LABELS)


# ------------------------------------------------------------------ data access
def load_series(db: Session, product_id: int, store_id: int | None) -> pd.Series:
    """Daily units, continuous from the first sale to the last date in the warehouse (missing days = 0)."""
    stmt = select(Sale.date, func.sum(Sale.units)).where(Sale.product_id == product_id)
    if store_id is not None:
        stmt = stmt.where(Sale.store_id == store_id)
    rows = db.execute(stmt.group_by(Sale.date).order_by(Sale.date)).all()
    if not rows:
        return pd.Series(dtype=float)
    s = pd.Series({pd.Timestamp(d): float(u) for d, u in rows})
    last = db.scalar(select(func.max(Sale.date)))
    idx = pd.date_range(s.index.min(), pd.Timestamp(last), freq="D")
    return s.reindex(idx, fill_value=0.0).asfreq("D")


def _snap_states(db: Session, store_id: int | None) -> list[str]:
    if store_id is None:
        return ["CA", "TX", "WI"]
    st = db.get(Store, store_id)
    return [st.state] if st and st.state in ("CA", "TX", "WI") else []


def load_exog(db: Session, product_id: int, store_id: int | None, start: date, end: date) -> pd.DataFrame:
    """
    Calendar + price features for every day in [start, end] (may extend into the future).

    Documented assumptions for future dates that are not in the database:
      * holidays follow the standard US event calendar used by M5,
      * SNAP days follow the state's monthly pattern,
      * the price stays at the last known weekly price.
    """
    idx = pd.date_range(start, end, freq="D")
    df = pd.DataFrame(index=idx)
    cal = {c.date: c for c in db.scalars(select(CalendarDay).where(CalendarDay.date >= start, CalendarDay.date <= end)).all()}
    gen_events = build_events(sorted({d.year for d in idx} | {idx[-1].year + 1}))
    states = _snap_states(db, store_id)
    ev_type, snap = [], []
    for ts in idx:
        d = ts.date()
        c = cal.get(d)
        if c is not None:
            ev_type.append(c.event_type_1)
            flags = {"CA": c.snap_ca, "TX": c.snap_tx, "WI": c.snap_wi}
            snap.append(np.mean([flags[s] for s in states]) if states else 0.0)
        else:
            ev_type.append(gen_events.get(d, (None, None))[1])
            snap.append(np.mean([d.day in SNAP_DAYS[s] for s in states]) if states else 0.0)
    df["event_type"] = ev_type
    df["snap"] = snap

    # weekly price (mean over stores when forecasting the all-store total)
    pstmt = select(Price.wm_yr_wk, func.avg(Price.sell_price)).where(Price.product_id == product_id)
    if store_id is not None:
        pstmt = pstmt.where(Price.store_id == store_id)
    prices = dict(db.execute(pstmt.group_by(Price.wm_yr_wk)).all())
    wk = [wm_week_id(ts.date()) for ts in idx]
    price = pd.Series([prices.get(w, np.nan) for w in wk], index=idx, dtype=float)
    if price.isna().all() and prices:
        price[:] = prices[max(prices)]
    df["price"] = price.ffill().bfill()
    if df["price"].isna().all():  # no price information at all
        df["price"] = 0.0
    return df


# ------------------------------------------------------------------ feature builders
def _calendar_block(exog: pd.DataFrame) -> pd.DataFrame:
    idx = exog.index
    out = pd.DataFrame(index=idx)
    out["dow"] = idx.dayofweek
    out["is_weekend"] = (idx.dayofweek >= 5).astype(int)
    out["month"] = idx.month
    out["day_of_month"] = idx.day
    out["week_of_year"] = idx.isocalendar().week.astype(int).to_numpy()
    ev = exog["event_type"]
    out["is_event"] = ev.notna().astype(int)
    out["event_tomorrow"] = ev.shift(-1).notna().astype(int)
    for t in EVENT_TYPES:
        out[f"event_{t}"] = (ev == t).astype(int)
    out["snap"] = exog["snap"].astype(float)
    out["price"] = exog["price"].astype(float)
    ref = exog["price"].rolling(28, min_periods=1).mean()
    out["price_ratio"] = (exog["price"] / ref.replace(0, np.nan)).fillna(1.0)
    out["is_promo"] = (out["price_ratio"] < 0.95).astype(int)
    return out


def build_training_frame(y: pd.Series, cal: pd.DataFrame) -> pd.DataFrame:
    """
    Vectorised features for every day of `y` (rows without full lag history are dropped).
    `cal` is the output of `_calendar_block` covering at least the dates of `y`.
    """
    df = cal.loc[y.index].copy()
    shifted = y.shift(1)
    for k in LAGS:
        df[f"lag_{k}"] = y.shift(k)
    df["roll_mean_7"] = shifted.rolling(7).mean()
    df["roll_mean_28"] = shifted.rolling(28).mean()
    df["roll_std_7"] = shifted.rolling(7).std()
    df["target"] = y
    return df.dropna()[FEATURES + ["target"]]


def features_for_next_day(history: np.ndarray, cal_row: pd.Series) -> np.ndarray:
    """One feature row for the day after `history` ends (same definitions as above)."""
    h = history
    vals = {f"lag_{k}": h[-k] for k in LAGS}
    vals["roll_mean_7"] = h[-7:].mean()
    vals["roll_mean_28"] = h[-28:].mean()
    vals["roll_std_7"] = h[-7:].std(ddof=1)
    row = {**cal_row.to_dict(), **vals}
    return np.array([row[f] for f in FEATURES], dtype=float)


def future_calendar(db: Session, product_id: int, store_id: int | None, history_end: pd.Timestamp,
                    horizon: int) -> pd.DataFrame:
    start = (history_end - timedelta(days=40)).date()
    end = (history_end + timedelta(days=horizon + 1)).date()
    exog = load_exog(db, product_id, store_id, start, end)
    cal = _calendar_block(exog)
    return cal.loc[history_end + timedelta(days=1): history_end + timedelta(days=horizon)]
