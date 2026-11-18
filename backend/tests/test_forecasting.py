"""Forecasting: metrics, leakage-free features, time-based splits and the full pipeline."""
import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select

from app.forecasting.features import (
    FEATURES,
    _calendar_block,
    build_training_frame,
    features_for_next_day,
)
from app.forecasting.metrics import evaluate
from app.forecasting.models import MovingAverage, SeasonalNaive
from app.forecasting.pipeline import ForecastError, run_forecast
from app.models import Product, Store


def test_metrics_known_values():
    m = evaluate([10, 20, 30], [12, 18, 33])
    assert m["mae"] == pytest.approx(7 / 3)
    assert m["rmse"] == pytest.approx(np.sqrt((4 + 4 + 9) / 3))
    assert m["wape"] == pytest.approx(7 / 60 * 100)
    assert m["bias"] == pytest.approx(3 / 60 * 100)
    assert m["mape"] == pytest.approx(np.mean([2 / 10, 2 / 20, 3 / 30]) * 100)


def test_mape_not_reported_with_many_zeros():
    m = evaluate([0, 0, 5, 0], [1, 0, 4, 1])
    assert m["mape"] is None and "zero" in m["mape_note"]


def _toy():
    idx = pd.date_range("2025-01-01", periods=80, freq="D")
    y = pd.Series(np.arange(80, dtype=float), index=idx)
    exog = pd.DataFrame({"event_type": [None] * 80, "snap": 0.0, "price": 2.0}, index=idx)
    return y, _calendar_block(exog)


def test_features_do_not_leak_the_target():
    y, cal = _toy()
    fr = build_training_frame(y, cal)
    row = fr.iloc[0]
    t = fr.index[0]
    assert row["lag_1"] == y[t - pd.Timedelta(days=1)]
    # rolling mean of the 7 days BEFORE t (t itself excluded)
    assert row["roll_mean_7"] == pytest.approx(y[t - pd.Timedelta(days=7): t - pd.Timedelta(days=1)].mean())
    assert "target" in fr and row["target"] == y[t]


def test_recursive_features_match_training_features():
    y, cal = _toy()
    fr = build_training_frame(y, cal)
    t = fr.index[-1]
    hist = y[:t - pd.Timedelta(days=1)].to_numpy()
    x = features_for_next_day(hist, cal.loc[t])
    assert np.allclose(x, fr.loc[t, FEATURES].to_numpy(dtype=float))


def test_baselines():
    y, cal = _toy()
    assert np.allclose(SeasonalNaive().fit(y, cal).predict(7, cal), y.iloc[-7:].to_numpy())
    assert np.allclose(MovingAverage().fit(y, cal).predict(3, cal), y.iloc[-28:].mean())


def test_full_pipeline_time_splits_and_outputs(db):
    p = db.scalar(select(Product).where(Product.sku == "FOODS_1_001"))
    s = db.scalar(select(Store).where(Store.code == "CA_1"))
    r = run_forecast(db, p.id, s.id, 14)
    sp = r["splits"]
    # train < validation < test, no overlap (time-based, not random)
    assert sp["train"][1] < sp["validation"][0] <= sp["validation"][1] < sp["test"][0]
    assert len(r["forecast"]) == 14
    assert r["forecast"][0]["date"] > sp["test"][1]
    names = {m["name"] for m in r["models"]}
    assert {"seasonal_naive", "moving_average", "exp_smoothing", "random_forest", "xgboost"} <= names
    assert sum(m["is_selected"] for m in r["models"]) == 1
    best = next(m for m in r["models"] if m["is_selected"])
    # selection really is the lowest validation WAPE
    assert best["validation"]["wape"] == min(m["validation"]["wape"] for m in r["models"])
    for f in r["forecast"]:
        assert f["predicted"] >= 0 and f["lower"] <= f["upper"]
    assert r["shap"] and r["shap"]["importance"]


def test_all_stores_forecast_and_bad_horizon(db):
    p = db.scalar(select(Product).where(Product.sku == "FOODS_3_003"))
    r = run_forecast(db, p.id, None, 7)
    assert r["store"] is None and len(r["forecast"]) == 7
    with pytest.raises(ForecastError):
        run_forecast(db, p.id, None, 10)


def test_forecast_api_and_download(client, analyst_headers, db):
    p = db.scalar(select(Product).where(Product.sku == "HOUSEHOLD_1_001"))
    r = client.post("/api/forecasting/run", headers=analyst_headers, json={"product_id": p.id, "horizon": 30})
    assert r.status_code == 200, r.text
    run_id = r.json()["run_id"]
    d = client.get(f"/api/forecasting/runs/{run_id}/download", headers=analyst_headers)
    assert d.status_code == 200 and d.text.count("\n") == 31  # header + 30 days
    assert client.post("/api/forecasting/run", headers=analyst_headers,
                       json={"product_id": p.id, "horizon": 9}).status_code == 422
