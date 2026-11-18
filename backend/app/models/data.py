"""Uploaded datasets and their data-quality reports."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # sales_long | customer_transactions | m5_sales | generic
    kind: Mapped[str] = mapped_column(String(40), default="generic", index=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    cleaned_path: Mapped[str | None] = mapped_column(String(500))
    rejected_path: Mapped[str | None] = mapped_column(String(500))
    n_rows: Mapped[int] = mapped_column(Integer, default=0)
    n_cols: Mapped[int] = mapped_column(Integer, default=0)
    # uploaded -> profiled -> cleaned -> imported (or failed)
    status: Mapped[str] = mapped_column(String(20), default="uploaded")
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str | None] = mapped_column(Text)
    imported_rows: Mapped[int | None] = mapped_column(Integer)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    quality_reports: Mapped[list["DataQualityReport"]] = relationship(
        cascade="all, delete-orphan", back_populates="dataset", order_by="DataQualityReport.id"
    )


class DataQualityReport(Base):
    __tablename__ = "data_quality_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(20), default="raw")  # raw | cleaned
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    dataset: Mapped[Dataset] = relationship(back_populates="quality_reports")
