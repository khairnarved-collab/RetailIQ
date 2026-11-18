"""Inventory calculations (pure functions) and the inventory API."""
import math

import pytest

from app.inventory.optimizer import compute_position

BASE = {"lead_time_days": 4, "review_period_days": 0, "service_level": 0.95, "on_hand": 100,
        "min_order_qty": 1, "pack_size": 1, "unit_cost": 2.0, "order_cost": 25.0, "holding_cost_rate": 0.25,
        "replenishment_policy": "order_up_to", "product_name": "Milk"}


def pos(**kw):
    return compute_position({**BASE, **kw.pop("item", {})}, kw.pop("mu", 10.0), kw.pop("sigma", 2.0),
                            kw.pop("forecast", None), kw.pop("overstock", 60))


def test_textbook_formulas():
    p = pos()
    z = 1.6449
    assert p["safety_stock"] == pytest.approx(z * 2 * math.sqrt(4), abs=0.1)        # z·σ·√L
    assert p["reorder_point"] == pytest.approx(10 * 4 + z * 2 * 2, abs=0.1)        # μL + SS
    assert p["days_of_inventory"] == pytest.approx(10.0)
    assert p["eoq"] == pytest.approx(math.sqrt(2 * 3650 * 25 / (2 * 0.25)), rel=1e-3)


def test_status_categories():
    assert pos(item={"on_hand": 3})["status"] == "Critical"        # below safety stock
    assert pos(item={"on_hand": 45})["status"] == "Low Stock"      # between SS and ROP
    assert pos(item={"on_hand": 300})["status"] == "Healthy"
    assert pos(item={"on_hand": 1000})["status"] == "Overstocked"  # 100 days of cover > 60
    assert pos(mu=0, sigma=0, item={"on_hand": 5})["status"] == "Overstocked"  # stock but no demand


def test_order_quantity_rules():
    p = pos(item={"on_hand": 20, "review_period_days": 7, "pack_size": 12})
    assert p["recommended_order_qty"] > 0 and p["recommended_order_qty"] % 12 == 0
    assert pos(item={"on_hand": 300})["recommended_order_qty"] == 0   # above ROP -> no order
    eoq = pos(item={"on_hand": 20, "replenishment_policy": "eoq"})
    assert eoq["recommended_order_qty"] >= eoq["eoq"]


def test_milk_example_from_spec():
    # Current stock 100, expected demand 150 over the cycle -> order ≈ 50 + safety stock
    p = pos(mu=10, sigma=0.0, item={"on_hand": 100, "lead_time_days": 10, "review_period_days": 5})
    assert p["expected_demand_cycle"] == pytest.approx(150)
    assert p["recommended_order_qty"] == 50
    assert "Restock 50 units" in p["recommendation"]


def test_forecast_is_used_when_available():
    p = pos(forecast=[20.0] * 10)
    assert p["demand_source"] == "forecast" and p["expected_demand_lead_time"] == pytest.approx(80)


def test_stockout_risk_bounds():
    assert pos(item={"on_hand": 0})["stockout_risk_pct"] > 99
    assert pos(item={"on_hand": 1000})["stockout_risk_pct"] < 1


def test_inventory_api_filters_and_update(client, analyst_headers):
    r = client.get("/api/inventory", headers=analyst_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["summary"]["total_items"] == len(data["items"]) > 0
    crit = client.get("/api/inventory?status=Critical", headers=analyst_headers).json()
    assert all(i["status"] == "Critical" for i in crit["items"])
    item = data["items"][0]
    up = client.patch(f"/api/inventory/{item['id']}", headers=analyst_headers, json={"on_hand": 5000, "lead_time_days": 3})
    assert up.status_code == 200
    assert up.json()["on_hand"] == 5000 and up.json()["on_hand_source"] == "user"
    assert client.patch(f"/api/inventory/{item['id']}", headers=analyst_headers, json={"on_hand": -1}).status_code == 422
