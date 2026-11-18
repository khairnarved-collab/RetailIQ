"""API endpoints, dashboard correctness, uploads, customers, insights, assistant, reports and DB constraints."""
import io
from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import Category, Product, Sale


def test_health(client):
    assert client.get("/api/health").json()["database"] == "connected"


def test_dashboard_matches_database(client, analyst_headers, db):
    """KPIs must equal independent SQL aggregates - proves nothing is hard-coded."""
    d = client.get("/api/dashboard", headers=analyst_headers).json()
    rev = db.scalar(select(func.sum(Sale.revenue)))
    units = db.scalar(select(func.sum(Sale.units)))
    n = db.scalar(select(func.count(Sale.id)))
    k = d["kpis"]
    assert k["total_revenue"] == pytest.approx(rev, rel=1e-6)
    assert k["units_sold"] == units and k["total_orders"] == n
    assert k["avg_order_value"] == pytest.approx(rev / n, abs=0.01)
    for key in ("revenue_over_time", "monthly_comparison", "by_category", "top_products", "worst_products",
                "stores", "by_weekday", "by_month", "revenue_distribution", "demand_trends"):
        assert d[key], key
    assert sum(c["revenue"] for c in d["by_category"]) == pytest.approx(rev, rel=1e-6)


def test_dashboard_filters_change_results(client, analyst_headers, db):
    meta = client.get("/api/meta/filters", headers=analyst_headers).json()
    foods = next(c["id"] for c in meta["categories"] if c["name"] == "FOODS")
    store = meta["stores"][0]["id"]
    f = client.get(f"/api/dashboard?categories={foods}&stores={store}&start=2026-09-01&end=2026-09-30",
                   headers=analyst_headers).json()
    expected = db.scalar(select(func.sum(Sale.revenue)).join(Product, Product.id == Sale.product_id)
                         .where(Product.category_id == foods, Sale.store_id == store,
                                Sale.date >= date(2026, 9, 1), Sale.date <= date(2026, 9, 30)))
    assert f["kpis"]["total_revenue"] == pytest.approx(expected, rel=1e-6)
    assert [c["category"] for c in f["by_category"]] == ["FOODS"]
    assert f["kpis"]["revenue_growth_pct"] is not None
    assert client.get("/api/dashboard?start=2026-10-01&end=2026-01-01", headers=analyst_headers).status_code == 422


def test_upload_clean_import_sales(client, analyst_headers, sample_dir, db):
    before = db.scalar(select(func.count(Sale.id)))
    with open(sample_dir / "messy_sales_sample.csv", "rb") as fh:
        r = client.post("/api/datasets/upload", headers=analyst_headers, files={"file": ("messy_sales.csv", fh, "text/csv")})
    assert r.status_code == 201, r.text
    ds = r.json()
    assert ds["kind"] == "sales_long" and ds["quality"]["duplicate_rows"] > 0
    c = client.post(f"/api/datasets/{ds['id']}/clean", headers=analyst_headers)
    assert c.status_code == 200 and c.json()["summary"]["rows_rejected"] > 0
    for which in ("raw", "cleaned", "rejected"):
        assert client.get(f"/api/datasets/{ds['id']}/download/{which}", headers=analyst_headers).status_code == 200
    i = client.post(f"/api/datasets/{ds['id']}/import", headers=analyst_headers)
    assert i.status_code == 200, i.text
    db.expire_all()
    assert db.scalar(select(func.count(Sale.id))) > before - 1
    hist = client.get("/api/datasets", headers=analyst_headers).json()
    assert any(h["id"] == ds["id"] and h["status"] == "imported" for h in hist)


def test_upload_customer_excel_file(client, analyst_headers):
    import pandas as pd
    df = pd.DataFrame({"CustomerID": ["A", "A", "B"], "InvoiceNo": ["1", "2", "3"],
                       "InvoiceDate": ["2026-01-01", "2026-02-01", "2026-03-01"], "Amount": [10, 20, 30]})
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    r = client.post("/api/datasets/upload", headers=analyst_headers,
                    files={"file": ("customers.xlsx", buf.getvalue(), "application/vnd.ms-excel")})
    assert r.status_code == 201 and r.json()["kind"] == "customer_transactions"


def test_upload_validation(client, analyst_headers):
    r = client.post("/api/datasets/upload", headers=analyst_headers, files={"file": ("evil.exe", b"MZ...", "application/octet-stream")})
    assert r.status_code == 415
    r = client.post("/api/datasets/upload", headers=analyst_headers, files={"file": ("empty.csv", b"", "text/csv")})
    assert r.status_code == 400


