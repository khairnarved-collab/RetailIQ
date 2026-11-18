"""
Data profiling and the automated data-cleaning pipeline.

Principles
  * Never silently delete data. Rows that cannot be used are moved to a
    separate "rejected rows" file together with the reason.
  * Every change is recorded as a step in the cleaning summary, with the
    number of rows/cells affected, so the user can see exactly what happened.
  * Outliers are FLAGGED, not removed - an unusual value may be a real event.
  * Missing values in optional columns are reported but not invented
    (no silent imputation).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- dataset kinds
# Canonical column names per kind; aliases map common real-world spellings.
ALIASES = {
    "date": ["date", "sale_date", "sales_date", "day", "transaction_date"],
    "store": ["store", "store_id", "store_code", "shop", "branch"],
    "product": ["product", "product_id", "item", "item_id", "sku"],
    "product_name": ["product_name", "item_name", "name", "description"],
    "units": ["units", "units_sold", "qty_sold", "sales_units", "volume"],
    "price": ["price", "unit_price", "sell_price", "selling_price"],
    "category": ["category", "cat", "cat_id", "category_name"],
    "state": ["state", "state_id", "region"],
    "customer_id": ["customer_id", "customer", "client_id", "cust_id", "customerid"],
    "order_id": ["order_id", "invoice", "invoice_no", "invoiceno", "order", "transaction_id", "order_no"],
    "order_date": ["order_date", "invoice_date", "invoicedate", "purchase_date", "orderdate"],
    "amount": ["amount", "total", "order_value", "sales", "revenue", "line_total", "total_amount"],
    "quantity": ["quantity", "qty"],
    "city": ["city", "town"],
}

KINDS = {
    "customer_transactions": {
        "required": ["customer_id", "order_id", "order_date", "amount"],
        "optional": ["quantity", "category", "store", "city"],
        "nonnegative": ["amount", "quantity"],
        "dates": ["order_date"],
        "numeric": ["amount", "quantity"],
        "label": "Customer transactions",
    },
    "sales_long": {
        "required": ["date", "store", "product", "units"],
        "optional": ["price", "category", "product_name", "state"],
        "nonnegative": ["units", "price"],
        "dates": ["date"],
        "numeric": ["units", "price"],
        "label": "Daily sales (long format)",
    },
}


def standardize_name(col: str) -> str:
    c = str(col).strip()
    c = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", c)          # camelCase -> camel_Case
    c = re.sub(r"[^0-9a-zA-Z]+", "_", c).strip("_").lower()
    return c or "column"


def detect_kind(columns: list[str]) -> str:
    std = {standardize_name(c) for c in columns}
    if any(c.startswith("d_") for c in std) and {"item_id", "store_id"} <= std:
        return "m5_sales"
    for kind, spec in KINDS.items():
        if all(any(a in std for a in ALIASES[req]) for req in spec["required"]):
            return kind
    return "generic"


def _alias_map(columns: list[str], kind: str) -> dict[str, str]:
    """Map standardized column names to canonical names for the given kind."""
    if kind not in KINDS:
        return {}
    wanted = KINDS[kind]["required"] + KINDS[kind]["optional"]
    out = {}
    for canon in wanted:
        for alias in ALIASES[canon]:
            if alias in columns and alias not in out and canon not in out.values():
                out[alias] = canon
                break
    return out


# ---------------------------------------------------------------- reading files
def read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        try:
            return pd.read_csv(path, low_memory=False)
        except UnicodeDecodeError:
            return pd.read_csv(path, low_memory=False, encoding="latin-1")
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(path)
    raise ValueError(f"Unsupported file type: {suffix}")


_NUM_CLEAN = re.compile(r"[\s$€£₹,%]")


def _to_numeric(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s):
        return s
    cleaned = s.astype("string").str.replace(_NUM_CLEAN, "", regex=True)
    return pd.to_numeric(cleaned, errors="coerce").astype("float64")


def _looks_numeric(s: pd.Series) -> float:
    nn = s.dropna()
    if nn.empty or pd.api.types.is_numeric_dtype(s):
        return 0.0
    return float(_to_numeric(nn).notna().mean())


def _to_datetime(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce", format="mixed") if not pd.api.types.is_datetime64_any_dtype(s) else s


def _looks_date(s: pd.Series, name: str) -> float:
    nn = s.dropna()
    if nn.empty or pd.api.types.is_numeric_dtype(s) or pd.api.types.is_datetime64_any_dtype(s):
        return 0.0
    sample = nn.astype(str).head(500)
    if not sample.str.contains(r"\d", regex=True).mean() > 0.8:
        return 0.0
    parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
    score = float(parsed.notna().mean())
    return score if ("date" in name or "time" in name or score > 0.9) else 0.0


def _json_safe(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else float(v)
    if isinstance(v, (pd.Timestamp,)):
        return v.isoformat()
    if v is pd.NA or (isinstance(v, float) and np.isnan(v)):
        return None
    return v


# ---------------------------------------------------------------- profiling
def profile(df: pd.DataFrame) -> dict:
    """Data-quality report of a DataFrame (works on raw or cleaned data)."""
    n = len(df)
    cols = []
    total_missing = 0
    for c in df.columns:
        s = df[c]
        missing = int(s.isna().sum())
        total_missing += missing
        issues: list[str] = []
        inferred = str(s.dtype)
        num_score = _looks_numeric(s)
        date_score = _looks_date(s, standardize_name(c))
        if num_score >= 0.8:
            bad = int(s.notna().sum() - _to_numeric(s).notna().sum())
            inferred = "numeric (stored as text)"
            issues.append(f"Numbers stored as text{f'; {bad} value(s) cannot be converted' if bad else ''}")
        elif date_score >= 0.8:
            bad = int(s.notna().sum() - _to_datetime(s).notna().sum())
            inferred = "date (stored as text)"
            issues.append(f"Dates stored as text{f'; {bad} value(s) are not valid dates' if bad else ''}")
        if missing:
            issues.append(f"{missing} missing value(s) ({missing / max(n, 1):.1%})")
        info = {
            "name": str(c), "dtype": str(s.dtype), "inferred_type": inferred,
            "missing": missing, "missing_pct": round(missing / max(n, 1) * 100, 2),
            "unique": int(s.nunique(dropna=True)),
            "sample_values": [_json_safe(v) for v in s.dropna().astype(str).unique()[:5].tolist()],
            "issues": issues,
        }
        numeric = _to_numeric(s) if (num_score >= 0.8 or pd.api.types.is_numeric_dtype(s)) else None
        if numeric is not None and numeric.notna().sum() >= 4 and not pd.api.types.is_bool_dtype(s):
            q1, q3 = numeric.quantile([0.25, 0.75])
            iqr = q3 - q1
            lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            n_out = int(((numeric < lo) | (numeric > hi)).sum()) if iqr > 0 else 0
            n_neg = int((numeric < 0).sum())
            info.update({"min": _json_safe(numeric.min()), "max": _json_safe(numeric.max()),
                         "mean": _json_safe(round(numeric.mean(), 4)), "outliers": n_out,
                         "outlier_bounds": [_json_safe(round(lo, 4)), _json_safe(round(hi, 4))],
                         "negative_values": n_neg})
            if n_out:
                issues.append(f"{n_out} outlier(s) outside the 1.5×IQR range")
            key = standardize_name(c)
            if n_neg and any(k in key for k in ("unit", "qty", "quantity", "price", "amount", "sales", "revenue", "total")):
                issues.append(f"{n_neg} negative value(s) - invalid for this kind of column")
        cols.append(info)
    dups = int(df.duplicated().sum())
    kind = detect_kind(list(df.columns))
    total_cells = max(n * max(len(df.columns), 1), 1)
    score = 100.0
    score -= min(40, total_missing / total_cells * 100 * 2)
    score -= min(20, dups / max(n, 1) * 100 * 2)
    score -= min(30, sum(1 for c in cols if c["issues"]) / max(len(cols), 1) * 30)
    return {
        "n_rows": n, "n_cols": int(df.shape[1]), "duplicate_rows": dups,
        "total_missing": total_missing, "detected_kind": kind,
        "detected_kind_label": KINDS.get(kind, {}).get("label", "M5 sales (wide)" if kind == "m5_sales" else "Generic table"),
        "required_columns": KINDS.get(kind, {}).get("required", []),
        "quality_score": round(max(score, 0), 1), "columns": cols,
    }


# ---------------------------------------------------------------- cleaning
@dataclass
class CleaningResult:
    cleaned: pd.DataFrame
    rejected: pd.DataFrame
    steps: list[dict] = field(default_factory=list)
    kind: str = "generic"

    def summary(self) -> dict:
        return {
            "kind": self.kind,
            "rows_in": int(len(self.cleaned) + len(self.rejected)),
            "rows_clean": int(len(self.cleaned)),
            "rows_rejected": int(len(self.rejected)),
            "steps": self.steps,
        }


def clean(df_raw: pd.DataFrame, kind: str | None = None) -> CleaningResult:
    df = df_raw.copy()
    steps: list[dict] = []
    rejected_parts: list[pd.DataFrame] = []

    def reject(mask: pd.Series, reason: str):
        if mask.any():
            r = df[mask].copy()
            r["_rejection_reason"] = reason
            rejected_parts.append(r)
        return df[~mask]

    # 1. standardise column names
    new_cols = [standardize_name(c) for c in df.columns]
    # make unique (e.g. two columns both becoming "price")
    seen: dict[str, int] = {}
    for i, c in enumerate(new_cols):
        if c in seen:
            seen[c] += 1
            new_cols[i] = f"{c}_{seen[c]}"
        else:
            seen[c] = 0
    renamed = {str(o): n for o, n in zip(df.columns, new_cols, strict=True) if str(o) != n}
    df.columns = new_cols
    kind = kind or detect_kind(new_cols)
    amap = _alias_map(new_cols, kind)
    alias_renamed = {k: v for k, v in amap.items() if k != v}
    df = df.rename(columns=amap)
    steps.append({"step": "Standardise column names",
                  "detail": "Converted to snake_case and mapped to standard names",
                  "changes": {**renamed, **{f"{k} (alias)": v for k, v in alias_renamed.items()}},
                  "affected": len(renamed) + len(alias_renamed)})

    # 2. trim whitespace in text columns
    trimmed = 0
    for c in df.columns:
        if df[c].dtype == object or pd.api.types.is_string_dtype(df[c]):
            before = df[c]
            after = before.where(before.isna(), before.astype(str).str.strip())
            trimmed += int(((before != after) & before.notna()).sum())
            df[c] = after
            # empty strings are missing values
            df.loc[df[c] == "", c] = np.nan
    steps.append({"step": "Trim text", "detail": "Removed leading/trailing spaces; empty text treated as missing",
                  "affected": trimmed})

    # 3. standardise known categorical text (case)
    cased = 0
    for c in ("category", "store", "state"):
        if c in df.columns:
            before = df[c]
            after = before.where(before.isna(), before.astype(str).str.upper())
            cased += int(((before != after) & before.notna()).sum())
            df[c] = after
    if cased:
        steps.append({"step": "Standardise text case", "detail": "Upper-cased category/store/state codes",
                      "affected": cased})

    # 4. convert data types
    spec = KINDS.get(kind, {})
    conversions = {}
    numeric_cols = set(spec.get("numeric", []))
    date_cols = set(spec.get("dates", []))
    for c in df.columns:
        if c not in numeric_cols and c not in date_cols:
            if _looks_numeric(df[c]) >= 0.8:
                numeric_cols.add(c)
            elif _looks_date(df[c], c) >= 0.8:
                date_cols.add(c)
    for c in numeric_cols & set(df.columns):
        before_na = int(df[c].isna().sum())
        df[c] = _to_numeric(df[c])
        failed = int(df[c].isna().sum()) - before_na
        conversions[c] = {"to": "number", "unconvertible_values_set_missing": failed}
    for c in date_cols & set(df.columns):
        before_na = int(df[c].isna().sum())
        df[c] = _to_datetime(df[c])
        failed = int(df[c].isna().sum()) - before_na
        conversions[c] = {"to": "date", "unconvertible_values_set_missing": failed}
    steps.append({"step": "Convert data types", "detail": "Text that holds numbers/dates converted; "
                  "values that could not be converted became missing (and are reported)",
                  "changes": conversions, "affected": sum(v["unconvertible_values_set_missing"] for v in conversions.values())})

    # 5. exact duplicate rows
    dup_mask = df.duplicated(keep="first")
    df = reject(dup_mask, "Exact duplicate of an earlier row")
    steps.append({"step": "Handle duplicates", "detail": "Exact duplicate rows moved to the rejected-rows file "
                  "(first occurrence kept)", "affected": int(dup_mask.sum())})

    # 6. validate required fields
    missing_report = {}
    if spec:
        missing_cols = [c for c in spec["required"] if c not in df.columns]
        if missing_cols:
            raise ValueError(f"Required column(s) missing for {spec['label']}: {', '.join(missing_cols)}")
        mask = df[spec["required"]].isna().any(axis=1)
        for c in spec["required"]:
            missing_report[c] = int(df[c].isna().sum())
        df = reject(mask, "Missing a required field (" + ", ".join(spec["required"]) + ")")
        steps.append({"step": "Validate required fields", "detail": "Rows missing a required value moved to rejected rows",
                      "changes": missing_report, "affected": int(mask.sum())})

    # 7. invalid values
    invalid = 0
    for c in spec.get("nonnegative", []):
        if c in df.columns:
            mask = df[c] < 0
            invalid += int(mask.sum())
            df = reject(mask, f"Negative value in '{c}'")
    for c in date_cols & set(df.columns):
        mask = df[c] > pd.Timestamp.now() + pd.Timedelta(days=1)
        invalid += int(mask.sum())
        df = reject(mask, f"Date in the future in '{c}'")
    steps.append({"step": "Validate values", "detail": "Negative quantities/prices/amounts and future dates moved to rejected rows",
                  "affected": invalid})

    # 8. missing values remaining in optional columns (reported, not invented)
    remaining = {c: int(df[c].isna().sum()) for c in df.columns if df[c].isna().any()}
    steps.append({"step": "Missing values", "detail": "Remaining missing values are in optional columns; they are kept "
                  "as missing rather than invented", "changes": remaining, "affected": sum(remaining.values())})

    # 9. flag outliers (IQR, k=3 = 'extreme')
    flagged = {}
    flags = pd.Series("", index=df.index, dtype=object)
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c]) and df[c].notna().sum() >= 8:
            q1, q3 = df[c].quantile([0.25, 0.75])
            iqr = q3 - q1
            if iqr <= 0:
                continue
            m = (df[c] < q1 - 3 * iqr) | (df[c] > q3 + 3 * iqr)
            if m.any():
                flagged[c] = int(m.sum())
                flags[m] = flags[m] + c + ";"
    if flagged:
        df["_outlier_columns"] = flags.str.rstrip(";").replace("", np.nan)
    steps.append({"step": "Identify outliers", "detail": "Extreme values (beyond 3×IQR) are flagged in column "
                  "'_outlier_columns' but NOT removed", "changes": flagged, "affected": sum(flagged.values())})

    rejected = pd.concat(rejected_parts) if rejected_parts else pd.DataFrame(columns=[*df.columns, "_rejection_reason"])
    return CleaningResult(cleaned=df.reset_index(drop=True), rejected=rejected, steps=steps, kind=kind)
