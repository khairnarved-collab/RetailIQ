"""
Read-only analytics endpoints: filters metadata, dashboard, EDA, customers,
insights. All require a logged-in user (admin or analyst).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics import customers as cust
from app.analytics import eda
from app.analytics import sales as sa
from app.core.deps import get_current_user
from app.database.session import get_db
from app.models import Category, Dataset, Product, Sale, Store
from app.services import insights

router = APIRouter(tags=["analytics"], dependencies=[Depends(get_current_user)])


def parse_ids(raw: str | None) -> tuple[int, ...]:
    if not raw:
        return ()
    try:
        return tuple(sorted({int(x) for x in raw.split(",") if x.strip()}))
    except ValueError:
        raise HTTPException(422, "IDs must be comma-separated integers") from None


def filters(start: date | None = None, end: date | None = None, stores: str | None = None,
            categories: str | None = None, products: str | None = None) -> sa.Filters:
    if start and end and start > end:
        raise HTTPException(422, "Start date must be before end date")
    return sa.Filters(start, end, parse_ids(stores), parse_ids(categories), parse_ids(products))


@router.get("/meta/filters")
def filter_options(db: Session = Depends(get_db)):
    lo, hi = sa.data_bounds(db)
    synthetic = db.scalar(select(func.count(Dataset.id)).where(Dataset.kind == "m5_sales", Dataset.is_synthetic.is_(True)))
    return {
        "date_min": lo, "date_max": hi,
        "stores": [{"id": s.id, "code": s.code, "name": s.name, "state": s.state}
                   for s in db.scalars(select(Store).order_by(Store.code))],
        "categories": [{"id": c.id, "name": c.name} for c in db.scalars(select(Category).order_by(Category.name))],
        "products": [{"id": p.id, "sku": p.sku, "name": p.name, "category_id": p.category_id}
                     for p in db.scalars(select(Product).order_by(Product.name))],
        "sales_rows": db.scalar(select(func.count(Sale.id))),
        "synthetic_data": bool(synthetic),
    }


@router.get("/dashboard")
def dashboard(f: sa.Filters = Depends(filters), db: Session = Depends(get_db)):
    if sa.data_bounds(db)[1] is None:
        return {"empty": True}
    return sa.dashboard(db, f)


# ------------------------------------------------------------------ EDA
@router.get("/eda/sources")
def eda_sources(db: Session = Depends(get_db)):
    out = [{"id": "sales", "label": "Sales warehouse (all imported sales)"}]
    for d in db.scalars(select(Dataset).where(Dataset.kind != "m5_sales").order_by(Dataset.id.desc())):
        out.append({"id": f"dataset:{d.id}", "label": f"{d.name} ({'cleaned' if d.cleaned_path else 'raw'})",
                    "is_synthetic": d.is_synthetic})
    return out


def _load(db, source):
    try:
        return eda.load_source(db, source)[0]
    except ValueError as e:
        raise HTTPException(404, str(e)) from None


@router.get("/eda/summary")
def eda_summary(source: str = "sales", db: Session = Depends(get_db)):
    try:
        return eda.summary(db, source)
    except ValueError as e:
        raise HTTPException(404, str(e)) from None


@router.get("/eda/histogram")
def eda_histogram(column: str, source: str = "sales", bins: int = Query(30, ge=5, le=100), db: Session = Depends(get_db)):
    df = _load(db, source)
    if column not in df.columns:
        raise HTTPException(404, "Unknown column")
    try:
        return eda.histogram(df, column, bins)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@router.get("/eda/box")
def eda_box(columns: str, source: str = "sales", by: str | None = None, db: Session = Depends(get_db)):
    df = _load(db, source)
    cols = [c for c in columns.split(",") if c in df.columns]
    if not cols or (by and by not in df.columns):
        raise HTTPException(404, "Unknown column")
    return eda.box(df, cols, by)


@router.get("/eda/scatter")
def eda_scatter(x: str, y: str, source: str = "sales", db: Session = Depends(get_db)):
    df = _load(db, source)
    if x not in df.columns or y not in df.columns:
        raise HTTPException(404, "Unknown column")
    try:
        return eda.scatter(df, x, y)
    except (ValueError, TypeError) as e:
        raise HTTPException(422, str(e)) from None


@router.get("/eda/correlation")
def eda_corr(source: str = "sales", columns: str | None = None, db: Session = Depends(get_db)):
    return eda.correlation(_load(db, source), columns.split(",") if columns else None)


@router.get("/eda/plot.png")
def eda_plot(kind: str = "heatmap", source: str = "sales", columns: str | None = None, db: Session = Depends(get_db)):
    try:
        png = eda.seaborn_png(db, source, kind, columns.split(",") if columns else None)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    return Response(png, media_type="image/png",
                    headers={"Content-Disposition": f'attachment; filename="retailiq_eda_{kind}.png"'})


# ------------------------------------------------------------------ customers
@router.get("/customers/analysis")
def customer_analysis(dataset_id: int | None = None, db: Session = Depends(get_db)):
    return cust.analyse(db, dataset_id)


# ------------------------------------------------------------------ insights
@router.get("/insights")
def business_insights(db: Session = Depends(get_db)):
    return insights.generate(db)

