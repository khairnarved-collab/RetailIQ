"""
AI business assistant.

SAFETY DESIGN
  * The user's question is NEVER turned into SQL. It is mapped to one of a
    fixed set of read-only analytical functions (an "intent"). Those
    functions use the same tested analytics code as the dashboard.
  * The answer is therefore always a CALCULATED result.
  * If an LLM API key is configured (ANTHROPIC_API_KEY or OPENAI_API_KEY),
    the verified results - not the database - are sent to the LLM, which only
    writes a short plain-English explanation. That text is labelled
    "AI-generated explanation" in the UI. Without a key, or if the API call
    fails, the assistant still works in rule-based mode.
"""
from __future__ import annotations

import calendar as _cal
import difflib
import json
import logging
import re
from datetime import date, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics import sales as sa
from app.core.config import settings
from app.models import Category, ForecastRun, Product, Store

log = logging.getLogger(__name__)

EXAMPLES = [
    "What were my best-performing products last month?",
    "Which category generated the highest revenue?",
    "What is the predicted demand next month?",
    "Which products need restocking?",
    "Why did revenue decline?",
    "Summarize this month's business performance.",
    "How are the stores performing?",
    "Which customers are most valuable?",
]


# ------------------------------------------------------------------ parsing helpers
def parse_period(q: str, hi: date) -> tuple[date, date, str]:
    q = q.lower()
    m = re.search(r"last (\d{1,3}) days", q)
    if m:
        n = int(m.group(1))
        return hi - timedelta(days=n - 1), hi, f"the last {n} days"
    if "last week" in q or "past week" in q:
        return hi - timedelta(days=6), hi, "the last 7 days"
    if "last month" in q or "previous month" in q:
        first_this = hi.replace(day=1)
        end = first_this - timedelta(days=1)
        return end.replace(day=1), end, f"{_cal.month_name[end.month]} {end.year}"
    if "this month" in q or "month to date" in q:
        return hi.replace(day=1), hi, f"{_cal.month_name[hi.month]} {hi.year} (to {hi:%d %b})"
    if "quarter" in q:
        return hi - timedelta(days=89), hi, "the last 90 days"
    if "this year" in q or "ytd" in q:
        return hi.replace(month=1, day=1), hi, f"{hi.year} to date"
    if "last year" in q:
        return date(hi.year - 1, 1, 1), date(hi.year - 1, 12, 31), str(hi.year - 1)
    if "all time" in q or "overall" in q:
        return date(1900, 1, 1), hi, "all available data"
    return hi - timedelta(days=29), hi, "the last 30 days"


def find_product(db: Session, q: str) -> Product | None:
    products = db.scalars(select(Product)).all()
    ql = q.lower()
    for p in products:
        if p.sku.lower() in ql or p.name.lower() in ql:
            return p
    words = re.findall(r"[a-z]{4,}", ql)
    names = {p.name.lower(): p for p in products}
    for w in words:
        hits = [n for n in names if w in n.split()]
        if len(hits) == 1:
            return names[hits[0]]
    m = difflib.get_close_matches(ql, list(names), n=1, cutoff=0.75)
    return names[m[0]] if m else None


INTENTS = [
    ("restock", r"restock|re-stock|reorder|re-order|stock ?out|shortage|low stock|inventory|need.*stock"),
    ("revenue_decline", r"why.*(declin|drop|fall|fell|decreas|down)|(declin|drop|fall|decreas).*why|reason.*(declin|drop)"),
    ("forecast", r"forecast|predict|projection|expected demand|demand next|next (week|month)|coming (week|month)"),
    ("customers", r"customer|segment|champion|rfm|clv|loyal"),
    ("worst_products", r"worst|lowest|losing|poor(ly)?[ -]perform|declining product|least"),
    ("category", r"categor"),
    ("stores", r"store|branch|shop|location"),
    ("top_products", r"best|top|highest|most (sold|popular|revenue)|best[- ]selling|product"),
    ("summary", r"summar|overview|how (did|is|are) (we|the business)|performance|report|kpi|how.*doing"),
]


def detect_intent(q: str) -> str:
    ql = q.lower()
    for name, pattern in INTENTS:
        if re.search(pattern, ql):
            return name
    return "help"


def _money(v: float) -> str:
    return f"-${abs(v):,.0f}" if v < 0 else f"${v:,.0f}"


