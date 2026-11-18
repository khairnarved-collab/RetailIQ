"""
End-to-end forecasting pipeline for one product (in one store or all stores).

Time-based splits (never random - that would leak the future into training):

    |------------------- train -------------------|--- validation ---|----- test -----|--> future
                                                   E days             E days            horizon H
    E = evaluation window = min(H, 56) days (at least 14)

Steps
  1. Fit every candidate model on TRAIN, forecast the VALIDATION window,
     score it. The model with the lowest validation WAPE is selected
     (RMSE breaks ties). WAPE is used because it stays meaningful on days
     with zero sales.
  2. Refit every model on TRAIN+VALIDATION and forecast the TEST window.
     These test scores are reported as the honest estimate of accuracy:
     the test data played no role in choosing the model.
  3. Refit the selected model on ALL data and forecast H days ahead.
  4. Prediction interval: empirical quantiles of the selected model's
     hold-out errors (validation + test), added to the point forecast.
  5. SHAP values explain the tree model's forecast drivers.
"""
from __future__ import annotations

import logging
import time
from datetime import date

import joblib
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import settings
from app.forecasting import explain
from app.forecasting.features import (
    _calendar_block,
    future_calendar,
    load_exog,
    load_series,
)
from app.forecasting.metrics import evaluate
from app.forecasting.models import MODEL_CLASSES, MODEL_LABELS
from app.models import Forecast, ForecastRun, ModelEvaluation, Product, Store

log = logging.getLogger(__name__)
ALLOWED_HORIZONS = (7, 14, 30, 60)
MIN_TRAIN_DAYS = 120


class ForecastError(ValueError):
    pass


def _r(x, nd=3):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), nd)


