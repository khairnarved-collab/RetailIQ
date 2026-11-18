"""
Customer intelligence: RFM analysis, K-Means segmentation, CLV and retention.

Only runs on customer-level transaction data that a user uploaded (or the
clearly-labelled synthetic sample). The M5 dataset has no customer data, so
nothing here is ever derived from it.

RFM
    Recency   = days since the customer's last order (relative to the day after the last order in the data)
    Frequency = number of distinct orders
    Monetary  = total amount spent
    Each is scored 1-5 by quintile (5 = best; for recency, more recent = higher).

Simple CLV estimate (assumptions are admin-configurable in Settings)
    CLV = average order value × orders per year × expected lifespan (years) × gross margin
    orders per year uses the customer's observed tenure (at least 90 days, so
    one-off new customers are not extrapolated wildly).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.models import Customer, CustomerSegment, CustomerTransaction, Dataset
from app.services import app_settings

SEGMENT_INFO = {
    "Champions": ("Bought recently, buy often and spend the most.",
                  ["Reward them with loyalty perks or early access to new products.",
                   "Ask for reviews and referrals.", "Avoid heavy discounts; they already buy at full price."]),
    "Loyal Customers": ("Buy regularly; respond well to engagement.",
                        ["Offer membership or tiered rewards.", "Up-sell higher-value products.",
                         "Personalise recommendations from their purchase history."]),
    "Potential Loyalists": ("Recent customers with average frequency.",
                            ["Encourage the next purchase with a time-limited offer.",
                             "Recommend complementary products.", "Invite them into the loyalty programme."]),
    "New Customers": ("Made their first purchase recently.",
                      ["Send a welcome / onboarding sequence.", "Offer a small incentive for the second purchase.",
                       "Collect feedback on the first experience."]),
    "Need Attention": ("Average recency and frequency; at risk of drifting away.",
                       ["Send personalised reminders.", "Offer limited-time deals on categories they bought before."]),
    "At Risk": ("Used to buy often but have not purchased for a long time.",
                ["Run a win-back campaign with a meaningful offer.", "Ask why they stopped (short survey).",
                 "Highlight new products since their last visit."]),
    "Lost Customers": ("Low frequency and long since their last purchase.",
                       ["Only re-engage with low-cost channels (email).",
                        "Do not over-invest; focus budget on higher-value segments.",
                        "Use them to learn about churn reasons."]),
}


def customer_datasets(db: Session) -> list[dict]:
    rows = db.execute(select(Dataset.id, Dataset.name, Dataset.is_synthetic, func.count(CustomerTransaction.id))
                      .join(CustomerTransaction, CustomerTransaction.dataset_id == Dataset.id)
                      .group_by(Dataset.id, Dataset.name, Dataset.is_synthetic).order_by(Dataset.id.desc())).all()
    return [{"id": i, "name": n, "is_synthetic": s, "transactions": c} for i, n, s, c in rows]


def _load(db: Session, dataset_id: int) -> pd.DataFrame:
    rows = db.execute(select(Customer.id, Customer.external_id, CustomerTransaction.order_id,
                             CustomerTransaction.order_date, CustomerTransaction.amount, CustomerTransaction.category)
                      .join(Customer, Customer.id == CustomerTransaction.customer_id)
                      .where(CustomerTransaction.dataset_id == dataset_id)).all()
    df = pd.DataFrame(rows, columns=["cid", "external_id", "order_id", "order_date", "amount", "category"])
    df["order_date"] = pd.to_datetime(df["order_date"])
    return df


def _score(series: pd.Series, reverse: bool = False) -> pd.Series:
    """Quintile scores 1..5 (ties broken by order so qcut always has 5 bins)."""
    ranks = series.rank(method="first", ascending=not reverse)
    return pd.qcut(ranks, 5, labels=[1, 2, 3, 4, 5]).astype(int)


def _segment(r: int, f: int, orders: int) -> str:
    if r >= 4 and f >= 4:
        return "Champions"
    if r >= 3 and f >= 4:
        return "Loyal Customers"
    if r >= 4 and orders == 1:
        return "New Customers"
    if r >= 3 and f >= 2:
        return "Potential Loyalists"
    if r >= 4:
        return "Potential Loyalists"
    if r <= 2 and f >= 3:
        return "At Risk"
    if r <= 2:
        return "Lost Customers"
    return "Need Attention"


def _cluster_label(row: pd.Series, med: pd.Series) -> str:
    value = "High-value" if row.monetary >= med.monetary * 1.5 else ("Low-value" if row.monetary < med.monetary * 0.6 else "Mid-value")
    recency = "recent" if row.recency <= med.recency * 0.6 else ("lapsed" if row.recency >= med.recency * 1.6 else "occasional")
    freq = "frequent" if row.frequency >= med.frequency * 1.5 else ""
    return " · ".join(x for x in (value, freq, recency) if x)


def analyse(db: Session, dataset_id: int | None = None, persist: bool = True) -> dict:
    sets = customer_datasets(db)
    if not sets:
        return {"available": False, "datasets": [],
                "message": "No customer-level data is loaded. The M5 sales data contains no customer information, "
                           "so customer analytics needs a separate transactions file with at least customer_id, "
                           "order_id, order_date and amount. Upload one in Data Management, clean it and import it."}
    ds_id = dataset_id or sets[0]["id"]
    ds = next((s for s in sets if s["id"] == ds_id), None)
    if ds is None:
        return {"available": False, "datasets": sets, "message": "That dataset has no imported customer transactions."}
    cfg = app_settings.get_section(db, "customers")
    tx = _load(db, ds_id)
    snapshot = tx.order_date.max() + pd.Timedelta(days=1)

    orders = tx.groupby(["cid", "order_id"]).agg(date=("order_date", "min"), amount=("amount", "sum")).reset_index()
    cust = orders.groupby("cid").agg(first=("date", "min"), last=("date", "max"), frequency=("order_id", "nunique"),
                                     monetary=("amount", "sum")).reset_index()
    cust["recency"] = (snapshot - cust["last"]).dt.days
    cust["r_score"] = _score(cust.recency, reverse=True)
    cust["f_score"] = _score(cust.frequency)
    cust["m_score"] = _score(cust.monetary)
    cust["segment"] = [_segment(r, f, o) for r, f, o in zip(cust.r_score, cust.f_score, cust.frequency, strict=True)]

    # CLV
    tenure_days = np.maximum((snapshot - cust["first"]).dt.days, 90)
    aov = cust.monetary / cust.frequency
    orders_per_year = cust.frequency / (tenure_days / 365.0)
    cust["clv"] = aov * orders_per_year * float(cfg["clv_lifespan_years"]) * float(cfg["gross_margin"])

    # K-Means on log-scaled RFM (log reduces the effect of a few very big spenders)
    X = StandardScaler().fit_transform(np.log1p(cust[["recency", "frequency", "monetary"]].to_numpy(float)))
    rng = np.random.default_rng(0)
    sample = rng.choice(len(X), size=min(3000, len(X)), replace=False)
    best_k, best_s, scores = 3, -1.0, []
    for k in range(3, 7):
        if len(X) <= k:
            break
        km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(X)
        s = float(silhouette_score(X[sample], km.labels_[sample]))
        scores.append({"k": k, "silhouette": round(s, 4)})
        if s > best_s:
            best_k, best_s = k, s
    km = KMeans(n_clusters=best_k, n_init=10, random_state=42).fit(X)
    cust["cluster"] = km.labels_
    med = cust[["recency", "frequency", "monetary"]].median()
    prof = cust.groupby("cluster").agg(customers=("cid", "count"), recency=("recency", "mean"),
                                       frequency=("frequency", "mean"), monetary=("monetary", "mean"),
                                       clv=("clv", "mean")).reset_index()
    labels = [_cluster_label(r, med) for r in prof.itertuples()]
    # make labels unique when two clusters get the same description
    original = list(labels)
    seen: dict[str, int] = {}
    for i, lab in enumerate(original):
        if original.count(lab) > 1:
            seen[lab] = seen.get(lab, 0) + 1
            labels[i] = f"{lab} ({'ABCDEF'[seen[lab] - 1]})"
    prof["label"] = labels

    if persist:
        db.execute(delete(CustomerSegment).where(CustomerSegment.dataset_id == ds_id))
        db.execute(insert(CustomerSegment), [
            {"customer_id": int(r.cid), "dataset_id": ds_id, "recency_days": int(r.recency), "frequency": int(r.frequency),
             "monetary": float(r.monetary), "r_score": int(r.r_score), "f_score": int(r.f_score), "m_score": int(r.m_score),
             "rfm_segment": r.segment, "cluster": int(r.cluster), "clv_estimate": float(r.clv)}
            for r in cust.itertuples()])
        db.commit()

    total_rev = float(cust.monetary.sum())
    seg = cust.groupby("segment").agg(customers=("cid", "count"), revenue=("monetary", "sum"),
                                      avg_recency=("recency", "mean"), avg_frequency=("frequency", "mean"),
                                      avg_monetary=("monetary", "mean"), avg_clv=("clv", "mean")).reset_index()
    seg_order = list(SEGMENT_INFO)
    seg["order"] = seg.segment.map(seg_order.index)
    seg = seg.sort_values("order")
    segments = [{"segment": r.segment, "customers": int(r.customers), "share_pct": round(r.customers / len(cust) * 100, 1),
                 "revenue": round(float(r.revenue), 2), "revenue_share_pct": round(float(r.revenue) / total_rev * 100, 1),
                 "avg_recency_days": round(float(r.avg_recency), 1), "avg_frequency": round(float(r.avg_frequency), 2),
                 "avg_monetary": round(float(r.avg_monetary), 2), "avg_clv": round(float(r.avg_clv), 2),
                 "description": SEGMENT_INFO[r.segment][0], "recommendations": SEGMENT_INFO[r.segment][1]}
                for r in seg.itertuples()]

    # retention: monthly cohorts
    orders["month"] = orders.date.dt.to_period("M")
    first_month = orders.groupby("cid").month.min().rename("cohort")
    o = orders.join(first_month, on="cid")
    o["age"] = (o.month - o.cohort).apply(lambda x: x.n)
    cohort = o.groupby(["cohort", "age"]).cid.nunique().unstack(fill_value=0)
    sizes = cohort[0]
    ret = (cohort.div(sizes, axis=0) * 100).round(1)
    ret = ret.iloc[-12:, :12]
    cohorts = [{"cohort": str(idx), "size": int(sizes[idx]),
                "values": [None if (pd.Period(idx, "M") + int(a)) > orders.month.max() else float(v)
                           for a, v in row.items()]} for idx, row in ret.iterrows()]

    # 90-day retention: customers active in the previous 90 days who bought again in the last 90 days
    last90 = orders[orders.date >= snapshot - pd.Timedelta(days=90)].cid.unique()
    prev90 = orders[(orders.date < snapshot - pd.Timedelta(days=90)) & (orders.date >= snapshot - pd.Timedelta(days=180))].cid.unique()
    retention_90 = round(len(set(prev90) & set(last90)) / len(prev90) * 100, 1) if len(prev90) else None

    freq_hist = cust.frequency.clip(upper=30).value_counts().sort_index()
    m_counts, m_edges = np.histogram(cust.monetary, bins=20)
    top = cust.merge(tx[["cid", "external_id"]].drop_duplicates(), on="cid").sort_values("monetary", ascending=False).head(15)

    return {
        "available": True, "dataset": ds, "datasets": sets,
        "snapshot_date": snapshot.date().isoformat(),
        "kpis": {
            "customers": int(len(cust)), "orders": int(orders.order_id.nunique()), "revenue": round(total_rev, 2),
            "avg_spend_per_customer": round(float(cust.monetary.mean()), 2),
            "avg_order_value": round(total_rev / max(len(orders), 1), 2),
            "avg_orders_per_customer": round(float(cust.frequency.mean()), 2),
            "repeat_purchase_rate_pct": round(float((cust.frequency > 1).mean() * 100), 1),
            "retention_90d_pct": retention_90,
            "avg_clv": round(float(cust.clv.mean()), 2),
        },
        "segments": segments,
        "clusters": {
            "k": best_k, "silhouette_by_k": scores, "method": "K-Means on standardised log(R, F, M); k chosen by silhouette score",
            "profiles": [{"cluster": int(r.cluster), "label": r.label, "customers": int(r.customers),
                          "avg_recency_days": round(r.recency, 1), "avg_frequency": round(r.frequency, 2),
                          "avg_monetary": round(r.monetary, 2), "avg_clv": round(r.clv, 2)} for r in prof.itertuples()],
            "points": [{"recency": int(r.recency), "frequency": int(r.frequency), "monetary": round(float(r.monetary), 2),
                        "cluster": int(r.cluster), "segment": r.segment}
                       for r in cust.sample(min(800, len(cust)), random_state=1).itertuples()],
            "crosstab": pd.crosstab(cust.segment, cust.cluster).reset_index().rename(columns=str).to_dict("records"),
        },
        "cohorts": cohorts,
        "frequency_distribution": [{"orders": f"{int(k)}{'+' if k == 30 else ''}", "customers": int(v)} for k, v in freq_hist.items()],
        "monetary_distribution": [{"range": f"{m_edges[i]:,.0f}–{m_edges[i + 1]:,.0f}", "customers": int(c)}
                                  for i, c in enumerate(m_counts)],
        "top_customers": [{"customer": r.external_id, "segment": r.segment, "orders": int(r.frequency),
                           "spend": round(float(r.monetary), 2), "recency_days": int(r.recency), "clv": round(float(r.clv), 2)}
                          for r in top.itertuples()],
        "assumptions": {
            "clv_formula": "Average order value × orders per year × expected lifespan × gross margin",
            "clv_lifespan_years": cfg["clv_lifespan_years"], "gross_margin": cfg["gross_margin"],
            "note": "CLV is a simple historical estimate, not a probabilistic model. Orders per year use each "
                    "customer's tenure (minimum 90 days).",
        },
    }