# ------------------------------------------------------------------ intent handlers
def _top(db, q, hi, worst=False):
    start, end, label = parse_period(q, hi)
    f = sa.Filters(max(start, sa.data_bounds(db)[0]), end)
    rows = sa.worst_products(db, f, 5) if worst else sa.top_products(db, f, 5)
    if not rows:
        return "There are no sales in that period.", None
    lead = rows[0]
    word = "lowest" if worst else "highest"
    text = (f"In {label}, the {word}-revenue product was **{lead['name']}** with {_money(lead['revenue'])} "
            f"from {lead['units']:,} units.")
    if worst:
        decl = [r for r in sa.product_performance(db, f).sort_values("change_pct").head(3).to_dict("records")
                if r["change_pct"] is not None and r["change_pct"] == r["change_pct"] and r["change_pct"] < 0]
        if decl:
            text += " Biggest declines vs the previous period: " + ", ".join(
                f"{d['name']} ({d['change_pct']:+.0f}%)" for d in decl) + "."
    table = {"columns": ["Product", "Category", "Revenue", "Units", "Change vs prev. period"],
             "rows": [[r["name"], r["category"], _money(r["revenue"]), f"{r['units']:,}",
                       f"{r['change_pct']:+.1f}%" if r["change_pct"] is not None else "n/a"] for r in rows]}
    return text, table


def _category(db, q, hi):
    start, end, label = parse_period(q, hi)
    rows = sa.by_category(db, sa.Filters(max(start, sa.data_bounds(db)[0]), end))
    if not rows:
        return "No sales in that period.", None
    t = rows[0]
    text = (f"In {label}, **{t['category'].title()}** generated the highest revenue: {_money(t['revenue'])} "
            f"({t['share_pct']:.1f}% of the total).")
    return text, {"columns": ["Category", "Revenue", "Share", "Units"],
                  "rows": [[r["category"], _money(r["revenue"]), f"{r['share_pct']:.1f}%", f"{r['units']:,}"] for r in rows]}


def _stores(db, q, hi):
    start, end, label = parse_period(q, hi)
    rows = sa.store_performance(db, sa.Filters(max(start, sa.data_bounds(db)[0]), end))
    if not rows:
        return "No sales in that period.", None
    best, worst = rows[0], rows[-1]
    text = (f"In {label}, the best store was **{best['code']} ({best['name']})** with {_money(best['revenue'])}; "
            f"the lowest was **{worst['code']} ({worst['name']})** with {_money(worst['revenue'])}.")
    return text, {"columns": ["Store", "Revenue", "Revenue/day", "Growth"],
                  "rows": [[f"{r['code']} – {r['name']}", _money(r["revenue"]), _money(r["revenue_per_day"]),
                            f"{r['growth_pct']:+.1f}%" if r["growth_pct"] is not None else "n/a"] for r in rows]}


def _forecast(db, q, hi):
    product = find_product(db, q)
    if product:
        run = db.scalar(select(ForecastRun).where(ForecastRun.product_id == product.id, ForecastRun.store_id.is_(None))
                        .order_by(ForecastRun.id.desc()))
        if run is None or run.train_end < hi:
            from app.forecasting.pipeline import run_forecast
            res = run_forecast(db, product.id, None, 30)
        else:
            res = {**run.details, "run_id": run.id}
        s = res["summary"]
        test = next(m for m in res["models"] if m["is_selected"])["test"]
        text = (f"Predicted demand for **{product.name}** (all stores) over the next {res['horizon']} days: "
                f"**{s['total_predicted_units']:,.0f} units** (≈{s['avg_daily_units']:.1f}/day, "
                f"{s['change_vs_recent_pct']:+.1f}% vs the last 28 days). Model: {res['best_model_label']}; "
                f"its error on the held-out test window was WAPE {test['wape']:.1f}%.")
        rows = [[r["date"], f"{r['predicted']:.1f}", f"{r['lower']:.1f} – {r['upper']:.1f}"] for r in res["forecast"][:14]]
        return text, {"columns": ["Date", "Predicted units", "80% interval"], "rows": rows}
    fc = sa.forecast_revenue(db, sa.Filters(), 30)
    if not fc:
        return "Not enough history to forecast.", None
    last30 = sa._totals(db, sa.Filters(hi - timedelta(days=29), hi))["revenue"]
    text = (f"Projected revenue for the next 30 days (all products and stores) is **{_money(fc['total'])}**, vs "
            f"{_money(last30)} in the last 30 days ({sa.pct_change(fc['total'], last30):+.1f}%). Method: {fc['method']}. "
            "Ask about a specific product (e.g. 'forecast demand for Whole Milk') for a unit forecast with model comparison.")
    weekly = {}
    for p in fc["series"]:
        wk = (date.fromisoformat(p["date"]) - timedelta(days=date.fromisoformat(p["date"]).weekday())).isoformat()
        weekly[wk] = weekly.get(wk, 0) + p["revenue"]
    return text, {"columns": ["Week starting", "Projected revenue"], "rows": [[k, _money(v)] for k, v in weekly.items()]}