def test_only_admin_deletes_datasets(client, analyst_headers, admin_headers):
    r = client.post("/api/datasets/upload", headers=analyst_headers, files={"file": ("t.csv", b"a,b\n1,2\n3,4\n", "text/csv")})
    did = r.json()["id"]
    assert client.delete(f"/api/datasets/{did}", headers=analyst_headers).status_code == 403
    assert client.delete(f"/api/datasets/{did}", headers=admin_headers).status_code == 204


def test_eda_endpoints(client, analyst_headers):
    s = client.get("/api/eda/summary?source=sales", headers=analyst_headers).json()
    num = {d["column"]: d for d in s["describe"]["numeric"]}
    assert {"mean", "median", "mode", "std", "q1", "q3"} <= set(num["units"])
    assert s["findings"] and s["correlation"]["matrix"]
    assert client.get("/api/eda/histogram?column=units", headers=analyst_headers).status_code == 200
    assert client.get("/api/eda/scatter?x=unit_price&y=units", headers=analyst_headers).json()["points"]
    assert client.get("/api/eda/box?columns=revenue&by=category", headers=analyst_headers).status_code == 200
    png = client.get("/api/eda/plot.png?kind=heatmap", headers=analyst_headers)
    assert png.status_code == 200 and png.content[:4] == b"\x89PNG"


def test_customer_analytics(client, analyst_headers):
    r = client.get("/api/customers/analysis", headers=analyst_headers).json()
    assert r["available"] and r["dataset"]["is_synthetic"]
    assert sum(s["customers"] for s in r["segments"]) == r["kpis"]["customers"]
    assert 3 <= r["clusters"]["k"] <= 6
    assert all(s["recommendations"] for s in r["segments"])


def test_insights_separate_findings_and_hypotheses(client, analyst_headers):
    r = client.get("/api/insights", headers=analyst_headers).json()
    assert r["insights"]
    for i in r["insights"]:
        assert i["finding"] and i["recommendation"]
        for c in i["possible_causes"]:
            assert c.startswith(("Data:", "Hypothesis:", "Based on"))


@pytest.mark.parametrize("q,intent", [
    ("What were my best-performing products?", "top_products"),
    ("Which category generated the highest revenue?", "category"),
    ("What is the predicted demand next month?", "forecast"),
    ("Which products need restocking?", "restock"),
    ("Why did revenue decline?", "revenue_decline"),
    ("Summarize this month's business performance.", "summary"),
    ("Which customers are most valuable?", "customers"),
    ("hello there", "help"),
])
def test_assistant_intents_work_without_llm(client, analyst_headers, q, intent):
    r = client.post("/api/assistant/ask", headers=analyst_headers, json={"question": q})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == intent and body["answer"]
    assert body["mode"] == "rule-based" and body.get("ai_explanation") is None


def test_assistant_never_runs_sql(client, analyst_headers, db):
    before = db.scalar(select(func.count(Sale.id)))
    client.post("/api/assistant/ask", headers=analyst_headers, json={"question": "DROP TABLE sales; SELECT * FROM users"})
    db.expire_all()
    assert db.scalar(select(func.count(Sale.id))) == before


@pytest.mark.parametrize("rtype", ["daily", "weekly", "monthly", "product", "customer", "forecast", "inventory"])
@pytest.mark.parametrize("fmt,magic", [("pdf", b"%PDF"), ("xlsx", b"PK"), ("csv", None)])
def test_report_generation(client, analyst_headers, rtype, fmt, magic, db):
    if rtype == "forecast" and fmt == "pdf":  # a forecast report needs at least one forecast run
        pid = db.scalar(select(Product.id))
        assert client.post("/api/forecasting/run", headers=analyst_headers, json={"product_id": pid, "horizon": 7}).status_code == 200
    r = client.post("/api/reports", headers=analyst_headers, json={"report_type": rtype, "format": fmt})
    assert r.status_code == 201, r.text
    d = client.get(f"/api/reports/{r.json()['id']}/download", headers=analyst_headers)
    assert d.status_code == 200 and len(d.content) > 50
    if magic:
        assert d.content.startswith(magic)


def test_notifications(client, analyst_headers):
    client.post("/api/inventory/alerts", headers=analyst_headers)
    n = client.get("/api/notifications", headers=analyst_headers).json()
    assert n
    assert client.post("/api/notifications/read-all", headers=analyst_headers).status_code == 200
    assert all(x["is_read"] for x in client.get("/api/notifications", headers=analyst_headers).json() if x["title"] != "")


def test_database_constraints(db):
    s = db.scalar(select(Sale))
    dup = Sale(date=s.date, store_id=s.store_id, product_id=s.product_id, units=1, revenue=1)
    db.add(dup)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(Sale(date=s.date, store_id=s.store_id, product_id=s.product_id, units=-5, revenue=0))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(Category(name=db.scalar(select(Category.name))))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
