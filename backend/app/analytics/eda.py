"""
Exploratory Data Analysis (EDA).

Works on two kinds of source:
  * "sales"        - the sales warehouse joined with product / store / calendar
                     (one row per store × product × day with sales), sampled to 60k rows
  * "dataset:<id>" - any uploaded dataset (the cleaned version if it exists)

Everything returned - statistics, chart data and the plain-language
findings - is computed from the data at request time.
"""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.money import load_currency, money
from app.models import CalendarDay, Category, Dataset, Product, Sale, Store
from app.services.data_quality import read_table

MAX_ROWS = 60_000


def _sales_frame(db: Session) -> tuple[pd.DataFrame, int]:
    """
    Load a deterministic sample of at most MAX_ROWS sales rows.

    Sampling happens IN THE DATABASE (every k-th row id) so the full table is
    never loaded into memory - important on small cloud instances.
    """
    from sqlalchemy import func
    total = int(db.scalar(select(func.count(Sale.id))) or 0)
    step = max(1, -(-total // MAX_ROWS))  # ceil(total / MAX_ROWS)
    stmt = (select(Sale.date, Store.code, Category.name, Product.name, Sale.units, Sale.unit_price, Sale.revenue,
                   CalendarDay.weekday, CalendarDay.month, CalendarDay.event_name_1, CalendarDay.snap_ca,
                   CalendarDay.snap_tx, CalendarDay.snap_wi, Store.state)
            .join(Store, Store.id == Sale.store_id).join(Product, Product.id == Sale.product_id)
            .join(Category, Category.id == Product.category_id).join(CalendarDay, CalendarDay.date == Sale.date))
    if step > 1:
        stmt = stmt.where(Sale.id % step == 0)
    df = pd.DataFrame(db.execute(stmt).all(), columns=[
        "date", "store", "category", "product", "units", "unit_price", "revenue", "weekday", "month",
        "event", "snap_ca", "snap_tx", "snap_wi", "state"])
    if df.empty:
        return df, total
    df["date"] = pd.to_datetime(df["date"])
    df["is_event"] = df["event"].notna().astype(int)
    df["snap_day"] = np.select([df.state == "CA", df.state == "TX", df.state == "WI"],
                               [df.snap_ca, df.snap_tx, df.snap_wi], 0).astype(int)
    df["is_weekend"] = df["date"].dt.dayofweek.ge(5).astype(int)
    df = df.drop(columns=["snap_ca", "snap_tx", "snap_wi", "event", "state"])
    for c in ("store", "category", "product", "weekday"):  # categoricals use far less memory than strings
        df[c] = df[c].astype("category")
    df["month"] = df["month"].astype("int16")
    return df, total


# One cached frame per data version (version changes whenever sales rows change)
_CACHE: dict[tuple[str, str], pd.DataFrame] = {}


def load_source(db: Session, source: str) -> tuple[pd.DataFrame, dict]:
    if source == "sales":
        from sqlalchemy import func
        version = str(db.scalar(select(func.count(Sale.id)))) + str(db.scalar(select(func.max(Sale.id))))
        key = (source, version)
        if key not in _CACHE:
            _CACHE.clear()
            _CACHE[key] = _sales_frame(db)
        full, total = _CACHE[key]
        meta = {"source": "sales", "label": "Sales warehouse", "total_rows": total,
                "sampled": total > len(full), "rows_used": len(full)}
        return full, meta
    elif source.startswith("dataset:"):
        ds = db.get(Dataset, int(source.split(":", 1)[1]))
        if ds is None:
            raise ValueError("Dataset not found")
        if ds.kind == "m5_sales":
            raise ValueError("M5 source files are explored through the 'Sales warehouse' source")
        path = Path(ds.cleaned_path or ds.file_path)
        full = read_table(path)
        if ds.cleaned_path:
            for c in full.columns:
                if "date" in c:
                    full[c] = pd.to_datetime(full[c], errors="coerce")
        meta = {"source": source, "label": ds.name, "total_rows": len(full), "is_synthetic": ds.is_synthetic,
                "version": "cleaned" if ds.cleaned_path else "raw"}
    else:
        raise ValueError("Unknown source")
    df = full.sample(MAX_ROWS, random_state=0) if len(full) > MAX_ROWS else full
    meta["sampled"] = len(full) > MAX_ROWS
    meta["rows_used"] = len(df)
    return df, meta


def _num_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])
            and df[c].nunique() > 1]