def _restock(db, q, hi):
    from app.inventory.optimizer import positions
    inv = positions(db)
    items = [i for i in inv["items"] if i["recommended_order_qty"] > 0][:10]
    c = inv["summary"]["counts"]
    if not items:
        return "No products currently need restocking: all items are above their reorder points.", None
    text = (f"**{c['Critical']} critical** and **{c['Low Stock']} low-stock** items need attention. Recommended orders total "
            f"{inv['summary']['units_to_order']:,} units (≈{_money(inv['summary']['recommended_order_value'])} at cost). "
            f"Most urgent: {items[0]['product_name']} at {items[0]['store_code']} ({items[0]['on_hand']} in stock, "
            f"{items[0]['stockout_risk_pct']:.0f}% stock-out risk within the lead time).")
    return text, {"columns": ["Product", "Store", "Status", "On hand", "Order qty", "Stock-out risk"],
                  "rows": [[i["product_name"], i["store_code"], i["status"], i["on_hand"], i["recommended_order_qty"],
                            f"{i['stockout_risk_pct']:.0f}%"] for i in items]}


def _decline(db, q, hi):
    start, end, label = parse_period(q, hi)
    lo = sa.data_bounds(db)[0]
    start = max(start, lo)
    days = (end - start).days + 1
    cur = sa.Filters(start, end)
    prev = sa.Filters(start - timedelta(days=days), start - timedelta(days=1))
    tc, tp = sa._totals(db, cur)["revenue"], sa._totals(db, prev)["revenue"]
    ch = sa.pct_change(tc, tp)
    if ch is None:
        return "There is no previous period to compare with.", None
    perf = sa.product_performance(db, cur)
    perf["delta"] = perf.revenue - perf.prev_revenue
    neg = perf.sort_values("delta").head(5)
    cats_now = {c["category"]: c["revenue"] for c in sa.by_category(db, cur)}
    cats_prev = {c["category"]: c["revenue"] for c in sa.by_category(db, prev)}
    cat_delta = sorted(((k, cats_now.get(k, 0) - cats_prev.get(k, 0)) for k in set(cats_now) | set(cats_prev)), key=lambda t: t[1])
    direction = "declined" if ch < 0 else "did not decline - it rose"
    text = (f"Revenue in {label} {direction} {abs(ch):.1f}% ({_money(tc)} vs {_money(tp)} in the previous {days} days). "
            f"The largest category change was {cat_delta[0][0].title()} ({_money(cat_delta[0][1])}). "
            f"Products with the largest revenue decreases: " + ", ".join(f"{r.name} ({_money(r.delta)})" for r in neg.itertuples() if r.delta < 0)
            + ". These are the measured contributors; the underlying causes (pricing, availability, promotions, competition) "
              "need to be checked - the data shows what changed, not why.")
    return text, {"columns": ["Product", "Revenue now", "Revenue before", "Change"],
                  "rows": [[r.name, _money(r.revenue), _money(r.prev_revenue), _money(r.delta)] for r in neg.itertuples()]}


def _summary(db, q, hi):
    start, end, label = parse_period(q if "month" in q.lower() or "day" in q.lower() else q + " this month", hi)
    start = max(start, sa.data_bounds(db)[0])
    f = sa.Filters(start, end)
    k = sa.kpis(db, f)
    cats = sa.by_category(db, f)
    top = sa.top_products(db, f, 1)
    st = sa.store_performance(db, f)
    from app.inventory.optimizer import positions
    c = positions(db)["summary"]["counts"]
    g = k["revenue_growth_pct"]
    text = (f"**{label}:** revenue {_money(k['total_revenue'])}"
            + (f" ({g:+.1f}% vs the previous {k['period']['days']} days)" if g is not None else "")
            + f", {k['units_sold']:,} units across {k['num_stores']} stores. "
            + (f"Top category: {cats[0]['category'].title()} ({cats[0]['share_pct']:.0f}%). " if cats else "")
            + (f"Best product: {top[0]['name']} ({_money(top[0]['revenue'])}). " if top else "")
            + (f"Best store: {st[0]['code']}. " if st else "")
            + f"Inventory: {c['Critical']} critical and {c['Low Stock']} low-stock items.")
    return text, {"columns": ["Metric", "Value"], "rows": [
        ["Revenue", _money(k["total_revenue"])], ["Sales transactions", f"{k['total_orders']:,}"],
        ["Units sold", f"{k['units_sold']:,}"], ["Avg. transaction value", f"${k['avg_order_value']:.2f}"],
        ["Revenue growth", f"{g:+.1f}%" if g is not None else "n/a"],
        ["Forecast next 30 days", _money(k["forecasted_revenue_30d"]) if k["forecasted_revenue_30d"] else "n/a"]]}


