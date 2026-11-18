"""
M5 dataset ingestion pipeline.

Maps the M5 Forecasting files into RetailIQ's relational schema:

    calendar.csv                 -> calendar
    sales_train_*.csv (wide)     -> categories, products, stores, sales
    sell_prices.csv              -> prices (+ revenue = units x weekly price)
    optional extras (synthetic demo only): item_names.csv, stores.csv,
    suppliers_synthetic.csv, inventory_synthetic.csv

Works with the real Kaggle files (https://www.kaggle.com/competitions/m5-forecasting-accuracy/data)
and with the bundled synthetic files, which use the same format.

The real M5 data has 30,490 series x 1,941 days (~59M cells), far too much
for a laptop demo, so the loader can take a subset:

    python -m app.services.m5_ingestion --data-dir ../data/m5 \
        --stores CA_1,TX_1,WI_1 --max-items 50 --start-date 2015-01-01

Design notes
  * The wide table is "melted" to long format (one row per store x item x day).
  * Only rows with units > 0 are stored; zero days are restored when building
    a time series (saves ~70% of rows for M5, which is very sparse).
  * Re-running is idempotent: existing sales/prices for the loaded
    store x product pairs are replaced, dimension rows are upserted.
  * M5 has NO customer data and NO stock levels. Customer tables are never
    touched. If no inventory file is supplied, stock is initialised as an
    explicitly *assumed* 14 days of cover, flagged on_hand_source="assumed".
"""
from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.models import (
    CalendarDay,
    Category,
    Dataset,
    InventoryItem,
    Price,
    Product,
    Sale,
    Store,
    Supplier,
)

log = logging.getLogger(__name__)
CHUNK = 20_000


@dataclass
class IngestOptions:
    data_dir: Path
    stores: list[str] | None = None
    max_items: int | None = None
    items: list[str] | None = None
    start_date: str | None = None
    end_date: str | None = None
    seed: int = 0


@dataclass
class IngestResult:
    stores: int = 0
    products: int = 0
    calendar_days: int = 0
    sales_rows: int = 0
    price_rows: int = 0
    inventory_rows: int = 0
    synthetic: bool = False
    notes: list[str] = field(default_factory=list)


def _find_sales_file(data_dir: Path) -> Path:
    for name in ("sales_train_evaluation.csv", "sales_train_validation.csv", "sales_train_synthetic.csv"):
        if (data_dir / name).exists():
            return data_dir / name
    raise FileNotFoundError(f"No sales_train_*.csv found in {data_dir}")


def _bulk_insert(db: Session, model, records: list[dict]) -> None:
    for i in range(0, len(records), CHUNK):
        db.execute(insert(model), records[i:i + CHUNK])


