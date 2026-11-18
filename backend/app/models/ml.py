"""Forecast runs, the predictions they produced, and honest model evaluations."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class ForecastRun(Base):
    __tablename__ = "forecast_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    # NULL store = forecast of the product's total demand across all stores
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id", ondelete="CASCADE"), index=True)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    best_model: Mapped[str] = mapped_column(String(40), nullable=False)
    train_start: Mapped[date] = mapped_column(Date)
    train_end: Mapped[date] = mapped_column(Date)
    details: Mapped[dict] = mapped_column(JSON, default=dict)  # splits, SHAP, notes
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    forecasts: Mapped[list["Forecast"]] = relationship(cascade="all, delete-orphan", back_populates="run")
    evaluations: Mapped[list["ModelEvaluation"]] = relationship(cascade="all, delete-orphan", back_populates="run")


class Forecast(Base):
    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("forecast_runs.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    predicted_units: Mapped[float] = mapped_column(Float, nullable=False)
    lower_units: Mapped[float | None] = mapped_column(Float)
    upper_units: Mapped[float | None] = mapped_column(Float)

    run: Mapped[ForecastRun] = relationship(back_populates="forecasts")


class ModelEvaluation(Base):
    """Metrics of one candidate model on one hold-out split (validation or test)."""
    __tablename__ = "model_evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("forecast_runs.id", ondelete="CASCADE"), index=True)
    model_name: Mapped[str] = mapped_column(String(40), nullable=False)
    split: Mapped[str] = mapped_column(String(20), nullable=False)  # "validation" | "test"
    mae: Mapped[float] = mapped_column(Float)
    rmse: Mapped[float] = mapped_column(Float)
    mape: Mapped[float | None] = mapped_column(Float)  # NULL when not mathematically meaningful
    wape: Mapped[float | None] = mapped_column(Float)
    bias: Mapped[float | None] = mapped_column(Float)

    run: Mapped[ForecastRun] = relationship(back_populates="evaluations")