def _f(x, nd=4):
    if x is None:
        return None
    try:
        if pd.isna(x):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(x, (np.integer, int)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return round(float(x), nd)
    if isinstance(x, pd.Timestamp):
        return x.date().isoformat()
    return str(x)


def describe(df: pd.DataFrame) -> dict:
    numeric, categorical = [], []
    for c in df.columns:
        s = df[c]
        if c in _num_cols(df):
            mode = s.mode()
            q = s.quantile([0.25, 0.5, 0.75])
            numeric.append({"column": c, "count": int(s.count()), "missing": int(s.isna().sum()),
                            "mean": _f(s.mean()), "median": _f(s.median()), "mode": _f(mode.iloc[0]) if len(mode) else None,
                            "std": _f(s.std()), "min": _f(s.min()), "q1": _f(q[0.25]), "q2": _f(q[0.5]), "q3": _f(q[0.75]),
                            "max": _f(s.max()), "skewness": _f(s.skew()), "kurtosis": _f(s.kurt())})
        elif pd.api.types.is_datetime64_any_dtype(s):
            categorical.append({"column": c, "type": "date", "count": int(s.count()), "missing": int(s.isna().sum()),
                                "min": _f(s.min()), "max": _f(s.max()), "unique": int(s.nunique())})
        else:
            vc = s.astype(str).where(s.notna()).value_counts()
            categorical.append({"column": c, "type": "text", "count": int(s.count()), "missing": int(s.isna().sum()),
                                "unique": int(s.nunique()), "top": _f(vc.index[0]) if len(vc) else None,
                                "top_freq": int(vc.iloc[0]) if len(vc) else 0, "mode": _f(vc.index[0]) if len(vc) else None})
    return {"numeric": numeric, "categorical": categorical}


def correlation(df: pd.DataFrame, columns: list[str] | None = None) -> dict:
    cols = [c for c in (columns or _num_cols(df)) if c in _num_cols(df)][:15]
    if len(cols) < 2:
        return {"columns": cols, "matrix": []}
    m = df[cols].corr().round(3)
    return {"columns": cols, "matrix": [[_f(v, 3) for v in row] for row in m.to_numpy()]}


def histogram(df: pd.DataFrame, column: str, bins: int = 30) -> dict:
    s = df[column].dropna()
    if s.empty or column not in _num_cols(df):
        raise ValueError("Column is not numeric")
    counts, edges = np.histogram(s, bins=bins)
    return {"column": column, "bins": [{"from": _f(edges[i]), "to": _f(edges[i + 1]), "label": f"{edges[i]:.4g}", "count": int(c)}
                                       for i, c in enumerate(counts)],
            "mean": _f(s.mean()), "median": _f(s.median())}


def box(df: pd.DataFrame, columns: list[str], by: str | None = None) -> list[dict]:
    out = []
    groups = [(c, None, df[c]) for c in columns] if not by else [
        (columns[0], str(g), sub[columns[0]]) for g, sub in df.groupby(by)][:20]
    for c, g, s in groups:
        s = s.dropna()
        if s.empty:
            continue
        q1, med, q3 = s.quantile([0.25, 0.5, 0.75])
        iqr = q3 - q1
        lo_w = s[s >= q1 - 1.5 * iqr].min()
        hi_w = s[s <= q3 + 1.5 * iqr].max()
        outl = s[(s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)]
        out.append({"column": c, "group": g, "min": _f(s.min()), "lower_whisker": _f(lo_w), "q1": _f(q1), "median": _f(med),
                    "q3": _f(q3), "upper_whisker": _f(hi_w), "max": _f(s.max()), "outliers": int(len(outl)),
                    "outlier_sample": [_f(v) for v in outl.sample(min(30, len(outl)), random_state=0)] if len(outl) else []})
    return out


def scatter(df: pd.DataFrame, x: str, y: str, n: int = 1500) -> dict:
    d = df[[x, y]].dropna()
    if d.empty:
        raise ValueError("No overlapping values")
    r = float(d[x].corr(d[y])) if d[x].nunique() > 1 and d[y].nunique() > 1 else None
    slope, intercept = (np.polyfit(d[x], d[y], 1) if d[x].nunique() > 1 else (None, None))
    s = d.sample(min(n, len(d)), random_state=0)
    return {"x": x, "y": y, "points": [{"x": _f(a), "y": _f(b)} for a, b in s.itertuples(index=False)],
            "pearson_r": _f(r, 3), "trend": {"slope": _f(slope), "intercept": _f(intercept)} if slope is not None else None}


def missing(df: pd.DataFrame) -> list[dict]:
    return [{"column": c, "missing": int(df[c].isna().sum()), "missing_pct": round(df[c].isna().mean() * 100, 2)}
            for c in df.columns]


def outliers(df: pd.DataFrame) -> list[dict]:
    out = []
    for c in _num_cols(df):
        s = df[c].dropna()
        q1, q3 = s.quantile([0.25, 0.75])
        iqr = q3 - q1
        if iqr == 0:
            continue
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        n = int(((s < lo) | (s > hi)).sum())
        out.append({"column": c, "outliers": n, "pct": round(n / max(len(s), 1) * 100, 2),
                    "lower_bound": _f(lo), "upper_bound": _f(hi), "extreme_3iqr": int(((s < q1 - 3 * iqr) | (s > q3 + 3 * iqr)).sum())})
    return out


def findings(df: pd.DataFrame, source: str, db: Session | None = None) -> list[dict]:
    """Plain-language findings, each generated from a computed number."""
    out: list[dict] = []
    if source == "sales" and not df.empty and db is not None:
        from app.analytics import sales as sa
        lo, hi = sa.data_bounds(db)
        cur = sa._totals(db, sa.Filters(hi - pd.Timedelta(days=29), hi))
        prev = sa._totals(db, sa.Filters(hi - pd.Timedelta(days=59), hi - pd.Timedelta(days=30)))
        ch = sa.pct_change(cur["revenue"], prev["revenue"])
        if ch is not None:
            out.append({"type": "trend", "text": f"Revenue in the last 30 days (to {hi:%d %b %Y}) was "
                        f"{'up' if ch >= 0 else 'down'} {abs(ch):.1f}% compared with the previous 30 days "
                        f"({money(cur['revenue'])} vs {money(prev['revenue'])})."})
        cats = sa.by_category(db, sa.Filters(hi - pd.Timedelta(days=29), hi))
        if cats:
            out.append({"type": "composition", "text": f"{cats[0]['category'].title()} contributed the largest share "
                        f"of revenue in the last 30 days ({cats[0]['share_pct']:.1f}%)."})
        wd = sa.by_weekday(db, sa.Filters(lo, hi))
        best, worst = max(wd, key=lambda r: r["avg_revenue"]), min(wd, key=lambda r: r["avg_revenue"])
        if worst["avg_revenue"]:
            out.append({"type": "seasonality", "text": f"{best['weekday_full']} is the strongest day: average revenue is "
                        f"{(best['avg_revenue'] / worst['avg_revenue'] - 1) * 100:.0f}% higher than on {worst['weekday_full']}."})
        if "is_event" in df and df.is_event.any():
            ev = df.groupby("is_event").units.mean()
            if 0 in ev and 1 in ev and ev[0] > 0:
                out.append({"type": "events", "text": f"On holiday / event days, average units per sales record are "
                            f"{(ev[1] / ev[0] - 1) * 100:+.1f}% vs. normal days (correlation, not proof of cause)."})
    num = _num_cols(df)
    if len(num) >= 2:
        c = df[num].corr().abs().to_numpy(copy=True)
        np.fill_diagonal(c, 0)
        i, j = np.unravel_index(np.nanargmax(c), c.shape)
        r = df[num].corr().iloc[i, j]
        strength = "strong" if abs(r) >= 0.7 else "moderate" if abs(r) >= 0.4 else "weak"
        out.append({"type": "correlation", "text": f"The strongest relationship is between '{num[i]}' and '{num[j]}' "
                    f"(Pearson r = {r:.2f}, {strength} {'positive' if r > 0 else 'negative'}). Correlation does not imply causation."})
    for c in num:
        sk = df[c].skew()
        if pd.notna(sk) and abs(sk) > 2:
            out.append({"type": "distribution", "text": f"'{c}' is highly {'right' if sk > 0 else 'left'}-skewed "
                        f"(skewness {sk:.1f}): the median ({df[c].median():.4g}) is a better 'typical value' than the mean ({df[c].mean():.4g})."})
            break
    miss = [(c, df[c].isna().mean()) for c in df.columns if df[c].isna().mean() > 0 and not str(c).startswith("_")]
    if miss:
        c, p = max(miss, key=lambda t: t[1])
        out.append({"type": "quality", "text": f"'{c}' has the most missing values ({p:.1%} of rows)."})
    else:
        out.append({"type": "quality", "text": "No missing values were found in the analysed rows."})
    outl = sorted(outliers(df), key=lambda r: r["pct"], reverse=True)
    if outl and outl[0]["outliers"]:
        o = outl[0]
        out.append({"type": "outliers", "text": f"'{o['column']}' has {o['outliers']:,} outliers ({o['pct']}% of values) "
                    f"beyond the 1.5×IQR fences [{o['lower_bound']:.4g}, {o['upper_bound']:.4g}]. Check these before modelling."})
    return out


def summary(db: Session, source: str) -> dict:
    load_currency(db)
    df, meta = load_source(db, source)
    return {"meta": meta, "columns": [{"name": c, "numeric": c in _num_cols(df), "dtype": str(df[c].dtype)} for c in df.columns],
            "describe": describe(df), "correlation": correlation(df), "missing": missing(df), "outliers": outliers(df),
            "findings": findings(df, source, db)}


def seaborn_png(db: Session, source: str, kind: str, columns: list[str] | None = None) -> bytes:
    """Static publication-quality chart rendered with Matplotlib + Seaborn (for downloads/reports)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import seaborn as sns

    df, meta = load_source(db, source)
    num = [c for c in (columns or _num_cols(df)) if c in _num_cols(df)][:8]
    sns.set_theme(style="whitegrid", palette="crest")
    if kind == "heatmap":
        fig, ax = plt.subplots(figsize=(8, 6.5))
        sns.heatmap(df[num].corr(), annot=True, fmt=".2f", cmap="RdBu_r", vmin=-1, vmax=1, ax=ax, square=True)
        ax.set_title(f"Correlation matrix - {meta['label']}")
    elif kind == "distribution":
        n = len(num)
        cols = 2 if n > 1 else 1
        rows = int(np.ceil(n / cols))
        fig, axes = plt.subplots(rows, cols, figsize=(10, 3.2 * rows), squeeze=False)
        for ax, c in zip(axes.flat, num, strict=False):
            sns.histplot(df[c].dropna(), kde=True, ax=ax, color="#0f766e")
            ax.set_title(c)
        for ax in list(axes.flat)[n:]:
            ax.set_visible(False)
        fig.suptitle(f"Distributions - {meta['label']}")
    elif kind == "boxplot":
        fig, ax = plt.subplots(figsize=(10, 5))
        z = (df[num] - df[num].mean()) / df[num].std()
        sns.boxplot(data=z, ax=ax, color="#5eead4")
        ax.set_title("Box plots (standardised values)")
    else:
        raise ValueError("kind must be heatmap, distribution or boxplot")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130)
    plt.close(fig)
    return buf.getvalue()
