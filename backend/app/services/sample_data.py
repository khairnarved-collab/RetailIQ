"""
Synthetic demonstration data generator.

╔══════════════════════════════════════════════════════════════════════════╗
║  EVERYTHING THIS MODULE PRODUCES IS SYNTHETIC (computer-generated) DATA. ║
║  It is NOT real Walmart / M5 data and must never be presented as such.   ║
╚══════════════════════════════════════════════════════════════════════════╝

Why it exists: the real M5 dataset is behind a Kaggle login and is ~450 MB,
so the project ships with a small dataset in the *exact same file format*
(sales_train_*.csv in wide format, calendar.csv, sell_prices.csv). The very
same ingestion pipeline (`app.services.m5_ingestion`) loads either one, so
swapping in the real M5 files later needs no code changes.

The demand simulation deliberately contains realistic, learnable structure:
  * weekly seasonality (weekends busier, different by category)
  * yearly seasonality (e.g. hobbies peak in December)
  * long-term trends (some products grow, some decline, one is launched later)
  * holiday / event effects and closed stores on Christmas Day (as in M5)
  * SNAP benefit days lifting FOODS sales in the matching state (as in M5)
  * price promotions with price elasticity of demand
  * negative-binomial noise (over-dispersed counts, like real retail sales)

It also writes two independent sample files:
  * customer_transactions_synthetic.csv - for the customer analytics module
  * messy_sales_sample.csv - small file with deliberate quality problems,
    for trying the upload + data-cleaning pipeline.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

START = date(2024, 11, 1)
N_DAYS = 730  # two full years -> 2024-11-01 .. 2026-10-31

STORES = {  # code: (state, size multiplier, display name)
    "CA_1": ("CA", 1.25, "Los Angeles Central"), "CA_2": ("CA", 0.95, "San Diego Harbor"),
    "CA_3": ("CA", 1.45, "San Francisco Bay"), "CA_4": ("CA", 0.70, "Fresno Valley"),
    "TX_1": ("TX", 1.00, "Houston Galleria"), "TX_2": ("TX", 1.15, "Dallas Uptown"),
    "TX_3": ("TX", 0.90, "Austin Hills"),
    "WI_1": ("WI", 0.85, "Milwaukee Lakeside"), "WI_2": ("WI", 1.05, "Madison Capitol"),
    "WI_3": ("WI", 0.80, "Green Bay North"),
}

# item_id, display name, base price, base daily units (per avg store), trend
# trend: flat | grow | decline | launch (starts selling later) | late_decline
ITEMS = [
    ("FOODS_1_001", "Whole Milk 1 gal", 3.48, 9.0, "flat"),
    ("FOODS_1_002", "Large Brown Eggs 12ct", 2.98, 7.0, "grow"),
    ("FOODS_1_003", "Sourdough Bread", 3.97, 5.0, "flat"),
    ("FOODS_1_004", "Greek Yogurt 32oz", 4.68, 3.5, "grow"),
    ("FOODS_2_001", "Basmati Rice 5lb", 6.97, 2.5, "flat"),
    ("FOODS_2_002", "Pasta Penne 1lb", 1.28, 6.0, "flat"),
    ("FOODS_2_003", "Organic Peanut Butter", 5.48, 2.0, "late_decline"),
    ("FOODS_2_004", "Canned Black Beans", 0.98, 5.5, "flat"),
    ("FOODS_3_001", "Bananas (per lb)", 0.58, 14.0, "flat"),
    ("FOODS_3_002", "Fresh Strawberries 1lb", 3.24, 4.5, "flat"),
    ("FOODS_3_003", "Chicken Breast 2lb", 7.94, 4.0, "grow"),
    ("FOODS_3_004", "Ground Coffee 12oz", 8.98, 2.8, "decline"),
    ("FOODS_3_005", "Sparkling Water 12pk", 4.98, 5.0, "launch"),
    ("FOODS_3_006", "Potato Chips Family Size", 3.98, 6.5, "flat"),
    ("HOUSEHOLD_1_001", "Paper Towels 6 Roll", 7.97, 3.0, "flat"),
    ("HOUSEHOLD_1_002", "Laundry Detergent 92oz", 11.97, 1.8, "decline"),
    ("HOUSEHOLD_1_003", "Dish Soap 24oz", 2.97, 2.6, "flat"),
    ("HOUSEHOLD_1_004", "Trash Bags 40ct", 9.47, 1.6, "grow"),
    ("HOUSEHOLD_2_001", "LED Light Bulbs 4pk", 8.88, 1.1, "flat"),
    ("HOUSEHOLD_2_002", "Storage Bins Set", 14.97, 0.7, "flat"),
    ("HOUSEHOLD_2_003", "Bath Towel Cotton", 9.97, 0.8, "late_decline"),
    ("HOUSEHOLD_2_004", "Air Freshener Spray", 3.47, 1.5, "flat"),
    ("HOBBIES_1_001", "Acrylic Paint Set", 12.97, 0.9, "grow"),
    ("HOBBIES_1_002", "Jigsaw Puzzle 1000pc", 11.48, 0.8, "flat"),
    ("HOBBIES_1_003", "Board Game Classic", 19.97, 0.6, "flat"),
    ("HOBBIES_1_004", "Yarn Bundle", 7.97, 0.7, "decline"),
    ("HOBBIES_2_001", "Kids Craft Kit", 9.97, 0.8, "flat"),
    ("HOBBIES_2_002", "Model Car Kit", 24.97, 0.35, "flat"),
    ("HOBBIES_2_003", "Sketchbook A4", 5.97, 1.0, "grow"),
    ("HOBBIES_2_004", "Party Balloons 50ct", 4.47, 0.9, "flat"),
]

SUPPLIERS = [
    ("FreshFarm Distributors", "orders@freshfarm.example", 3),
    ("Pantry Wholesale Inc.", "supply@pantrywholesale.example", 7),
    ("HomeGoods Supply Co.", "sales@homegoods-supply.example", 10),
    ("CraftWorld Trading", "b2b@craftworld.example", 14),
    ("Metro Beverage Group", "orders@metrobev.example", 5),
]

# Day-of-week multipliers (Mon..Sun) per category
DOW = {
    "FOODS": [0.88, 0.85, 0.86, 0.90, 1.05, 1.25, 1.21],
    "HOUSEHOLD": [0.92, 0.90, 0.90, 0.93, 1.02, 1.20, 1.13],
    "HOBBIES": [0.82, 0.80, 0.82, 0.88, 1.05, 1.36, 1.27],
}

SNAP_DAYS = {  # day-of-month on which SNAP benefits are paid (pattern as in M5)
    "CA": set(range(1, 11)),
    "TX": {1, 3, 5, 6, 7, 9, 11, 12, 13, 15},
    "WI": {2, 3, 5, 6, 8, 9, 11, 12, 14, 15},
}


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-th given weekday of a month (n=-1 for last)."""
    if n > 0:
        d = date(year, month, 1)
        d += timedelta(days=(weekday - d.weekday()) % 7)
        return d + timedelta(weeks=n - 1)
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    d = nxt - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _easter(year: int) -> date:
    """Anonymous Gregorian algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = (h + l_ - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def build_events(years: list[int]) -> dict[date, tuple[str, str]]:
    """Event calendar using the same event types as M5: National, Religious, Cultural, Sporting."""
    ev: dict[date, tuple[str, str]] = {}
    for y in years:
        ev[date(y, 1, 1)] = ("NewYear", "National")
        ev[_nth_weekday(y, 1, 0, 3)] = ("MartinLutherKingDay", "National")
        ev[_nth_weekday(y, 2, 6, 2)] = ("SuperBowl", "Sporting")
        ev[date(y, 2, 14)] = ("ValentinesDay", "Cultural")
        ev[_nth_weekday(y, 2, 0, 3)] = ("PresidentsDay", "National")
        ev[_easter(y)] = ("Easter", "Cultural")
        ev[_nth_weekday(y, 5, 6, 2)] = ("Mother's day", "Cultural")
        ev[_nth_weekday(y, 5, 0, -1)] = ("MemorialDay", "National")
        ev[_nth_weekday(y, 6, 6, 3)] = ("Father's day", "Cultural")
        ev[date(y, 7, 4)] = ("IndependenceDay", "National")
        ev[_nth_weekday(y, 9, 0, 1)] = ("LaborDay", "National")
        ev[date(y, 10, 31)] = ("Halloween", "Cultural")
        ev[date(y, 11, 11)] = ("VeteransDay", "National")
        ev[_nth_weekday(y, 11, 3, 4)] = ("Thanksgiving", "National")
        ev[date(y, 12, 25)] = ("Christmas", "National")
    return ev


EVENT_LIFT = {  # multiplier on the event day, per category
    "SuperBowl": {"FOODS": 1.35, "HOUSEHOLD": 1.0, "HOBBIES": 1.05},
    "ValentinesDay": {"FOODS": 1.10, "HOUSEHOLD": 1.0, "HOBBIES": 1.25},
    "Easter": {"FOODS": 1.15, "HOUSEHOLD": 1.0, "HOBBIES": 1.20},
    "IndependenceDay": {"FOODS": 1.30, "HOUSEHOLD": 1.05, "HOBBIES": 1.10},
    "Halloween": {"FOODS": 1.15, "HOUSEHOLD": 1.05, "HOBBIES": 1.45},
    "Thanksgiving": {"FOODS": 0.75, "HOUSEHOLD": 0.7, "HOBBIES": 0.7},  # stores busy the days before
    "NewYear": {"FOODS": 0.80, "HOUSEHOLD": 0.75, "HOBBIES": 0.75},
}


def wm_week_id(d: date) -> int:
    """M5-style fiscal week id (weeks start on Saturday), e.g. 12447."""
    anchor = date(2011, 1, 29)  # first Saturday of the M5 calendar (wm_yr_wk 11101)
    weeks = (d - anchor).days // 7
    year_idx, week = divmod(weeks, 52)
    return 11101 + year_idx * 100 + week


def _trend_factor(kind: str, t: np.ndarray) -> np.ndarray:
    """t = 0..1 over the 2-year horizon."""
    if kind == "grow":
        return 0.75 + 0.6 * t
    if kind == "decline":
        return 1.25 - 0.6 * t
    if kind == "late_decline":  # stable, then a sharp drop over the final ~2 months
        return np.where(t < 0.9, 1.0, 1.0 - 4.5 * (t - 0.9))
    if kind == "launch":  # new product launched ~7 months in, ramps up
        start = 0.3
        return np.where(t < start, 0.0, np.clip((t - start) / 0.12, 0, 1) * (1.0 + 0.3 * (t - start)))
    return np.ones_like(t)


def _yearly(cat: str, doy: np.ndarray) -> np.ndarray:
    rad = 2 * np.pi * doy / 365.25
    if cat == "HOBBIES":   # strong December (holiday gifting) peak
        return 1 + 0.18 * np.cos(rad) + 0.35 * np.exp(-((doy - 352) ** 2) / (2 * 12 ** 2))
    if cat == "HOUSEHOLD":  # spring cleaning bump
        return 1 + 0.12 * np.exp(-((doy - 100) ** 2) / (2 * 25 ** 2)) + 0.05 * np.cos(rad)
    return 1 + 0.07 * np.cos(rad - 3.6)  # FOODS: mild summer peak


def generate(out_dir: Path, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    dates = [START + timedelta(days=i) for i in range(N_DAYS)]
    dates_np = pd.to_datetime(dates)
    years = sorted({d.year for d in dates})
    events = build_events(years)

    # ---- calendar.csv (M5 schema)
    cal = pd.DataFrame({
        "date": [d.isoformat() for d in dates],
        "wm_yr_wk": [wm_week_id(d) for d in dates],
        "weekday": [d.strftime("%A") for d in dates],
        "wday": [((d.weekday() + 2) % 7) + 1 for d in dates],  # M5: Saturday=1
        "month": [d.month for d in dates],
        "year": [d.year for d in dates],
        "d": [f"d_{i + 1}" for i in range(N_DAYS)],
        "event_name_1": [events.get(d, (None, None))[0] for d in dates],
        "event_type_1": [events.get(d, (None, None))[1] for d in dates],
        "event_name_2": [None] * N_DAYS,
        "event_type_2": [None] * N_DAYS,
        "snap_CA": [int(d.day in SNAP_DAYS["CA"]) for d in dates],
        "snap_TX": [int(d.day in SNAP_DAYS["TX"]) for d in dates],
        "snap_WI": [int(d.day in SNAP_DAYS["WI"]) for d in dates],
    })
    cal.to_csv(out_dir / "calendar.csv", index=False)

    t = np.arange(N_DAYS) / (N_DAYS - 1)
    doy = dates_np.dayofyear.to_numpy()
    dow = dates_np.dayofweek.to_numpy()
    weeks = cal["wm_yr_wk"].to_numpy()
    uniq_weeks = np.unique(weeks)
    christmas = np.array([d.month == 12 and d.day == 25 for d in dates])
    # Days just before Thanksgiving / Christmas are busy
    pre_holiday = np.zeros(N_DAYS)
    for i, d in enumerate(dates):
        for off, lift in ((1, 1.45), (2, 1.25), (3, 1.12)):
            nd = d + timedelta(days=off)
            if nd in events and events[nd][0] in ("Thanksgiving", "Christmas"):
                pre_holiday[i] = max(pre_holiday[i], lift)
    pre_holiday[pre_holiday == 0] = 1.0

    sales_rows, price_rows, names, inv_rows = [], [], [], []
    supplier_for_dept = {"FOODS_1": 0, "FOODS_2": 1, "FOODS_3": 0, "HOUSEHOLD_1": 2,
                         "HOUSEHOLD_2": 2, "HOBBIES_1": 3, "HOBBIES_2": 3}

    for item_id, name, base_price, base_units, trend in ITEMS:
        cat = item_id.split("_")[0]
        dept = "_".join(item_id.split("_")[:2])
        names.append({"item_id": item_id, "item_name": name, "dept_id": dept, "cat_id": cat})
        elasticity = rng.uniform(-2.0, -1.0)
        event_lift = np.array([EVENT_LIFT.get(events.get(d, ("", ""))[0], {}).get(cat, 1.0) for d in dates])
        tr = _trend_factor(trend, t)
        if item_id == "FOODS_3_005":  # the launched product uses its own supplier
            sup_idx = 4
        else:
            sup_idx = supplier_for_dept[dept]

        for store, (state, size, _) in STORES.items():
            store_pref = rng.lognormal(0, 0.15)  # store-specific affinity for this item
            # weekly price path: base price, occasional 1-week promos, one price change
            change_week = rng.choice(uniq_weeks[20:-20])
            change = rng.choice([1.0, 1.0, 1.06, 1.10, 0.95])
            wk_price = {}
            for w in uniq_weeks:
                p = base_price * (change if w >= change_week else 1.0)
                if rng.random() < 0.08:  # promotion week
                    p *= rng.uniform(0.70, 0.88)
                wk_price[w] = round(p, 2)
            launched = tr > 0
            for w in uniq_weeks:
                # like M5: no price row before a product is on sale
                if launched[weeks == w].any():
                    price_rows.append({"store_id": store, "item_id": item_id, "wm_yr_wk": int(w),
                                       "sell_price": wk_price[w]})
            price = np.array([wk_price[w] for w in weeks])
            reg_price = base_price * np.where(weeks >= change_week, change, 1.0)
            price_effect = (price / reg_price) ** elasticity
            snap = np.array([d.day in SNAP_DAYS[state] for d in dates]) if cat == "FOODS" else np.zeros(N_DAYS, bool)
            lam = (base_units * size * store_pref
                   * np.array(DOW[cat])[dow] * _yearly(cat, doy) * tr * event_lift * pre_holiday
                   * np.where(snap, 1.14, 1.0) * price_effect)
            lam = np.clip(lam, 0, None)
            # Negative binomial = Poisson with gamma-distributed rate (over-dispersion)
            shape = 4.0
            rate = rng.gamma(shape, lam / shape) if lam.any() else lam
            units = rng.poisson(rate)
            units[christmas] = 0  # stores closed on Christmas Day (as in M5)
            sales_rows.append({"id": f"{item_id}_{store}_evaluation", "item_id": item_id, "dept_id": dept,
                               "cat_id": cat, "store_id": store, "state_id": state,
                               **{f"d_{i + 1}": int(u) for i, u in enumerate(units)}})

            # current stock position at the end of the data (synthetic):
            recent = units[-28:].mean()
            days_cover = rng.choice([2, 4, 6, 9, 14, 18, 24, 30, 45, 90, 120],
                                    p=[.06, .08, .10, .12, .16, .14, .12, .08, .06, .05, .03])
            lead = SUPPLIERS[sup_idx][2]
            inv_rows.append({"store_id": store, "item_id": item_id, "on_hand": int(round(recent * days_cover)),
                             "supplier": SUPPLIERS[sup_idx][0], "lead_time_days": lead,
                             "unit_cost": round(base_price * rng.uniform(0.55, 0.72), 2),
                             "service_level": 0.95})

    pd.DataFrame(sales_rows).to_csv(out_dir / "sales_train_synthetic.csv", index=False)
    pd.DataFrame(price_rows).to_csv(out_dir / "sell_prices.csv", index=False)
    pd.DataFrame(names).to_csv(out_dir / "item_names.csv", index=False)
    pd.DataFrame(inv_rows).to_csv(out_dir / "inventory_synthetic.csv", index=False)
    pd.DataFrame([{"supplier": s, "contact_email": e, "default_lead_time_days": lt} for s, e, lt in SUPPLIERS]
                 ).to_csv(out_dir / "suppliers_synthetic.csv", index=False)
    stores_df = pd.DataFrame([{"store_id": k, "state_id": v[0], "store_name": v[2]} for k, v in STORES.items()])
    stores_df.to_csv(out_dir / "stores.csv", index=False)

    meta = {
        "synthetic": True,
        "description": "SYNTHETIC demonstration data in M5 file format. Not real Walmart data.",
        "generator": "backend/app/services/sample_data.py",
        "seed": seed, "start_date": START.isoformat(), "days": N_DAYS,
        "stores": len(STORES), "items": len(ITEMS),
    }
    (out_dir / "DATASET_INFO.json").write_text(json.dumps(meta, indent=2))
    return meta


# ---------------------------------------------------------------------------
# Customer transactions (independent synthetic dataset for the RFM module)
# ---------------------------------------------------------------------------
def generate_customers(path: Path, seed: int = 7, n_customers: int = 1200) -> int:
    rng = np.random.default_rng(seed)
    end = START + timedelta(days=N_DAYS - 1)
    cities = ["Los Angeles", "San Diego", "San Francisco", "Houston", "Dallas", "Austin", "Milwaukee", "Madison"]
    cats = ["FOODS", "HOUSEHOLD", "HOBBIES"]
    rows = []
    order_no = 100000
    # behaviour archetypes -> produce a realistic spread of RFM segments
    archetypes = [("champion", .12), ("loyal", .18), ("regular", .25), ("new", .12),
                  ("at_risk", .15), ("lost", .18)]
    names, probs = zip(*archetypes, strict=True)
    for c in range(n_customers):
        kind = rng.choice(names, p=probs)
        cid = f"C{c + 1:05d}"
        city = rng.choice(cities)
        if kind == "champion":
            first, last, n, spend = rng.integers(0, 200), N_DAYS - rng.integers(0, 15), rng.integers(25, 60), 70
        elif kind == "loyal":
            first, last, n, spend = rng.integers(0, 300), N_DAYS - rng.integers(5, 45), rng.integers(12, 30), 50
        elif kind == "regular":
            first, last, n, spend = rng.integers(0, 400), N_DAYS - rng.integers(10, 120), rng.integers(4, 12), 40
        elif kind == "new":
            first, last = N_DAYS - rng.integers(10, 60), N_DAYS - rng.integers(0, 10)
            n, spend = rng.integers(1, 3), 45
        elif kind == "at_risk":
            first, last, n, spend = rng.integers(0, 250), N_DAYS - rng.integers(120, 260), rng.integers(8, 25), 55
        else:  # lost
            first, last, n, spend = rng.integers(0, 200), N_DAYS - rng.integers(300, 520), rng.integers(1, 5), 30
        first, last = int(min(first, last)), int(max(first, last))
        days = np.sort(rng.integers(first, last + 1, size=int(n)))
        days[-1] = last
        for d in days:
            order_no += 1
            n_lines = rng.integers(1, 4)
            for _ in range(n_lines):
                qty = int(rng.integers(1, 6))
                amount = round(float(rng.gamma(3.0, spend / 3.0 / n_lines)), 2)
                rows.append({
                    "order_id": f"ORD{order_no}", "customer_id": cid,
                    "order_date": (START + timedelta(days=int(d))).isoformat(),
                    "amount": max(amount, 0.99), "quantity": qty,
                    "category": rng.choice(cats, p=[.6, .25, .15]), "store": rng.choice(list(STORES)),
                    "city": city,
                })
    df = pd.DataFrame(rows)
    df = df[pd.to_datetime(df.order_date) <= pd.Timestamp(end)]
    df.to_csv(path, index=False)
    return len(df)


def generate_messy_sales(path: Path, seed: int = 3) -> int:
    """Small long-format sales file with deliberate data-quality problems."""
    rng = np.random.default_rng(seed)
    rows = []
    stores = ["CA_1", "TX_1", "WI_1"]
    items = [i[0] for i in ITEMS[:8]]
    for _ in range(420):
        d = START + timedelta(days=int(rng.integers(600, N_DAYS)))
        item = rng.choice(items)
        units = int(rng.poisson(6))
        price = next(p for (iid, _, p, _, _) in ITEMS if iid == item)
        rows.append({" Sale Date ": d.isoformat(), "Store ID": rng.choice(stores), "Item-ID": item,
                     "Units Sold": units, "Unit Price": price, "Category": item.split("_")[0]})
    df = pd.DataFrame(rows)
    # inject problems so the cleaning pipeline has something to report
    df.loc[5:9, "Units Sold"] = np.nan                       # missing values
    df.loc[12, "Units Sold"] = -4                            # invalid negative quantity
    df.loc[15, " Sale Date "] = "not a date"                 # unparsable date
    df.loc[18, "Store ID"] = None                            # missing required field
    df["Unit Price"] = df["Unit Price"].astype(object)
    df.loc[20:24, "Unit Price"] = df.loc[20:24, "Unit Price"].map(lambda p: f"${p}")  # numbers stored as text
    df.loc[30, "Units Sold"] = 480                           # extreme outlier
    df.loc[40, "Category"] = " foods "                       # inconsistent text
    df = pd.concat([df, df.iloc[50:58]], ignore_index=True)  # exact duplicate rows
    df.to_csv(path, index=False)
    return len(df)


def main() -> None:  # pragma: no cover - CLI helper
    from app.core.config import settings
    ap = argparse.ArgumentParser(description="Generate the SYNTHETIC demo datasets")
    ap.add_argument("--out", type=Path, default=settings.SAMPLE_DIR)
    args = ap.parse_args()
    meta = generate(args.out / "m5_synthetic")
    n_c = generate_customers(args.out / "customer_transactions_synthetic.csv")
    n_m = generate_messy_sales(args.out / "messy_sales_sample.csv")
    print(json.dumps({**meta, "customer_rows": n_c, "messy_rows": n_m}, indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
