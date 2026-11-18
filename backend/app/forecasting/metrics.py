"""
Forecast accuracy metrics.

MAE   mean absolute error (units)              - easy to explain
RMSE  root mean squared error (units)          - punishes large misses
MAPE  mean absolute percentage error           - ONLY over days with actual > 0, and
      only reported when at most 10% of days are zero; with many zero days MAPE is
      undefined / misleading, so it is returned as None.
WAPE  sum|error| / sum(actual)                 - robust percentage error for retail
Bias  sum(forecast - actual) / sum(actual)     - >0 = over-forecasting, <0 = under-forecasting
"""
from __future__ import annotations

import numpy as np


def evaluate(actual, pred) -> dict:
    a = np.asarray(actual, dtype=float)
    p = np.asarray(pred, dtype=float)
    err = p - a
    total = a.sum()
    nz = a > 0
    mape = None
    mape_note = None
    if nz.mean() >= 0.9 and nz.sum() > 0:
        mape = float(np.mean(np.abs(err[nz]) / a[nz]) * 100)
    else:
        mape_note = f"MAPE not reported: {int((~nz).sum())} of {len(a)} days have zero sales"
    return {
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err ** 2))),
        "mape": mape,
        "wape": float(np.abs(err).sum() / total * 100) if total > 0 else None,
        "bias": float(err.sum() / total * 100) if total > 0 else None,
        "mape_note": mape_note,
    }
