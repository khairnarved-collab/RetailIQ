"""
Load a *cleaned* uploaded dataset into the relational tables.

  customer_transactions -> customers + customer_transactions
  sales_long            -> stores / categories / products / calendar / sales

Uploaded sales are merged into the warehouse: existing rows with the same
(date, store, product) are replaced by the uploaded values.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import delete, insert, select, tuple_
from sqlalchemy.orm import Session

from app.models import (
    CalendarDay,
    Category,
    Customer,
    CustomerSegment,
    CustomerTransaction,
    Dataset,
    InventoryItem,
    Price,
    Product,
    Sale,
    Store,
)
from app.services.sample_data import wm_week_id

CHUNK = 20_000


def import_customer_transactions(db: Session, ds: Dataset, df: pd.DataFrame) -> int:
    # Replace anything previously imported from this dataset
    db.execute(delete(CustomerSegment).where(CustomerSegment.dataset_id == ds.id))
    db.execute(delete(CustomerTransaction).where(CustomerTransaction.dataset_id == ds.id))
    db.execute(delete(Customer).where(Customer.dataset_id == ds.id))
    db.flush()

    df = df.copy()
    df["customer_id"] = df["customer_id"].astype(str)
    df["order_id"] = df["order_id"].astype(str)
    cities = df.groupby("customer_id")["city"].first() if "city" in df.columns else pd.Series(dtype=object)
    cust_records = [{"dataset_id": ds.id, "external_id": cid,
                     "city": (None if pd.isna(cities.get(cid)) else str(cities.get(cid))) if len(cities) else None}
                    for cid in df["customer_id"].unique()]
    for i in range(0, len(cust_records), CHUNK):
        db.execute(insert(Customer), cust_records[i:i + CHUNK])
    db.flush()
    id_map = dict(db.execute(select(Customer.external_id, Customer.id).where(Customer.dataset_id == ds.id)).all())

    def opt(row, col, cast=str):
        if col not in df.columns:
            return None
        v = row[col]
        return None if pd.isna(v) else cast(v)

    tx = []
    for row in df.to_dict("records"):
        tx.append({
            "dataset_id": ds.id, "customer_id": id_map[row["customer_id"]], "order_id": row["order_id"],
            "order_date": pd.Timestamp(row["order_date"]).date(), "amount": float(row["amount"]),
            "quantity": opt(row, "quantity", lambda v: int(round(float(v)))),
            "category": opt(row, "category"), "store_ref": opt(row, "store"),
        })
    for i in range(0, len(tx), CHUNK):
        db.execute(insert(CustomerTransaction), tx[i:i + CHUNK])
    return len(tx)


def _ensure_calendar(db: Session, days: list[date]) -> None:
    existing = set(db.scalars(select(CalendarDay.date).where(CalendarDay.date.in_(days))).all())
    new = [{"date": d, "wm_yr_wk": wm_week_id(d), "weekday": d.strftime("%A"), "month": d.month,
            "year": d.year, "snap_ca": False, "snap_tx": False, "snap_wi": False}
           for d in days if d not in existing]
    if new:
        db.execute(insert(CalendarDay), new)


def import_sales_long(db: Session, ds: Dataset, df: pd.DataFrame) -> tuple[int, list[str]]:
    notes: list[str] = []
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["store"] = df["store"].astype(str)
    df["product"] = df["product"].astype(str)
    df["units"] = df["units"].round().astype(int)
    # aggregate in case the file has several lines per day/store/product
    agg = {"units": "sum"}
    if "price" in df.columns:
        agg["price"] = "mean"
    keep_first = [c for c in ("category", "product_name", "state") if c in df.columns]
    for c in keep_first:
        agg[c] = "first"
    df = df.groupby(["date", "store", "product"], as_index=False).agg(agg)

    # dimensions
    # categories present in the file (products without a category go to UNCATEGORISED, created on demand)
    default_cat = "UNCATEGORISED"
    cat_ids: dict[str, int] = {}
    present = set(df["category"].dropna().astype(str)) if "category" in df.columns else set()
    for cat in sorted(present):
        obj = db.scalar(select(Category).where(Category.name == cat))
        if obj is None:
            obj = Category(name=cat)
            db.add(obj)
            db.flush()
        cat_ids[cat] = obj.id

    store_ids: dict[str, int] = {}
    for code in df["store"].unique():
        obj = db.scalar(select(Store).where(Store.code == code))
        if obj is None:
            state = None
            if "state" in df.columns:
                st = df.loc[df.store == code, "state"].dropna()
                state = str(st.iloc[0]) if len(st) else None
            obj = Store(code=code, name=f"Store {code}", state=state)
            db.add(obj)
            db.flush()
        store_ids[code] = obj.id

    prod_ids: dict[str, int] = {}
    for sku, grp in df.groupby("product"):
        obj = db.scalar(select(Product).where(Product.sku == sku))
        if obj is None:
            cat = grp["category"].dropna().astype(str).iloc[0] if "category" in grp and grp["category"].notna().any() else default_cat
            name = grp["product_name"].dropna().astype(str).iloc[0] if "product_name" in grp and grp["product_name"].notna().any() else sku
            if cat not in cat_ids:
                c = db.scalar(select(Category).where(Category.name == cat)) or Category(name=cat)
                db.add(c)
                db.flush()
                cat_ids[cat] = c.id
            obj = Product(sku=sku, name=name, category_id=cat_ids[cat], department=None)
            db.add(obj)
            db.flush()
        prod_ids[sku] = obj.id

    _ensure_calendar(db, sorted(df["date"].unique()))

    df["store_id"] = df["store"].map(store_ids)
    df["product_id"] = df["product"].map(prod_ids)

    # price: uploaded price if present, else the weekly price already in the database
    if "price" not in df.columns:
        df["price"] = float("nan")
    missing = df["price"].isna()
    if missing.any():
        weeks = {d: wm_week_id(d) for d in df.loc[missing, "date"].unique()}
        df.loc[missing, "wk"] = df.loc[missing, "date"].map(weeks)
        rows = db.execute(select(Price.store_id, Price.product_id, Price.wm_yr_wk, Price.sell_price).where(
            Price.store_id.in_(list(store_ids.values())), Price.product_id.in_(list(prod_ids.values())))).all()
        lookup = {(s, p, w): pr for s, p, w, pr in rows}
        df.loc[missing, "price"] = [lookup.get((s, p, w)) for s, p, w in
                                    df.loc[missing, ["store_id", "product_id", "wk"]].itertuples(index=False)]
        still = int(df["price"].isna().sum())
        if still:
            notes.append(f"{still} row(s) have no price in the file or the database; their revenue is recorded as 0.")

    # replace overlapping facts
    keys = list(df[["date", "store_id", "product_id"]].itertuples(index=False, name=None))
    for i in range(0, len(keys), 1000):
        db.execute(delete(Sale).where(tuple_(Sale.date, Sale.store_id, Sale.product_id).in_(keys[i:i + 1000])))
    records = [{"date": d, "store_id": int(s), "product_id": int(p), "units": int(u),
                "unit_price": None if pd.isna(pr) else float(pr),
                "revenue": 0.0 if pd.isna(pr) else round(float(u) * float(pr), 2)}
               for d, s, p, u, pr in df[["date", "store_id", "product_id", "units", "price"]].itertuples(index=False)
               if u > 0]
    for i in range(0, len(records), CHUNK):
        db.execute(insert(Sale), records[i:i + CHUNK])
    zero = int((df["units"] == 0).sum())
    if zero:
        notes.append(f"{zero} row(s) with 0 units were not stored (zero days are implicit).")

    # Inventory: uploaded sales files contain no stock levels. Create an inventory record for every
    # new store x product so the Inventory module works, with an explicitly ASSUMED stock of
    # 14 days of recent demand (flagged "assumed" in the UI until the user enters real counts).
    db.flush()
    existing = set(db.execute(select(InventoryItem.store_id, InventoryItem.product_id)).all())
    last = df["date"].max()
    recent = df[df["date"] > last - pd.Timedelta(days=28)] if hasattr(last, "year") else df
    avg = recent.groupby(["store_id", "product_id"])["units"].sum() / 28
    last_price = df.dropna(subset=["price"]).sort_values("date").groupby(["store_id", "product_id"])["price"].last()
    new_inv = []
    for (sid, pid) in df[["store_id", "product_id"]].drop_duplicates().itertuples(index=False, name=None):
        if (sid, pid) in existing:
            continue
        lp = last_price.get((sid, pid))
        new_inv.append({"store_id": int(sid), "product_id": int(pid), "on_hand": int(round(float(avg.get((sid, pid), 0)) * 14)),
                        "on_hand_source": "assumed", "lead_time_days": 7, "review_period_days": 7, "service_level": 0.95,
                        "min_order_qty": 1, "pack_size": 1, "unit_cost": None if lp is None or pd.isna(lp) else round(float(lp) * 0.7, 2),
                        "order_cost": 25.0, "holding_cost_rate": 0.25, "replenishment_policy": "order_up_to"})
    if new_inv:
        db.execute(insert(InventoryItem), new_inv)
        notes.append(f"Created {len(new_inv)} inventory records with ASSUMED stock (14 days of recent demand). "
                     "Enter real stock counts in Inventory.")
    return len(records), notes
