"""
Application-wide business settings that admins can change in the UI.

Stored as JSON in the `app_settings` table, merged over the defaults below so
new settings work even on an older database.
"""
from __future__ import annotations

import copy

from sqlalchemy.orm import Session

from app.models import AppSetting

DEFAULTS: dict[str, dict] = {
    "general": {
        "company_name": "RetailIQ Demo Retail Co.",
        "currency": "USD",
    },
    "inventory": {
        # Days of history used to estimate average daily demand and its variability
        "demand_window_days": 56,
        "default_lead_time_days": 7,
        "default_service_level": 0.95,
        # Stock covering more than this many days of demand is "Overstocked"
        "overstock_days_of_cover": 60,
    },
    "customers": {
        # Assumptions behind the simple customer-lifetime-value estimate
        "clv_lifespan_years": 3.0,
        "gross_margin": 0.30,
    },
    "forecasting": {
        "default_horizon_days": 30,
        "interval_coverage": 0.80,
    },
}


def get_all(db: Session) -> dict[str, dict]:
    merged = copy.deepcopy(DEFAULTS)
    for row in db.query(AppSetting).all():
        if row.key in merged and isinstance(row.value, dict):
            merged[row.key].update({k: v for k, v in row.value.items() if k in merged[row.key]})
    return merged


def get_section(db: Session, section: str) -> dict:
    return get_all(db)[section]


def update_section(db: Session, section: str, values: dict, user_id: int | None) -> dict:
    if section not in DEFAULTS:
        raise KeyError(section)
    clean: dict = {}
    for k, v in values.items():
        if k not in DEFAULTS[section]:
            continue
        default = DEFAULTS[section][k]
        # keep the same type as the default value (simple validation)
        try:
            clean[k] = type(default)(v)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid value for {section}.{k}") from None
    row = db.get(AppSetting, section)
    if row is None:
        row = AppSetting(key=section, value={})
        db.add(row)
    row.value = {**(row.value or {}), **clean}
    row.updated_by = user_id
    db.commit()
    return get_section(db, section)