def load_m5(db: Session, opts: IngestOptions, uploaded_by: int | None = None) -> IngestResult:
    d = Path(opts.data_dir)
    res = IngestResult()
    info_file = d / "DATASET_INFO.json"
    res.synthetic = info_file.exists() and json.loads(info_file.read_text()).get("synthetic", False)

    # ------------------------------------------------------------ 1. calendar
    cal = pd.read_csv(d / "calendar.csv", parse_dates=["date"])
    if opts.start_date:
        cal = cal[cal.date >= pd.Timestamp(opts.start_date)]
    if opts.end_date:
        cal = cal[cal.date <= pd.Timestamp(opts.end_date)]
    day_cols = cal["d"].tolist()

    # ------------------------------------------------------------ 2. sales (wide -> long)
    sales_path = _find_sales_file(d)
    id_cols = ["id", "item_id", "dept_id", "cat_id", "store_id", "state_id"]
    header = pd.read_csv(sales_path, nrows=0).columns
    usecols = id_cols + [c for c in day_cols if c in header]
    wide = pd.read_csv(sales_path, usecols=usecols)
    if opts.stores:
        wide = wide[wide.store_id.isin(opts.stores)]
    if opts.items:
        wide = wide[wide.item_id.isin(opts.items)]
    if opts.max_items:
        rng = np.random.default_rng(opts.seed)
        all_items = np.sort(wide.item_id.unique())
        keep = rng.choice(all_items, size=min(opts.max_items, len(all_items)), replace=False)
        wide = wide[wide.item_id.isin(keep)]
    if wide.empty:
        raise ValueError("The selected filters leave no sales series to import")

    long = wide.melt(id_vars=id_cols, var_name="d", value_name="units")
    long = long[long.units > 0]
    long = long.merge(cal[["d", "date", "wm_yr_wk"]], on="d", how="inner")

    # ------------------------------------------------------------ 3. prices
    prices = pd.read_csv(d / "sell_prices.csv")
    prices = prices[prices.store_id.isin(wide.store_id.unique()) & prices.item_id.isin(wide.item_id.unique())
                    & prices.wm_yr_wk.isin(cal.wm_yr_wk.unique())]
    long = long.merge(prices, on=["store_id", "item_id", "wm_yr_wk"], how="left")
    missing_price = int(long.sell_price.isna().sum())
    if missing_price:
        res.notes.append(f"{missing_price} sales rows had no weekly price; revenue for them is set to 0.")

    # ------------------------------------------------------------ 4. dimensions (upsert)
    names = {}
    if (d / "item_names.csv").exists():
        names = pd.read_csv(d / "item_names.csv").set_index("item_id")["item_name"].to_dict()
    store_names = {}
    if (d / "stores.csv").exists():
        store_names = pd.read_csv(d / "stores.csv").set_index("store_id")["store_name"].to_dict()

    cat_ids = {}
    for cat in sorted(wide.cat_id.unique()):
        obj = db.scalar(select(Category).where(Category.name == cat)) or Category(name=cat)
        db.add(obj)
        db.flush()
        cat_ids[cat] = obj.id

    store_ids = {}
    for code, state in wide[["store_id", "state_id"]].drop_duplicates().itertuples(index=False):
        obj = db.scalar(select(Store).where(Store.code == code)) or Store(code=code, name=code)
        obj.state = state
        obj.name = store_names.get(code, obj.name if obj.name != code else f"Store {code}")
        db.add(obj)
        db.flush()
        store_ids[code] = obj.id

    prod_ids = {}
    for item, dept, cat in wide[["item_id", "dept_id", "cat_id"]].drop_duplicates().itertuples(index=False):
        obj = db.scalar(select(Product).where(Product.sku == item)) or Product(sku=item, name=item)
        obj.name = names.get(item, obj.name)
        obj.department = dept
        obj.category_id = cat_ids[cat]
        db.add(obj)
        db.flush()
        prod_ids[item] = obj.id

    existing_days = set(db.scalars(select(CalendarDay.date)).all())
    cal_records = []
    for r in cal.itertuples(index=False):
        if r.date.date() in existing_days:
            continue
        cal_records.append({
            "date": r.date.date(), "wm_yr_wk": int(r.wm_yr_wk), "weekday": r.weekday,
            "month": int(r.month), "year": int(r.year),
            "event_name_1": r.event_name_1 if isinstance(r.event_name_1, str) else None,
            "event_type_1": r.event_type_1 if isinstance(r.event_type_1, str) else None,
            "event_name_2": r.event_name_2 if isinstance(r.event_name_2, str) else None,
            "event_type_2": r.event_type_2 if isinstance(r.event_type_2, str) else None,
            "snap_ca": bool(r.snap_CA), "snap_tx": bool(r.snap_TX), "snap_wi": bool(r.snap_WI),
        })
    _bulk_insert(db, CalendarDay, cal_records)
    res.calendar_days = len(cal)

    # ------------------------------------------------------------ 5. replace facts for these series
    sids, pids = list(store_ids.values()), list(prod_ids.values())
    db.execute(delete(Sale).where(Sale.store_id.in_(sids), Sale.product_id.in_(pids)))
    db.execute(delete(Price).where(Price.store_id.in_(sids), Price.product_id.in_(pids)))

    long["store_pk"] = long.store_id.map(store_ids)
    long["product_pk"] = long.item_id.map(prod_ids)
    long["revenue"] = (long.units * long.sell_price.fillna(0)).round(2)
    sale_records = [
        {"date": dt.date(), "store_id": int(s), "product_id": int(p), "units": int(u),
         "unit_price": (None if pd.isna(pr) else float(pr)), "revenue": float(rv)}
        for dt, s, p, u, pr, rv in zip(long.date, long.store_pk, long.product_pk, long.units,
                                       long.sell_price, long.revenue, strict=True)
    ]
    _bulk_insert(db, Sale, sale_records)
    res.sales_rows = len(sale_records)

    price_records = [
        {"store_id": store_ids[s], "product_id": prod_ids[i], "wm_yr_wk": int(w), "sell_price": float(p)}
        for s, i, w, p in prices[["store_id", "item_id", "wm_yr_wk", "sell_price"]].itertuples(index=False)
    ]
    _bulk_insert(db, Price, price_records)
    res.price_rows = len(price_records)

    # ------------------------------------------------------------ 6. suppliers + inventory
    supplier_ids = {}
    if (d / "suppliers_synthetic.csv").exists():
        for r in pd.read_csv(d / "suppliers_synthetic.csv").itertuples(index=False):
            obj = db.scalar(select(Supplier).where(Supplier.name == r.supplier)) or Supplier(name=r.supplier)
            obj.contact_email = r.contact_email
            obj.default_lead_time_days = int(r.default_lead_time_days)
            db.add(obj)
            db.flush()
            supplier_ids[r.supplier] = obj.id

    db.execute(delete(InventoryItem).where(InventoryItem.store_id.in_(sids), InventoryItem.product_id.in_(pids)))
    inv_records = []
    if (d / "inventory_synthetic.csv").exists():
        inv = pd.read_csv(d / "inventory_synthetic.csv")
        inv = inv[inv.store_id.isin(store_ids) & inv.item_id.isin(prod_ids)]
        for r in inv.itertuples(index=False):
            inv_records.append({
                "store_id": store_ids[r.store_id], "product_id": prod_ids[r.item_id],
                "supplier_id": supplier_ids.get(r.supplier), "on_hand": int(r.on_hand),
                "on_hand_source": "synthetic", "lead_time_days": int(r.lead_time_days),
                "service_level": float(r.service_level), "unit_cost": float(r.unit_cost),
                "review_period_days": 7, "min_order_qty": 1, "pack_size": 1,
                "order_cost": 25.0, "holding_cost_rate": 0.25, "replenishment_policy": "order_up_to",
            })
    else:
        # No stock data in M5 -> explicit, documented assumption: 14 days of recent average demand.
        recent_cut = long.date.max() - pd.Timedelta(days=27)
        recent = long[long.date >= recent_cut].groupby(["store_pk", "product_pk"]).units.sum() / 28
        last_price = long.sort_values("date").groupby(["store_pk", "product_pk"]).sell_price.last()
        for (s, p), avg in recent.items():
            lp = last_price.get((s, p))
            inv_records.append({
                "store_id": int(s), "product_id": int(p), "supplier_id": None,
                "on_hand": int(round(avg * 14)), "on_hand_source": "assumed", "lead_time_days": 7,
                "service_level": 0.95, "unit_cost": (None if lp is None or pd.isna(lp) else round(float(lp) * 0.65, 2)),
                "review_period_days": 7, "min_order_qty": 1, "pack_size": 1,
                "order_cost": 25.0, "holding_cost_rate": 0.25, "replenishment_policy": "order_up_to",
            })
        res.notes.append("M5 contains no stock levels: on-hand stock was initialised to an ASSUMED 14 days "
                         "of recent average demand (flagged 'assumed'). Update real stock in Inventory.")
    _bulk_insert(db, InventoryItem, inv_records)
    res.inventory_rows = len(inv_records)

    res.stores, res.products = len(store_ids), len(prod_ids)
    label = "Synthetic M5-format demo dataset" if res.synthetic else "M5 Walmart dataset"
    db.add(Dataset(
        name=label, original_filename=sales_path.name, kind="m5_sales", file_path=str(sales_path),
        n_rows=len(wide), n_cols=len(usecols), status="imported", is_synthetic=res.synthetic,
        imported_rows=res.sales_rows, uploaded_by=uploaded_by,
        description=(f"{res.stores} stores, {res.products} products, {res.calendar_days} days. "
                     + ("SYNTHETIC data generated by RetailIQ - not real Walmart data. " if res.synthetic else "")
                     + " ".join(res.notes)),
    ))
    db.commit()
    log.info("M5 ingestion finished: %s", res)
    return res


def main() -> None:  # pragma: no cover - CLI
    from app.core.logging import setup_logging
    from app.database.session import SessionLocal
    setup_logging()
    ap = argparse.ArgumentParser(description="Load M5 files into the RetailIQ database")
    ap.add_argument("--data-dir", type=Path, required=True)
    ap.add_argument("--stores", type=str, help="comma-separated store codes, e.g. CA_1,TX_1")
    ap.add_argument("--max-items", type=int, help="random sample of N items (reproducible)")
    ap.add_argument("--items", type=str, help="comma-separated item ids")
    ap.add_argument("--start-date", type=str)
    ap.add_argument("--end-date", type=str)
    a = ap.parse_args()
    opts = IngestOptions(data_dir=a.data_dir, stores=a.stores.split(",") if a.stores else None,
                         max_items=a.max_items, items=a.items.split(",") if a.items else None,
                         start_date=a.start_date, end_date=a.end_date)
    with SessionLocal() as db:
        print(load_m5(db, opts))


if __name__ == "__main__":  # pragma: no cover
    main()
