"""
Remove or restore the bundled SYNTHETIC demo data, leaving user-uploaded data untouched.

Demo records are recognised by the synthetic generator's fixed store codes and SKUs and by the
`is_synthetic` flag on datasets, so real uploads (different codes) are never deleted.
"""
from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.analytics import sales as sa
from app.models import (
    Category,
    Customer,
    CustomerSegment,
    CustomerTransaction,
    DataQualityReport,
    Dataset,
    ForecastRun,
    InventoryItem,
    Price,
    Product,
    Sale,
    Store,
)
from app.services import sample_data


def _demo_ids(db: Session) -> tuple[list[int], list[int]]:
    stores = db.scalars(select(Store.id).where(Store.code.in_(list(sample_data.STORES)))).all()
    products = db.scalars(select(Product.id).where(Product.sku.in_([i[0] for i in sample_data.ITEMS]))).all()
    return list(stores), list(products)


def status(db: Session) -> dict:
    stores, products = _demo_ids(db)
    demo_sales = db.scalar(select(func.count(Sale.id)).where(Sale.store_id.in_(stores), Sale.product_id.in_(products))) if stores and products else 0
    total = db.scalar(select(func.count(Sale.id))) or 0
    synthetic_customers = db.scalar(select(func.count(Dataset.id)).where(Dataset.kind == "customer_transactions",
                                                                         Dataset.is_synthetic.is_(True))) or 0
    return {"demo_sales_rows": int(demo_sales or 0), "other_sales_rows": int(total - (demo_sales or 0)),
            "demo_customer_datasets": int(synthetic_customers), "demo_present": bool(demo_sales)}


def remove(db: Session) -> dict:
    stores, products = _demo_ids(db)
    removed = status(db)
    if products:
        db.execute(delete(ForecastRun).where(ForecastRun.product_id.in_(products)))
    if stores and products:
        db.execute(delete(InventoryItem).where(InventoryItem.store_id.in_(stores), InventoryItem.product_id.in_(products)))
        db.execute(delete(Price).where(Price.store_id.in_(stores), Price.product_id.in_(products)))
        db.execute(delete(Sale).where(Sale.store_id.in_(stores), Sale.product_id.in_(products)))
    # drop demo products/stores/categories that no longer have any data
    for pid in products:
        if not db.scalar(select(func.count(Sale.id)).where(Sale.product_id == pid)):
            db.execute(delete(InventoryItem).where(InventoryItem.product_id == pid))
            db.execute(delete(Price).where(Price.product_id == pid))
            db.execute(delete(ForecastRun).where(ForecastRun.product_id == pid))
            db.execute(delete(Product).where(Product.id == pid))
    for sid in stores:
        if not db.scalar(select(func.count(Sale.id)).where(Sale.store_id == sid)):
            db.execute(delete(InventoryItem).where(InventoryItem.store_id == sid))
            db.execute(delete(Price).where(Price.store_id == sid))
            db.execute(delete(Store).where(Store.id == sid))
    for cid in db.scalars(select(Category.id)).all():
        if not db.scalar(select(func.count(Product.id)).where(Product.category_id == cid)):
            db.execute(delete(Category).where(Category.id == cid))
    # synthetic datasets (M5-format demo + synthetic customers)
    ds_ids = db.scalars(select(Dataset.id).where(Dataset.is_synthetic.is_(True),
                                                Dataset.kind.in_(["m5_sales", "customer_transactions"]))).all()
    if ds_ids:
        db.execute(delete(CustomerSegment).where(CustomerSegment.dataset_id.in_(ds_ids)))
        db.execute(delete(CustomerTransaction).where(CustomerTransaction.dataset_id.in_(ds_ids)))
        db.execute(delete(Customer).where(Customer.dataset_id.in_(ds_ids)))
        db.execute(delete(DataQualityReport).where(DataQualityReport.dataset_id.in_(ds_ids)))
        db.execute(delete(Dataset).where(Dataset.id.in_(ds_ids)))
    db.commit()
    sa._FC_CACHE.clear()
    return {"removed_sales_rows": removed["demo_sales_rows"], "remaining_sales_rows": removed["other_sales_rows"]}


def restore(db: Session, user_id: int | None) -> dict:
    from app.services.m5_ingestion import IngestOptions, load_m5
    from scripts.seed import ensure_sample_files, seed_customers
    res = load_m5(db, IngestOptions(data_dir=ensure_sample_files()), uploaded_by=user_id)
    seed_customers(db, user_id)
    sa._FC_CACHE.clear()
    return {"restored_sales_rows": res.sales_rows}
