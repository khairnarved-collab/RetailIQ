"""
SHAP explanations for the tree-based forecasting models.

SHAP (SHapley Additive exPlanations) splits each prediction into
contributions from every feature: prediction = base value + sum(contributions).
We report
  * global importance: mean |SHAP| over recent training days + forecast days
  * the drivers of the first forecast day (positive = pushes demand up)

If the selected model is not tree-based (naive, moving average, smoothing),
it has no features to explain, so we explain the better of the two tree
models instead and say so clearly.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from app.forecasting.features import FEATURE_LABELS, FEATURES
from app.forecasting.models import MODEL_LABELS, RandomForestModel, XGBoostModel

log = logging.getLogger(__name__)


def explain(final_model, y: pd.Series, cal: pd.DataFrame, fut_cal: pd.DataFrame, horizon: int,
            best: str, val_scores: dict) -> dict | None:
    try:
        import shap
    except ImportError:  # pragma: no cover
        return None
    try:
        model = final_model
        note = None
        if not getattr(final_model, "is_ml", False):
            tree_names = [n for n in ("xgboost", "random_forest") if n in val_scores]
            if not tree_names:
                return None
            pick = min(tree_names, key=lambda n: val_scores[n]["wape"] or 1e9)
            cls = XGBoostModel if pick == "xgboost" else RandomForestModel
            model = cls().fit(y, cal)
            model.predict(horizon, fut_cal)
            note = (f"The selected model ({MODEL_LABELS[best]}) does not use features, so these explanations are "
                    f"from the best tree model ({MODEL_LABELS[pick]}). They describe what drives demand in the data.")
        X_bg = model.X_train.tail(120 if model.name == "random_forest" else 240)
        X_all = pd.concat([X_bg, model.X_future])
        explainer = shap.TreeExplainer(model.model)
        values = np.asarray(explainer.shap_values(X_all.to_numpy()))
        mean_abs = np.abs(values).mean(axis=0)
        order = np.argsort(mean_abs)[::-1]
        total = mean_abs.sum() or 1
        importance = [{"feature": FEATURES[i], "label": FEATURE_LABELS[FEATURES[i]],
                       "mean_abs_shap": round(float(mean_abs[i]), 4), "share_pct": round(float(mean_abs[i] / total * 100), 1)}
                      for i in order[:12]]
        first = values[len(X_bg)]
        x_first = model.X_future.iloc[0]
        f_order = np.argsort(np.abs(first))[::-1][:8]
        base = explainer.expected_value
        base = float(np.ravel(base)[0])
        first_day = [{"feature": FEATURES[i], "label": FEATURE_LABELS[FEATURES[i]],
                      "value": round(float(x_first.iloc[i]), 3), "contribution": round(float(first[i]), 3)}
                     for i in f_order]
        top3 = ", ".join(f["label"].lower() for f in importance[:3])
        is_xgb_tweedie = model.name == "xgboost"
        return {
            "model": model.name, "model_label": MODEL_LABELS[model.name], "note": note,
            "importance": importance,
            "first_forecast_day": {"date": model.X_future.index[0].date().isoformat(), "base_value": round(base, 3),
                                   "contributions": first_day,
                                   "scale": "log scale (Tweedie link)" if is_xgb_tweedie else "units"},
            "summary": (f"The strongest drivers of the forecast are {top3}. "
                        "SHAP shows association within the model, not proof of cause and effect."),
        }
    except Exception as e:  # noqa: BLE001 - explanations are optional
        log.warning("SHAP explanation failed: %s", e)
        return None
