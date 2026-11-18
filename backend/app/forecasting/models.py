"""
Candidate forecasting models, all with the same tiny interface:

    model.fit(y_train: pd.Series, cal: pd.DataFrame)     # cal = calendar/price features for all days
    model.predict(horizon, cal_future) -> np.ndarray     # multi-step forecast after the training end

1. SeasonalNaive       - "same weekday last week" (the standard naive baseline for daily retail data)
2. MovingAverage       - flat forecast = mean of the last 28 days
3. ExpSmoothing        - Holt-Winters: damped additive trend + weekly seasonality (statsmodels)
4. RandomForestModel   - scikit-learn RandomForestRegressor on lag / calendar / price features
5. XGBoostModel        - gradient-boosted trees (Tweedie objective, well suited to sparse retail counts)

The tree models forecast RECURSIVELY: predict day t+1, add it to the history,
rebuild the lag features, predict t+2, and so on. This is how the model will
actually be used, so it is also how it is evaluated.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from app.forecasting.features import (
    FEATURES,
    build_training_frame,
    features_for_next_day,
)


class BaseModel:
    name = "base"
    label = "Base"
    is_ml = False

    def fit(self, y: pd.Series, cal: pd.DataFrame) -> BaseModel:
        self.history = y.to_numpy(dtype=float)
        return self

    def predict(self, horizon: int, cal_future: pd.DataFrame) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError


class SeasonalNaive(BaseModel):
    name, label = "seasonal_naive", "Naive (same day last week)"

    def predict(self, horizon, cal_future):
        last_week = self.history[-7:]
        return np.array([last_week[i % 7] for i in range(horizon)], dtype=float)


class MovingAverage(BaseModel):
    name, label = "moving_average", "Moving average (28 days)"

    def predict(self, horizon, cal_future):
        return np.repeat(self.history[-28:].mean(), horizon)


class ExpSmoothing(BaseModel):
    name, label = "exp_smoothing", "Exponential smoothing (Holt-Winters)"

    def fit(self, y, cal):
        super().fit(y, cal)
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        y = y.asfreq("D")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                self.model = ExponentialSmoothing(y.iloc[-730:], trend="add", damped_trend=True, seasonal="add",
                                                  seasonal_periods=7, initialization_method="estimated").fit()
            except Exception:  # noqa: BLE001 - e.g. too short: fall back to simple smoothing
                self.model = ExponentialSmoothing(y, initialization_method="estimated").fit()
        return self

    def predict(self, horizon, cal_future):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return np.clip(np.asarray(self.model.forecast(horizon), dtype=float), 0, None)


class _TreeModel(BaseModel):
    is_ml = True

    def _make(self):  # pragma: no cover
        raise NotImplementedError

    def fit(self, y, cal):
        super().fit(y, cal)
        frame = build_training_frame(y, cal)
        self.X_train = frame[FEATURES]
        self.model = self._make()
        self.model.fit(self.X_train.to_numpy(), frame["target"].to_numpy())
        return self

    def predict(self, horizon, cal_future):
        hist = list(self.history)
        preds, rows = [], []
        for i in range(horizon):
            x = features_for_next_day(np.asarray(hist), cal_future.iloc[i])
            p = max(float(self.model.predict(x.reshape(1, -1))[0]), 0.0)
            preds.append(p)
            rows.append(x)
            hist.append(p)
        self.X_future = pd.DataFrame(rows, columns=FEATURES, index=cal_future.index[:horizon])
        return np.array(preds)


class RandomForestModel(_TreeModel):
    name, label = "random_forest", "Random Forest"

    def _make(self):
        from sklearn.ensemble import RandomForestRegressor
        return RandomForestRegressor(n_estimators=200, min_samples_leaf=3, max_features=0.6,
                                     random_state=42, n_jobs=-1)

    def predict(self, horizon, cal_future):
        self.model.n_jobs = 1  # single-row predictions are faster without process overhead
        return super().predict(horizon, cal_future)


class XGBoostModel(_TreeModel):
    name, label = "xgboost", "XGBoost"

    def _make(self):
        from xgboost import XGBRegressor
        # Tweedie loss handles many zero days + right-skewed counts (popular in the M5 competition).
        return XGBRegressor(n_estimators=400, learning_rate=0.04, max_depth=5, subsample=0.8,
                            colsample_bytree=0.8, min_child_weight=3, objective="reg:tweedie",
                            tweedie_variance_power=1.2, random_state=42, n_jobs=2, verbosity=0)


MODEL_CLASSES = [SeasonalNaive, MovingAverage, ExpSmoothing, RandomForestModel, XGBoostModel]
MODEL_LABELS = {m.name: m.label for m in MODEL_CLASSES}
