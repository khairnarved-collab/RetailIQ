"""Currency setting, automatic inventory for uploads, and removing/restoring demo data.
(Named test_zz_* so it runs last: it removes the demo data that other tests use.)"""


import pandas as pd
from sqlalchemy import func, select

from app.core.money import money, set_currency
from app.models import InventoryItem, Product, Sale, Store


def test_money_formats():
    set_currency("INR")
    assert money(12345678) == "₹1,23,45,678"
    assert money(-999) == "-₹999"
    set_currency("USD")
    assert money(12345678) == "$12,345,678"


def test_currency_setting_changes_assistant_text(client, admin_headers):
    assert client.put("/api/admin/settings/general", headers=admin_headers, json={"values": {"currency": "INR"}}).status_code == 200
    a = client.post("/api/assistant/ask", headers=admin_headers, json={"question": "Which category generated the highest revenue?"}).json()
    assert "₹" in a["answer"] and "$" not in a["answer"]
    client.put("/api/admin/settings/general", headers=admin_headers, json={"values": {"currency": "USD"}})


def _upload_shop(client, headers):
    df = pd.DataFrame({"date": pd.date_range("2026-08-01", periods=60).strftime("%Y-%m-%d").tolist() * 2,
                       "store": ["MUM_TEST"] * 60 + ["DEL_TEST"] * 60, "product": ["PHONE-1"] * 120,
                       "product_name": ["Test Phone"] * 120, "category": ["Mobiles"] * 120,
                       "units": [3] * 120, "price": [14999] * 120})
    r = client.post("/api/datasets/upload", headers=headers, files={"file": ("shop.csv", df.to_csv(index=False).encode(), "text/csv")}).json()
    client.post(f"/api/datasets/{r['id']}/clean", headers=headers)
    return client.post(f"/api/datasets/{r['id']}/import", headers=headers).json()


def test_upload_creates_assumed_inventory(client, analyst_headers, db):
    res = _upload_shop(client, analyst_headers)
    assert any("inventory records" in n for n in res["notes"])
    store = db.scalar(select(Store).where(Store.code == "MUM_TEST"))
    inv = db.scalar(select(InventoryItem).where(InventoryItem.store_id == store.id))
    assert inv.on_hand_source == "assumed" and inv.on_hand == 42  # 3 units/day x 14 days


def test_remove_and_restore_demo_data_keeps_uploads(client, admin_headers, analyst_headers, db):
    assert client.post("/api/admin/demo-data/remove", headers=analyst_headers).status_code == 403
    before_upload = db.scalar(select(func.count(Sale.id)).join(Store).where(Store.code.in_(["MUM_TEST", "DEL_TEST"])))
    r = client.post("/api/admin/demo-data/remove", headers=admin_headers)
    assert r.status_code == 200 and r.json()["removed_sales_rows"] > 0
    db.expire_all()
    assert db.scalar(select(func.count(Product.id)).where(Product.sku == "FOODS_1_001")) == 0
    assert db.scalar(select(func.count(Sale.id)).join(Store).where(Store.code.in_(["MUM_TEST", "DEL_TEST"]))) == before_upload
    d = client.get("/api/dashboard", headers=admin_headers).json()
    assert [c["category"] for c in d["by_category"]] == ["MOBILES"]
    assert client.get("/api/admin/demo-data", headers=admin_headers).json()["demo_present"] is False
    assert client.post("/api/admin/demo-data/restore", headers=admin_headers).status_code == 200
    db.expire_all()
    assert db.scalar(select(func.count(Product.id)).where(Product.sku == "FOODS_1_001")) == 1



