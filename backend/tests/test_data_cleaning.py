"""Data validation, profiling and the cleaning pipeline."""
import numpy as np
import pandas as pd
import pytest

from app.services import data_quality as dq


@pytest.fixture()
def messy(sample_dir):
    return dq.read_table(sample_dir / "messy_sales_sample.csv")


def test_standardize_column_names():
    assert dq.standardize_name(" Sale Date ") == "sale_date"
    assert dq.standardize_name("Item-ID") == "item_id"
    assert dq.standardize_name("unitPrice") == "unit_price"


def test_detect_kind():
    assert dq.detect_kind(["Sale Date", "Store ID", "Item-ID", "Units Sold"]) == "sales_long"
    assert dq.detect_kind(["CustomerID", "InvoiceNo", "InvoiceDate", "Amount"]) == "customer_transactions"
    assert dq.detect_kind(["a", "b"]) == "generic"


def test_profile_finds_problems(messy):
    p = dq.profile(messy)
    assert p["n_rows"] == len(messy)
    assert p["duplicate_rows"] >= 8
    cols = {c["name"]: c for c in p["columns"]}
    assert cols["Units Sold"]["missing"] == 5
    assert any("Numbers stored as text" in i for i in cols["Unit Price"]["issues"])
    assert cols["Units Sold"]["negative_values"] == 1
    assert 0 <= p["quality_score"] <= 100


def test_cleaning_never_silently_drops_rows(messy):
    res = dq.clean(messy)
    # every input row is either clean or rejected-with-a-reason
    assert len(res.cleaned) + len(res.rejected) == len(messy)
    assert res.rejected["_rejection_reason"].notna().all()
    reasons = " ".join(res.rejected["_rejection_reason"])
    assert "duplicate" in reasons and "required" in reasons and "Negative" in reasons


def test_cleaning_converts_types_and_names(messy):
    res = dq.clean(messy)
    df = res.cleaned
    assert {"date", "store", "product", "units", "price"} <= set(df.columns)
    assert pd.api.types.is_datetime64_any_dtype(df["date"])
    assert pd.api.types.is_float_dtype(df["price"])          # "$3.48" -> 3.48
    assert (df["units"] >= 0).all()
    assert df["category"].str.isupper().all()                 # " foods " -> "FOODS"


def test_outliers_flagged_not_removed(messy):
    res = dq.clean(messy)
    assert 480 in res.cleaned["units"].to_numpy()            # the extreme value is kept...
    flagged = res.cleaned.loc[res.cleaned.units == 480, "_outlier_columns"].iloc[0]
    assert "units" in flagged                                 # ...but flagged


def test_cleaning_summary_lists_every_step(messy):
    steps = [s["step"] for s in dq.clean(messy).summary()["steps"]]
    for expected in ("Standardise column names", "Convert data types", "Handle duplicates",
                     "Validate required fields", "Identify outliers"):
        assert expected in steps


def test_missing_required_column_raises():
    df = pd.DataFrame({"customer_id": [1], "amount": [5.0]})
    with pytest.raises(ValueError, match="Required column"):
        dq.clean(df, "customer_transactions")


def test_optional_missing_values_are_not_invented():
    df = pd.DataFrame({"date": ["2025-01-01", "2025-01-02"], "store": ["A", "B"], "product": ["p", "q"],
                       "units": [1, 2], "price": [np.nan, 2.0]})
    res = dq.clean(df)
    assert res.cleaned["price"].isna().sum() == 1