def run_forecast(db: Session, product_id: int, store_id: int | None, horizon: int,
                 user_id: int | None = None, coverage: float = 0.80) -> dict:
    t0 = time.time()
    if horizon not in ALLOWED_HORIZONS:
        raise ForecastError(f"Horizon must be one of {ALLOWED_HORIZONS}")
    product = db.get(Product, product_id)
    if product is None:
        raise ForecastError("Product not found")
    store = db.get(Store, store_id) if store_id is not None else None
    if store_id is not None and store is None:
        raise ForecastError("Store not found")

    y = load_series(db, product_id, store_id)
    E = max(14, min(horizon, 56))
    if len(y) < MIN_TRAIN_DAYS + 2 * E + 28:
        raise ForecastError(f"Not enough history: {len(y)} days available, at least "
                            f"{MIN_TRAIN_DAYS + 2 * E + 28} needed for horizon {horizon}.")
    exog = load_exog(db, product_id, store_id, y.index[0].date(), y.index[-1].date())
    cal = _calendar_block(exog)

    n = len(y)
    train_end, val_end = n - 2 * E, n - E
    y_train, y_val, y_test = y.iloc[:train_end], y.iloc[train_end:val_end], y.iloc[val_end:]
    y_trval = y.iloc[:val_end]

    candidates = MODEL_CLASSES
    val_scores, test_scores, test_preds, val_preds = {}, {}, {}, {}
    for cls in candidates:
        try:
            m = cls().fit(y_train, cal)
            pv = m.predict(E, cal.loc[y_val.index])
            val_preds[cls.name] = pv
            val_scores[cls.name] = evaluate(y_val, pv)
            m2 = cls().fit(y_trval, cal)
            pt = m2.predict(E, cal.loc[y_test.index])
            test_preds[cls.name] = pt
            test_scores[cls.name] = evaluate(y_test, pt)
        except Exception as e:  # noqa: BLE001 - one failing model must not break the run
            log.warning("Model %s failed: %s", cls.name, e)

    if not val_scores:
        raise ForecastError("All models failed to train on this series")

    def rank_key(name):
        s = val_scores[name]
        return (s["wape"] if s["wape"] is not None else s["mae"] * 1e6, s["rmse"])

    best = min(val_scores, key=rank_key)
    best_cls = next(c for c in candidates if c.name == best)

    # final model on all data
    final = best_cls().fit(y, cal)
    fut_cal = future_calendar(db, product_id, store_id, y.index[-1], horizon)
    pred = final.predict(horizon, fut_cal)

    # empirical prediction interval from hold-out errors of the selected model
    resid = np.concatenate([y_val.to_numpy() - val_preds[best], y_test.to_numpy() - test_preds[best]])
    alpha = (1 - coverage) / 2
    q_lo, q_hi = np.quantile(resid, [alpha, 1 - alpha])
    lower = np.clip(pred + q_lo, 0, None)
    upper = np.clip(pred + q_hi, 0, None)

    # SHAP for a tree model
    shap_info = explain.explain(final, y, cal, fut_cal, horizon, best, val_scores)

    future_dates = pd.date_range(y.index[-1] + pd.Timedelta(days=1), periods=horizon, freq="D")
    history_days = min(len(y), 120)
    details = {
        "product": {"id": product.id, "sku": product.sku, "name": product.name},
        "store": {"id": store.id, "code": store.code, "name": store.name} if store else None,
        "horizon": horizon,
        "eval_window_days": E,
        "splits": {
            "train": [y_train.index[0].date().isoformat(), y_train.index[-1].date().isoformat()],
            "validation": [y_val.index[0].date().isoformat(), y_val.index[-1].date().isoformat()],
            "test": [y_test.index[0].date().isoformat(), y_test.index[-1].date().isoformat()],
        },
        "selection_metric": "validation WAPE (lowest wins; RMSE breaks ties)",
        "best_model": best,
        "best_model_label": MODEL_LABELS[best],
        "models": [
            {"name": name, "label": MODEL_LABELS[name], "is_selected": name == best,
             "validation": {k: _r(v) for k, v in val_scores[name].items() if k != "mape_note"},
             "test": {k: _r(v) for k, v in test_scores.get(name, {}).items() if k != "mape_note"},
             "mape_note": val_scores[name].get("mape_note") or test_scores.get(name, {}).get("mape_note")}
            for name in val_scores
        ],
        "history": [{"date": d.date().isoformat(), "actual": float(v)} for d, v in y.iloc[-history_days:].items()],
        "backtest": [
            {"date": d.date().isoformat(), "actual": float(a),
             **{name: _r(p[i], 2) for name, p in test_preds.items()}}
            for i, (d, a) in enumerate(y_test.items())
        ],
        "forecast": [{"date": d.date().isoformat(), "predicted": _r(p, 2), "lower": _r(lo, 2), "upper": _r(hi, 2)}
                     for d, p, lo, hi in zip(future_dates, pred, lower, upper, strict=True)],
        "interval": {"coverage": coverage, "method": "Empirical quantiles of the selected model's errors on the "
                     f"validation + test windows ({len(resid)} days)."},
        "summary": {
            "total_predicted_units": _r(pred.sum(), 1),
            "avg_daily_units": _r(pred.mean(), 2),
            "recent_avg_daily_units": _r(y.iloc[-28:].mean(), 2),
            "change_vs_recent_pct": _r((pred.mean() - y.iloc[-28:].mean()) / y.iloc[-28:].mean() * 100, 1)
            if y.iloc[-28:].mean() > 0 else None,
        },
        "shap": shap_info,
        "assumptions": [
            "Future holidays follow the standard US event calendar; SNAP days follow the state's monthly pattern.",
            "Future prices are taken from the price table when available, otherwise the last known weekly price.",
            "Tree models forecast recursively, re-using their own predictions as lag inputs for later days.",
        ],
        "runtime_seconds": None,
    }
    details["runtime_seconds"] = round(time.time() - t0, 2)

    run = ForecastRun(product_id=product.id, store_id=store.id if store else None, horizon_days=horizon,
                      best_model=best, train_start=y.index[0].date(), train_end=y.index[-1].date(),
                      details=details, created_by=user_id)
    db.add(run)
    db.flush()
    for name in val_scores:
        for split, scores in (("validation", val_scores[name]), ("test", test_scores.get(name))):
            if scores:
                db.add(ModelEvaluation(run_id=run.id, model_name=name, split=split, mae=scores["mae"],
                                       rmse=scores["rmse"], mape=scores["mape"], wape=scores["wape"], bias=scores["bias"]))
    for row in details["forecast"]:
        db.add(Forecast(run_id=run.id, date=date.fromisoformat(row["date"]), predicted_units=row["predicted"],
                        lower_units=row["lower"], upper_units=row["upper"]))
    db.commit()
    try:
        joblib.dump(final, settings.MODEL_DIR / f"forecast_run_{run.id}_{best}.joblib")
    except Exception as e:  # noqa: BLE001 - persisting the model is a convenience, not essential
        log.warning("Could not save model: %s", e)
    log.info("Forecast run %s: product=%s store=%s best=%s in %.1fs", run.id, product.sku,
             store.code if store else "ALL", best, details["runtime_seconds"])
    return {"run_id": run.id, "created_at": run.created_at, **details}
