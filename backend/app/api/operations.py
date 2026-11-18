"""
Forecasting, inventory, assistant, reports and notifications endpoints.
"""
from __future__ import annotations

import csv
import io
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.rate_limit import RateLimiter
from app.database.session import get_db
from app.forecasting.features import load_series
from app.forecasting.pipeline import ALLOWED_HORIZONS, ForecastError, run_forecast
from app.inventory.optimizer import positions
from app.models import ForecastRun, InventoryItem, Notification, Report, Supplier, User
from app.services import assistant, reports

router = APIRouter(dependencies=[Depends(get_current_user)])
assistant_limiter = RateLimiter(settings.RATE_LIMIT_ASSISTANT_PER_MIN, scope="assistant")


# ================================================================== forecasting
class ForecastIn(BaseModel):
    product_id: int
    store_id: int | None = None  # None = all stores combined
    horizon: int = Field(30, description="7, 14, 30 or 60 days")


@router.post("/forecasting/run", tags=["forecasting"])
def forecast(body: ForecastIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.horizon not in ALLOWED_HORIZONS:
        raise HTTPException(422, f"Horizon must be one of {list(ALLOWED_HORIZONS)}")
    try:
        return run_forecast(db, body.product_id, body.store_id, body.horizon, user.id)
    except ForecastError as e:
        raise HTTPException(422, str(e)) from None


@router.get("/forecasting/history", tags=["forecasting"])
def series_preview(product_id: int, store_id: int | None = None, days: int = Query(180, ge=28, le=1000),
                   db: Session = Depends(get_db)):
    y = load_series(db, product_id, store_id)
    return {"points": [{"date": d.date().isoformat(), "units": float(v)} for d, v in y.iloc[-days:].items()],
            "total_days": len(y)}


@router.get("/forecasting/runs", tags=["forecasting"])
def list_runs(limit: int = Query(25, le=200), db: Session = Depends(get_db)):
    runs = db.scalars(select(ForecastRun).order_by(ForecastRun.id.desc()).limit(limit)).all()
    out = []
    for r in runs:
        d = r.details
        sel = next((m for m in d.get("models", []) if m["is_selected"]), {})
        out.append({"id": r.id, "product": d["product"], "store": d["store"], "horizon": r.horizon_days,
                    "best_model": r.best_model, "best_model_label": d.get("best_model_label"),
                    "test": sel.get("test"), "total_predicted_units": d["summary"]["total_predicted_units"],
                    "created_at": r.created_at})
    return out


def _run(db, run_id) -> ForecastRun:
    r = db.get(ForecastRun, run_id)
    if r is None:
        raise HTTPException(404, "Forecast run not found")
    return r


@router.get("/forecasting/runs/{run_id}", tags=["forecasting"])
def get_run(run_id: int, db: Session = Depends(get_db)):
    r = _run(db, run_id)
    return {"run_id": r.id, "created_at": r.created_at, **r.details}


@router.get("/forecasting/runs/{run_id}/download", tags=["forecasting"])
def download_run(run_id: int, db: Session = Depends(get_db)):
    r = _run(db, run_id)
    d = r.details
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["product_sku", "product_name", "store", "date", "predicted_units", "lower_80", "upper_80", "model"])
    for row in d["forecast"]:
        w.writerow([d["product"]["sku"], d["product"]["name"], d["store"]["code"] if d["store"] else "ALL",
                    row["date"], row["predicted"], row["lower"], row["upper"], d["best_model"]])
    name = f"forecast_{d['product']['sku']}_{d['store']['code'] if d['store'] else 'ALL'}_{r.horizon_days}d.csv"
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ================================================================== inventory
@router.get("/inventory", tags=["inventory"])
def inventory(store_id: int | None = None, category_id: int | None = None, status: str | None = None,
              search: str | None = Query(None, max_length=100), db: Session = Depends(get_db)):
    if status and status not in ("Critical", "Low Stock", "Overstocked", "Healthy"):
        raise HTTPException(422, "Unknown status")
    return positions(db, store_id, category_id, status, search)


class InventoryUpdate(BaseModel):
    on_hand: int | None = Field(None, ge=0, le=10_000_000)
    lead_time_days: int | None = Field(None, ge=1, le=365)
    review_period_days: int | None = Field(None, ge=0, le=90)
    service_level: float | None = Field(None, gt=0.5, lt=0.9999)
    min_order_qty: int | None = Field(None, ge=1, le=1_000_000)
    pack_size: int | None = Field(None, ge=1, le=100_000)
    unit_cost: float | None = Field(None, ge=0)
    order_cost: float | None = Field(None, ge=0)
    holding_cost_rate: float | None = Field(None, gt=0, le=2)
    supplier_id: int | None = None
    replenishment_policy: str | None = Field(None, pattern="^(order_up_to|eoq)$")


@router.patch("/inventory/{item_id}", tags=["inventory"])
def update_inventory(item_id: int, body: InventoryUpdate, db: Session = Depends(get_db)):
    item = db.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(404, "Inventory item not found")
    data = body.model_dump(exclude_unset=True)
    if "supplier_id" in data and data["supplier_id"] is not None and db.get(Supplier, data["supplier_id"]) is None:
        raise HTTPException(422, "Supplier not found")
    for k, v in data.items():
        setattr(item, k, v)
    if "on_hand" in data:
        item.on_hand_source = "user"
    db.commit()
    res = positions(db, store_id=item.store_id, search=None)
    return next(i for i in res["items"] if i["id"] == item_id)


class SupplierIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    contact_email: EmailStr | None = None
    default_lead_time_days: int = Field(7, ge=1, le=365)


@router.get("/suppliers", tags=["inventory"])
def suppliers(db: Session = Depends(get_db)):
    return [{"id": s.id, "name": s.name, "contact_email": s.contact_email, "default_lead_time_days": s.default_lead_time_days}
            for s in db.scalars(select(Supplier).order_by(Supplier.name))]


@router.post("/suppliers", tags=["inventory"], status_code=201)
def create_supplier(body: SupplierIn, db: Session = Depends(get_db)):
    if db.scalar(select(Supplier).where(Supplier.name == body.name)):
        raise HTTPException(409, "Supplier already exists")
    s = Supplier(**body.model_dump())
    db.add(s)
    db.commit()
    return {"id": s.id, **body.model_dump()}


@router.put("/suppliers/{supplier_id}", tags=["inventory"])
def update_supplier(supplier_id: int, body: SupplierIn, db: Session = Depends(get_db)):
    s = db.get(Supplier, supplier_id)
    if s is None:
        raise HTTPException(404, "Supplier not found")
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    db.commit()
    return {"id": s.id, **body.model_dump()}


@router.post("/inventory/alerts", tags=["inventory"])
def create_alerts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Turn the current critical / low-stock items into a notification for the user."""
    res = positions(db)
    c = res["summary"]["counts"]
    if not (c["Critical"] or c["Low Stock"]):
        return {"created": False, "message": "No items need attention."}
    top = [i for i in res["items"] if i["status"] == "Critical"][:3]
    msg = f"{c['Critical']} critical and {c['Low Stock']} low-stock items. " + "; ".join(
        f"{i['product_name']} @ {i['store_code']}: order {i['recommended_order_qty']}" for i in top)
    db.add(Notification(user_id=user.id, title="Inventory needs attention", message=msg,
                        level="critical" if c["Critical"] else "warning", link="/app/inventory"))
    db.commit()
    return {"created": True, "message": msg}


# ================================================================== assistant
class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=500)


@router.post("/assistant/ask", tags=["assistant"], dependencies=[Depends(assistant_limiter)])
def ask(body: AskIn, db: Session = Depends(get_db)):
    return assistant.ask(db, body.question)


@router.get("/assistant/info", tags=["assistant"])
def assistant_info():
    return {"llm_configured": settings.llm_provider is not None, "provider": settings.llm_provider,
            "examples": assistant.EXAMPLES}


# ================================================================== reports
class ReportIn(BaseModel):
    report_type: str
    format: str = Field("pdf", pattern="^(pdf|xlsx|csv)$")
    start: date | None = None
    end: date | None = None
    run_id: int | None = None


@router.get("/reports/types", tags=["reports"])
def report_types():
    return [{"id": k, "label": v} for k, v in reports.REPORT_TYPES.items()]


@router.post("/reports", tags=["reports"], status_code=201)
def create_report(body: ReportIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.report_type not in reports.REPORT_TYPES:
        raise HTTPException(422, "Unknown report type")
    try:
        path, rd = reports.generate_file(db, body.report_type, body.format, settings.REPORT_DIR,
                                         start=body.start, end=body.end, run_id=body.run_id)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    rep = Report(report_type=body.report_type, file_format=body.format, title=f"{rd.title} · {rd.period}",
                 file_path=str(path), params=body.model_dump(mode="json"), created_by=user.id)
    db.add(rep)
    db.commit()
    return {"id": rep.id, "title": rep.title, "file_format": rep.file_format, "report_type": rep.report_type,
            "created_at": rep.created_at}


@router.get("/reports", tags=["reports"])
def list_reports(db: Session = Depends(get_db)):
    return [{"id": r.id, "title": r.title, "file_format": r.file_format, "report_type": r.report_type,
             "created_at": r.created_at, "created_by": r.created_by,
             "available": Path(r.file_path).exists()}
            for r in db.scalars(select(Report).order_by(Report.id.desc()).limit(100))]


@router.get("/reports/{report_id}/download", tags=["reports"])
def download_report(report_id: int, db: Session = Depends(get_db)):
    r = db.get(Report, report_id)
    if r is None or not Path(r.file_path).exists():
        raise HTTPException(404, "Report file not found")
    media = {"pdf": "application/pdf", "csv": "text/csv",
             "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}[r.file_format]
    return FileResponse(r.file_path, media_type=media, filename=Path(r.file_path).name)


# ================================================================== notifications
def _visible(user: User):
    return or_(Notification.user_id == user.id, Notification.user_id.is_(None))


@router.get("/notifications", tags=["notifications"])
def notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Notification).where(_visible(user)).order_by(Notification.id.desc()).limit(50)).all()
    return [{"id": n.id, "title": n.title, "message": n.message, "level": n.level, "link": n.link,
             "is_read": n.is_read, "created_at": n.created_at} for n in rows]


@router.post("/notifications/read-all", tags=["notifications"])
def read_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(Notification.user_id == user.id).values(is_read=True))
    db.commit()
    return {"ok": True}


@router.post("/notifications/{nid}/read", tags=["notifications"])
def read_one(nid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = db.get(Notification, nid)
    if n is None or (n.user_id not in (None, user.id)):
        raise HTTPException(404, "Notification not found")
    if n.user_id == user.id:
        n.is_read = True
        db.commit()
    return {"ok": True}

