"""
Customer-level data.

These tables are ONLY filled from an uploaded customer-transaction dataset.
The M5 data has no customer information, so nothing here is ever derived
from it.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("dataset_id", "external_id", name="uq_customer_dataset_ext"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(80), nullable=False)
    city: Mapped[str | None] = mapped_column(String(80))


class CustomerTransaction(Base):
    __tablename__ = "customer_transactions"
    __table_args__ = (Index("ix_ctx_customer_date", "customer_id", "order_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    order_id: Mapped[str] = mapped_column(String(80), nullable=False)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[int | None] = mapped_column(Integer)
    category: Mapped[str | None] = mapped_column(String(80))
    store_ref: Mapped[str | None] = mapped_column(String(80))


class CustomerSegment(Base):
    """Latest RFM + K-Means result per customer (recomputed on demand)."""
    __tablename__ = "customer_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), unique=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    recency_days: Mapped[int] = mapped_column(Integer)
    frequency: Mapped[int] = mapped_column(Integer)
    monetary: Mapped[float] = mapped_column(Float)
    r_score: Mapped[int] = mapped_column(Integer)
    f_score: Mapped[int] = mapped_column(Integer)
    m_score: Mapped[int] = mapped_column(Integer)
    rfm_segment: Mapped[str] = mapped_column(String(40), index=True)
    cluster: Mapped[int | None] = mapped_column(Integer)
    clv_estimate: Mapped[float | None] = mapped_column(Float)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
