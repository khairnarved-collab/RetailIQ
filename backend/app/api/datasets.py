"""
Dataset management: upload -> profile -> clean -> (download | import).
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, require_admin
from app.database.session import get_db
from app.models import DataQualityReport, Dataset, Notification, User
from app.services import data_quality as dq
from app.services.dataset_import import import_customer_transactions, import_sales_long

log = logging.getLogger(__name__)
router = APIRouter(prefix="/datasets", tags=["datasets"])

ALLOWED = {".csv", ".xlsx", ".xls"}
MAX_ROWS = 1_000_000


def _ds_out(ds: Dataset) -> dict:
    return {
        "id": ds.id, "name": ds.name, "original_filename": ds.original_filename, "kind": ds.kind,
        "kind_label": dq.KINDS.get(ds.kind, {}).get("label", "M5 sales (wide)" if ds.kind == "m5_sales" else "Generic table"),
        "n_rows": ds.n_rows, "n_cols": ds.n_cols, "status": ds.status, "is_synthetic": ds.is_synthetic,
        "description": ds.description, "imported_rows": ds.imported_rows,
        "has_cleaned": bool(ds.cleaned_path), "has_rejected": bool(ds.rejected_path),
        "created_at": ds.created_at, "updated_at": ds.updated_at, "uploaded_by": ds.uploaded_by,
    }


def _get(db: Session, dataset_id: int) -> Dataset:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise HTTPException(404, "Dataset not found")
    return ds


def _preview(df: pd.DataFrame, n: int = 50) -> dict:
    head = df.head(n).copy()
    for c in head.columns:
        if pd.api.types.is_datetime64_any_dtype(head[c]):
            head[c] = head[c].dt.strftime("%Y-%m-%d")
    head = head.astype(object).where(head.notna(), None)
    return {"columns": [str(c) for c in head.columns], "rows": head.values.tolist()}


@router.get("")
def list_datasets(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_ds_out(d) for d in db.scalars(select(Dataset).order_by(Dataset.created_at.desc(), Dataset.id.desc())).all()]


SAMPLE_FILES = {
    "messy_sales_sample.csv": "Small daily-sales file with deliberate quality problems - try the cleaning pipeline (SYNTHETIC)",
    "customer_transactions_synthetic.csv": "Customer transactions for RFM / segmentation (SYNTHETIC)",
}


@router.get("/samples")
def sample_files(_: User = Depends(get_current_user)):
    """Bundled sample files users can download and re-upload to try the pipeline."""
    out = []
    for name, desc in SAMPLE_FILES.items():
        p = settings.SAMPLE_DIR / name
        if p.exists():
            out.append({"name": name, "description": desc, "size_bytes": p.stat().st_size})
    return out


@router.get("/samples/{name}")
def sample_download(name: str, _: User = Depends(get_current_user)):
    if name not in SAMPLE_FILES or not (settings.SAMPLE_DIR / name).exists():
        raise HTTPException(404, "Sample not found")
    return FileResponse(settings.SAMPLE_DIR / name, filename=name, media_type="text/csv")


@router.post("/upload", status_code=201)
async def upload(file: UploadFile = File(...), name: str | None = Form(None),
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(415, "Only CSV (.csv) and Excel (.xlsx, .xls) files are supported")
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(413, f"File is larger than the {settings.MAX_UPLOAD_MB} MB limit")
    if not content:
        raise HTTPException(400, "The file is empty")
    stored = settings.UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
    stored.write_bytes(content)
    try:
        df = dq.read_table(stored)
    except Exception as e:  # noqa: BLE001 - any parse failure is a user error
        stored.unlink(missing_ok=True)
        raise HTTPException(422, f"Could not read the file: {e}") from None
    if df.empty or df.shape[1] == 0:
        stored.unlink(missing_ok=True)
        raise HTTPException(422, "The file contains no data rows")
    if len(df) > MAX_ROWS:
        stored.unlink(missing_ok=True)
        raise HTTPException(413, f"The file has more than {MAX_ROWS:,} rows")

    report = dq.profile(df)
    ds = Dataset(name=(name or Path(file.filename).stem)[:200], original_filename=file.filename[:255],
                 kind=report["detected_kind"], file_path=str(stored), n_rows=len(df), n_cols=df.shape[1],
                 status="profiled", uploaded_by=user.id,
                 is_synthetic="synthetic" in (file.filename or "").lower(),
                 description="File name indicates SYNTHETIC data." if "synthetic" in (file.filename or "").lower() else None)
    db.add(ds)
    db.flush()
    db.add(DataQualityReport(dataset_id=ds.id, stage="raw", report=report))
    db.commit()
    log.info("Dataset %s uploaded by %s: %s rows", ds.id, user.email, len(df))
    return {**_ds_out(ds), "quality": report, "preview": _preview(df)}


@router.get("/{dataset_id}")
def detail(dataset_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = _get(db, dataset_id)
    out = _ds_out(ds)
    reports = {r.stage: r.report for r in ds.quality_reports}
    out["quality"] = reports.get("raw")
    out["cleaned_quality"] = reports.get("cleaned")
    out["cleaning_summary"] = reports.get("cleaning")
    path = ds.cleaned_path or ds.file_path
    try:
        df = dq.read_table(Path(path)) if Path(path).exists() else None
    except Exception:  # noqa: BLE001
        df = None
    out["preview"] = _preview(df) if df is not None and ds.kind != "m5_sales" else None
    return out


@router.post("/{dataset_id}/clean")
def run_cleaning(dataset_id: int, kind: str | None = None, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    ds = _get(db, dataset_id)
    if ds.kind == "m5_sales":
        raise HTTPException(400, "M5 files are loaded by the M5 ingestion pipeline, not the generic cleaner")
    if kind and kind not in (*dq.KINDS, "generic"):
        raise HTTPException(422, "Unknown dataset kind")
    df = dq.read_table(Path(ds.file_path))
    try:
        result = dq.clean(df, None if kind in (None, "") else (None if kind == "generic" else kind))
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    cleaned_path = settings.PROCESSED_DIR / f"dataset_{ds.id}_cleaned.csv"
    rejected_path = settings.PROCESSED_DIR / f"dataset_{ds.id}_rejected.csv"
    result.cleaned.to_csv(cleaned_path, index=False, date_format="%Y-%m-%d")
    result.rejected.to_csv(rejected_path, index=False, date_format="%Y-%m-%d")
    ds.cleaned_path, ds.rejected_path = str(cleaned_path), str(rejected_path)
    ds.kind = result.kind
    ds.status = "cleaned"
    # keep only the latest cleaning reports
    for r in list(ds.quality_reports):
        if r.stage in ("cleaned", "cleaning"):
            db.delete(r)
    db.flush()
    summary = result.summary()
    db.add(DataQualityReport(dataset_id=ds.id, stage="cleaning", report=summary))
    db.add(DataQualityReport(dataset_id=ds.id, stage="cleaned", report=dq.profile(result.cleaned)))
    db.commit()
    return {"dataset": _ds_out(ds), "summary": summary, "preview": _preview(result.cleaned),
            "rejected_preview": _preview(result.rejected, 20)}


@router.post("/{dataset_id}/import")
def import_dataset(dataset_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = _get(db, dataset_id)
    if ds.status not in ("cleaned", "imported") or not ds.cleaned_path:
        raise HTTPException(400, "Run the cleaning pipeline before importing")
    df = pd.read_csv(ds.cleaned_path, low_memory=False)
    notes: list[str] = []
    try:
        if ds.kind == "customer_transactions":
            n = import_customer_transactions(db, ds, df)
            target = "customer analytics"
        elif ds.kind == "sales_long":
            n, notes = import_sales_long(db, ds, df)
            target = "the sales warehouse (dashboard, forecasting, inventory)"
        else:
            raise HTTPException(400, "Only customer-transaction and sales datasets can be imported. "
                                     "Generic tables can still be explored in the EDA module.")
        ds.status = "imported"
        ds.imported_rows = n
        db.add(Notification(user_id=user.id, title="Dataset imported", level="success",
                            message=f"'{ds.name}': {n:,} rows imported into {target}.", link="/app/data"))
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:  # noqa: BLE001
        db.rollback()
        log.exception("Import failed")
        raise HTTPException(422, f"Import failed: {e}") from None
    return {"dataset": _ds_out(ds), "imported_rows": n, "notes": notes}


@router.get("/{dataset_id}/download/{which}")
def download(dataset_id: int, which: str, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = _get(db, dataset_id)
    path = {"raw": ds.file_path, "cleaned": ds.cleaned_path, "rejected": ds.rejected_path}.get(which)
    if not path or not Path(path).exists():
        raise HTTPException(404, "File not available")
    stem = Path(ds.original_filename).stem
    ext = Path(path).suffix
    return FileResponse(path, filename=f"{stem}_{which}{ext}")


@router.delete("/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    ds = _get(db, dataset_id)
    for p in (ds.cleaned_path, ds.rejected_path):
        if p:
            Path(p).unlink(missing_ok=True)
    # Only delete uploaded files we own (never the bundled sample / M5 source files)
    if ds.file_path and Path(ds.file_path).parent == settings.UPLOAD_DIR:
        Path(ds.file_path).unlink(missing_ok=True)
    db.delete(ds)
    db.commit()