def _customers(db, q, hi):
    from app.analytics.customers import analyse
    r = analyse(db, persist=False)
    if not r["available"]:
        return r["message"], None
    segs = {s["segment"]: s for s in r["segments"]}
    ch = segs.get("Champions")
    text = (f"Based on {r['kpis']['customers']:,} customers in '{r['dataset']['name']}'"
            + (" (SYNTHETIC data)" if r["dataset"]["is_synthetic"] else "") + ": "
            + (f"**Champions** ({ch['customers']} customers, {ch['share_pct']}%) generate {ch['revenue_share_pct']}% of revenue. "
               if ch else "")
            + f"Repeat purchase rate is {r['kpis']['repeat_purchase_rate_pct']}%, average CLV estimate "
              f"${r['kpis']['avg_clv']:,.0f}.")
    return text, {"columns": ["Customer", "Segment", "Orders", "Spend", "CLV estimate"],
                  "rows": [[c["customer"], c["segment"], c["orders"], _money(c["spend"]), _money(c["clv"])]
                           for c in r["top_customers"][:10]]}


HANDLERS = {
    "top_products": lambda db, q, hi: _top(db, q, hi),
    "worst_products": lambda db, q, hi: _top(db, q, hi, worst=True),
    "category": _category, "stores": _stores, "forecast": _forecast, "restock": _restock,
    "revenue_decline": _decline, "summary": _summary, "customers": _customers,
}


# ------------------------------------------------------------------ LLM explanation (optional)
LLM_SYSTEM = ("You are a retail analytics assistant. Explain the VERIFIED RESULTS below to a business manager in "
              "3-5 short sentences. Use only numbers that appear in the results; do not invent figures. Clearly mark "
              "anything that is a possible explanation rather than a measured fact. Never claim causation from correlation.")


def llm_explain(question: str, answer: str, table: dict | None) -> tuple[str | None, str | None]:
    provider = settings.llm_provider
    if not provider:
        return None, None
    payload = json.dumps({"question": question, "calculated_answer": answer, "table": table}, default=str)[:8000]
    try:
        if provider == "anthropic":
            r = httpx.post("https://api.anthropic.com/v1/messages", timeout=25, headers={
                "x-api-key": settings.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": settings.ANTHROPIC_MODEL, "max_tokens": 400, "system": LLM_SYSTEM,
                      "messages": [{"role": "user", "content": payload}]})
            r.raise_for_status()
            return "".join(b.get("text", "") for b in r.json()["content"]).strip(), None
        r = httpx.post("https://api.openai.com/v1/chat/completions", timeout=25,
                       headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                       json={"model": settings.OPENAI_MODEL, "max_tokens": 400,
                             "messages": [{"role": "system", "content": LLM_SYSTEM}, {"role": "user", "content": payload}]})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip(), None
    except Exception as e:  # noqa: BLE001 - the assistant must keep working without the LLM
        log.warning("LLM explanation failed: %s", e)
        return None, "The AI explanation service is unavailable right now; showing calculated results only."


def ask(db: Session, question: str) -> dict:
    q = question.strip()[:500]
    _, hi = sa.data_bounds(db)
    if hi is None:
        return {"intent": "no_data", "answer": "There is no sales data yet. Load the sample data or upload a dataset.",
                "table": None, "mode": "rule-based", "examples": EXAMPLES}
    intent = detect_intent(q)
    if intent == "help":
        n_p = len(db.scalars(select(Product.id)).all())
        n_s = len(db.scalars(select(Store.id)).all())
        n_c = len(db.scalars(select(Category.id)).all())
        return {"intent": "help", "mode": "rule-based", "table": None, "examples": EXAMPLES,
                "answer": (f"I can answer questions about your {n_p} products, {n_s} stores and {n_c} categories, using "
                           f"data up to {hi:%d %b %Y}. Try one of the example questions.")}
    text, table = HANDLERS[intent](db, q, hi)
    ai_text, ai_err = llm_explain(q, text, table)
    return {"intent": intent, "answer": text, "table": table, "data_through": hi.isoformat(),
            "mode": "llm" if ai_text else "rule-based", "ai_explanation": ai_text, "ai_error": ai_err,
            "llm_configured": settings.llm_provider is not None}
