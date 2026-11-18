"""
Core retail star-schema.

    categories ─┐
                ├─< products ─┐
    stores ─────┼─────────────┼─< sales >── calendar
                │             ├─< prices
                │             └─< inventory >── suppliers

The structure mirrors the M5 (Walmart) competition data: products belong to
a department and a category, stores belong to a state, daily unit sales are
recorded per store x product x day, and prices change weekly.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)

    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)  # e.g. CA_1
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str | None] = mapped_column(String(40))


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)  # M5 item_id
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    department: Mapped[str | None] = mapped_column(String(80))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"), index=True)

    category: Mapped[Category] = relationship(back_populates="products")


class CalendarDay(Base):
    """One row per date, with event / holiday / SNAP flags (from M5 calendar.csv)."""
    __tablename__ = "calendar"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    wm_yr_wk: Mapped[int] = mapped_column(Integer, index=True)  # Walmart fiscal week id
    weekday: Mapped[str] = mapped_column(String(12))
    month: Mapped[int] = mapped_column(Integer)
    year: Mapped[int] = mapped_column(Integer)
    event_name_1: Mapped[str | None] = mapped_column(String(80))
    event_type_1: Mapped[str | None] = mapped_column(String(40))
    event_name_2: Mapped[str | None] = mapped_column(String(80))
    event_type_2: Mapped[str | None] = mapped_column(String(40))
    snap_ca: Mapped[bool] = mapped_column(Boolean, default=False)
    snap_tx: Mapped[bool] = mapped_column(Boolean, default=False)
    snap_wi: Mapped[bool] = mapped_column(Boolean, default=False)


class Price(Base):
    """Weekly selling price of a product in a store."""
    __tablename__ = "prices"
    __table_args__ = (
        UniqueConstraint("store_id", "product_id", "wm_yr_wk", name="uq_price_store_product_week"),
        CheckConstraint("sell_price >= 0", name="ck_price_nonneg"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    wm_yr_wk: Mapped[int] = mapped_column(Integer)
    sell_price: Mapped[float] = mapped_column(Float, nullable=False)


class Sale(Base):
    """
    Daily unit sales of one product in one store.

    Only days with units > 0 are stored (zero days are re-created when a
    continuous time series is needed, e.g. for forecasting). `revenue` is
    units x the selling price that applied that week.
    """
    __tablename__ = "sales"
    __table_args__ = (
        UniqueConstraint("date", "store_id", "product_id", name="uq_sale_day_store_product"),
        CheckConstraint("units >= 0", name="ck_sale_units_nonneg"),
        Index("ix_sales_store_date", "store_id", "date"),
        Index("ix_sales_product_date", "product_id", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(ForeignKey("calendar.date"), index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float | None] = mapped_column(Float)
    revenue: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(255))
    default_lead_time_days: Mapped[int] = mapped_column(Integer, default=7)


class InventoryItem(Base):
    """
    Current stock position + replenishment parameters for a store x product.

    `on_hand_source` documents where the stock figure came from:
      * "synthetic" - part of the clearly-labelled demo dataset
      * "user"      - entered / edited by a user in the app
      * "assumed"   - initialised by the system (e.g. M5 import has no stock data)
    """
    __tablename__ = "inventory"
    __table_args__ = (
        UniqueConstraint("store_id", "product_id", name="uq_inventory_store_product"),
        CheckConstraint("on_hand >= 0", name="ck_inv_onhand_nonneg"),
        CheckConstraint("lead_time_days > 0", name="ck_inv_leadtime_pos"),
        CheckConstraint("service_level > 0 AND service_level < 1", name="ck_inv_service_level"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"))
    on_hand: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    on_hand_source: Mapped[str] = mapped_column(String(20), default="user")
    lead_time_days: Mapped[int] = mapped_column(Integer, default=7)
    review_period_days: Mapped[int] = mapped_column(Integer, default=7)
    service_level: Mapped[float] = mapped_column(Float, default=0.95)
    min_order_qty: Mapped[int] = mapped_column(Integer, default=1)
    pack_size: Mapped[int] = mapped_column(Integer, default=1)
    unit_cost: Mapped[float | None] = mapped_column(Float)
    order_cost: Mapped[float] = mapped_column(Float, default=25.0)          # fixed cost per order
    holding_cost_rate: Mapped[float] = mapped_column(Float, default=0.25)   # annual, fraction of unit cost
    replenishment_policy: Mapped[str] = mapped_column(String(20), default="order_up_to")  # or "eoq"
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    store: Mapped[Store] = relationship()
    product: Mapped[Product] = relationship()
    supplier: Mapped[Supplier | None] = relationship()
