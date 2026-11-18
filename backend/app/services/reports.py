"""
Report generation: daily / weekly / monthly / product / customer / forecast / inventory,
exported as PDF (ReportLab + Matplotlib charts), Excel (openpyxl) or CSV.

Every report is built in two steps:
  1. a builder collects KPIs, tables (pandas DataFrames), chart data, findings and
     recommendations from the analytics modules (no hard-coded numbers);
  2. a renderer turns that structure into the requested file format.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics import sales as sa
from app.models import Dataset, ForecastRun

REPORT_TYPES = {
    "daily": "Daily Sales Report", "weekly": "Weekly Performance Report", "monthly": "Monthly Business Report",
    "product": "Product Performance Report", "customer": "Customer Analytics Report",
    "forecast": "Demand Forecasting Report", "inventory": "Inventory Report",
}
FORMATS = ("pdf", "xlsx", "csv")
BRAND = "#0f766e"


@dataclass
class Section:
    heading: str
    table: pd.DataFrame | None = None
    text: str | None = None
    chart: dict | None = None  # {"kind": "line"|"bar"|"barh", "x": [...], "series": {name: [...]}, "ylabel": str}


@dataclass
class ReportData:
    title: str
    period: str
    kpis: list[tuple[str, str]] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _m(v) -> str:
    return "n/a" if v is None else (f"-${abs(v):,.0f}" if v < 0 else f"${v:,.0f}")


def _pct(v) -> str:
    return "n/a" if v is None else f"{v:+.1f}%"


def _synthetic_note(db: Session) -> list[str]:
    if db.scalar(select(Dataset.id).where(Dataset.kind == "m5_sales", Dataset.is_synthetic.is_(True))):
        return ["Data notice: this workspace contains SYNTHETIC demonstration data in M5 format. "
                "Figures are illustrative and do not describe a real business."]
    return []


def _period_report(db: Session, title: str, start: date, end: date, chart_daily: bool = True) -> ReportData:
    f = sa.Filters(start, end)
    k = sa.kpis(db, f)
    rd = ReportData(title=title, period=f"{start:%d %b %Y} – {end:%d %b %Y}")
    rd.kpis = [("Revenue", _m(k["total_revenue"])), ("Revenue growth", _pct(k["revenue_growth_pct"])),
               ("Sales transactions", f"{k['total_orders']:,}"), ("Units sold", f"{k['units_sold']:,}"),
               ("Avg. transaction value", f"${k['avg_order_value']:.2f}"), ("Products sold", str(k["total_products"])),
               ("Stores", str(k["num_stores"])),
               ("Forecast next 30 days", _m(k["forecasted_revenue_30d"]))]
    ts = sa.revenue_over_time(db, f)["points"]
    if ts and chart_daily:
        rd.sections.append(Section("Revenue over time", chart={
            "kind": "line", "x": [p["date"] for p in ts], "series": {"Revenue": [p["revenue"] for p in ts]}, "ylabel": "Revenue ($)"}))
    cats = pd.DataFrame(sa.by_category(db, f))
    if not cats.empty:
        rd.sections.append(Section("Revenue by category", table=cats.rename(columns={
            "category": "Category", "revenue": "Revenue", "units": "Units", "share_pct": "Share %"}),
            chart={"kind": "bar", "x": cats.category.tolist(), "series": {"Revenue": cats.revenue.tolist()}, "ylabel": "Revenue ($)"}))
    perf = sa.product_performance(db, f)
    if not perf.empty:
        cols = {"sku": "SKU", "name": "Product", "category": "Category", "revenue": "Revenue", "units": "Units",
                "change_pct": "Change %"}
        top = perf.head(10)[list(cols)].rename(columns=cols)
        rd.sections.append(Section("Top 10 products", table=top.round(2), chart={
            "kind": "barh", "x": top.Product.tolist()[::-1], "series": {"Revenue": top.Revenue.tolist()[::-1]}, "ylabel": "Revenue ($)"}))
        rd.sections.append(Section("Lowest-revenue products", table=perf.tail(10).sort_values("revenue")[list(cols)].rename(columns=cols).round(2)))
    stores = pd.DataFrame(sa.store_performance(db, f))
    if not stores.empty:
        rd.sections.append(Section("Store performance", table=stores[["code", "name", "revenue", "units", "revenue_per_day", "growth_pct"]]
                                   .rename(columns={"code": "Store", "name": "Name", "revenue": "Revenue", "units": "Units",
                                                    "revenue_per_day": "Revenue/day", "growth_pct": "Growth %"})))
    if k["revenue_growth_pct"] is not None:
        rd.findings.append(f"Revenue was {_m(k['total_revenue'])}, {_pct(k['revenue_growth_pct'])} vs the previous period of equal length.")
    if not cats.empty:
        rd.findings.append(f"{cats.iloc[0].category.title()} was the largest category with {cats.iloc[0].share_pct:.1f}% of revenue.")
    if not perf.empty:
        rd.findings.append(f"Best product: {perf.iloc[0]['name']} ({_m(perf.iloc[0].revenue)}).")
        decl = perf.dropna(subset=["change_pct"]).sort_values("change_pct").head(1)
        if len(decl) and decl.iloc[0].change_pct < -10:
            rd.findings.append(f"Largest decline: {decl.iloc[0]['name']} ({decl.iloc[0].change_pct:+.1f}%).")
            rd.recommendations.append(f"Review pricing, availability and promotions for {decl.iloc[0]['name']}.")
    if not stores.empty:
        rd.findings.append(f"Best store: {stores.iloc[0].code} ({_m(stores.iloc[0].revenue)}); "
                           f"lowest: {stores.iloc[-1].code} ({_m(stores.iloc[-1].revenue)}).")
    from app.services.insights import generate
    for ins in generate(db)["insights"][:5]:
        if ins["severity"] in ("critical", "warning"):
            rd.recommendations.append(f"{ins['title']}: {ins['recommendation']}")
    return rd


def build(db: Session, report_type: str, start: date | None = None, end: date | None = None,
          run_id: int | None = None) -> ReportData:
    lo, hi = sa.data_bounds(db)
    if hi is None:
        raise ValueError("No sales data available")
    end = min(end or hi, hi)
    if report_type == "daily":
        rd = _period_report(db, REPORT_TYPES["daily"], end, end, chart_daily=False)
        week_ago = sa._totals(db, sa.Filters(end - timedelta(days=7), end - timedelta(days=7)))
        rd.findings.insert(0, f"Revenue on {end:%A %d %b %Y} vs the same weekday last week: "
                              f"{_m(sa._totals(db, sa.Filters(end, end))['revenue'])} vs {_m(week_ago['revenue'])}.")
    elif report_type == "weekly":
        rd = _period_report(db, REPORT_TYPES["weekly"], end - timedelta(days=6), end)
    elif report_type == "monthly":
        s = start or end.replace(day=1)
        rd = _period_report(db, REPORT_TYPES["monthly"], s, end)
    elif report_type == "product":
        s = start or end - timedelta(days=89)
        f = sa.Filters(max(s, lo), end)
        perf = sa.product_performance(db, f)
        rd = ReportData(REPORT_TYPES["product"], f"{f.start:%d %b %Y} – {end:%d %b %Y}")
        rd.kpis = [("Products", str(len(perf))), ("Revenue", _m(perf.revenue.sum())), ("Units", f"{int(perf.units.sum()):,}"),
                   ("Growing products", str(int((perf.change_pct > 0).sum()))),
                   ("Declining products", str(int((perf.change_pct < 0).sum())))]
        cols = {"sku": "SKU", "name": "Product", "category": "Category", "revenue": "Revenue", "units": "Units",
                "prev_revenue": "Previous revenue", "change_pct": "Change %"}
        table = perf[list(cols)].rename(columns=cols).round(2)
        rd.sections.append(Section("All products", table=table, chart={
            "kind": "barh", "x": table.Product.head(12).tolist()[::-1], "series": {"Revenue": table.Revenue.head(12).tolist()[::-1]},
            "ylabel": "Revenue ($)"}))
        top3 = perf.head(3)
        rd.findings.append("Top products: " + ", ".join(f"{r.name} ({_m(r.revenue)})" for r in top3.itertuples()) + ".")
        share = perf.head(max(1, len(perf) // 5)).revenue.sum() / perf.revenue.sum() * 100
        rd.findings.append(f"The top 20% of products generate {share:.0f}% of revenue.")
        for r in perf.dropna(subset=["change_pct"]).sort_values("change_pct").head(3).itertuples():
            if r.change_pct < -10:
                rd.recommendations.append(f"{r.name}: revenue {r.change_pct:+.1f}% - review price, availability and promotion.")
    elif report_type == "customer":
        from app.analytics.customers import analyse
        r = analyse(db, persist=False)
        if not r["available"]:
            raise ValueError(r["message"])
        rd = ReportData(REPORT_TYPES["customer"], f"Snapshot {r['snapshot_date']} · dataset: {r['dataset']['name']}")
        k = r["kpis"]
        rd.kpis = [("Customers", f"{k['customers']:,}"), ("Orders", f"{k['orders']:,}"), ("Revenue", _m(k["revenue"])),
                   ("Avg. spend / customer", _m(k["avg_spend_per_customer"])), ("Repeat purchase rate", f"{k['repeat_purchase_rate_pct']}%"),
                   ("90-day retention", f"{k['retention_90d_pct']}%" if k["retention_90d_pct"] is not None else "n/a"),
                   ("Average CLV (estimate)", _m(k["avg_clv"]))]
        seg = pd.DataFrame(r["segments"])
        rd.sections.append(Section("Customer segments (RFM)", table=seg[["segment", "customers", "share_pct", "revenue", "revenue_share_pct",
                                                                         "avg_recency_days", "avg_frequency", "avg_monetary", "avg_clv"]],
                                   chart={"kind": "bar", "x": seg.segment.tolist(), "series": {"Customers": seg.customers.tolist()},
                                          "ylabel": "Customers"}))
        rd.sections.append(Section("Most valuable customers", table=pd.DataFrame(r["top_customers"])))
        rd.sections.append(Section("K-Means clusters", table=pd.DataFrame(r["clusters"]["profiles"]),
                                   text=r["clusters"]["method"] + f"; k = {r['clusters']['k']}."))
        for s in r["segments"]:
            rd.recommendations.append(f"{s['segment']}: {s['recommendations'][0]}")
        rd.findings.append(f"{seg.iloc[0].segment} account for {seg.iloc[0].revenue_share_pct}% of revenue." if len(seg) else "")
        rd.notes.append(r["assumptions"]["note"])
        if r["dataset"]["is_synthetic"]:
            rd.notes.append("The customer dataset is SYNTHETIC demonstration data.")
    elif report_type == "forecast":
        q = select(ForecastRun).order_by(ForecastRun.id.desc())
        runs = [db.get(ForecastRun, run_id)] if run_id else db.scalars(q.limit(30)).all()
        runs = [r for r in runs if r]
        if not runs:
            raise ValueError("No forecasts have been generated yet. Run a forecast first.")
        rd = ReportData(REPORT_TYPES["forecast"], f"{len(runs)} forecast run(s)")
        rows = []
        for r in runs:
            d = r.details
            sel = next(m for m in d["models"] if m["is_selected"])
            rows.append({"Run": r.id, "Product": d["product"]["name"], "Store": d["store"]["code"] if d["store"] else "All stores",
                         "Horizon (days)": r.horizon_days, "Model": d["best_model_label"],
                         "Predicted units": d["summary"]["total_predicted_units"],
                         "Test MAE": sel["test"].get("mae"), "Test WAPE %": sel["test"].get("wape"),
                         "Created": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else ""})
        rd.sections.append(Section("Forecast runs", table=pd.DataFrame(rows)))
        main = runs[0].details
        fc = pd.DataFrame(main["forecast"])
        rd.kpis = [("Product", main["product"]["name"]), ("Store", main["store"]["code"] if main["store"] else "All"),
                   ("Selected model", main["best_model_label"]), ("Horizon", f"{main['horizon']} days"),
                   ("Predicted units", f"{main['summary']['total_predicted_units']:,.0f}")]
        hist = main["history"][-60:]
        rd.sections.append(Section(f"Forecast - {main['product']['name']}", table=fc, chart={
            "kind": "line", "x": [h["date"] for h in hist] + fc.date.tolist(),
            "series": {"Actual": [h["actual"] for h in hist] + [None] * len(fc),
                       "Forecast": [None] * len(hist) + fc.predicted.tolist()}, "ylabel": "Units"}))
        mt = pd.DataFrame([{"Model": m["label"], "Selected": "yes" if m["is_selected"] else "",
                            **{f"Val {k.upper()}": v for k, v in m["validation"].items()},
                            **{f"Test {k.upper()}": v for k, v in m["test"].items()}} for m in main["models"]])
        rd.sections.append(Section("Model comparison", table=mt,
                                   text=f"Selection: {main['selection_metric']}. Splits: train {main['splits']['train'][0]}–"
                                        f"{main['splits']['train'][1]}, validation {main['splits']['validation'][0]}–"
                                        f"{main['splits']['validation'][1]}, test {main['splits']['test'][0]}–{main['splits']['test'][1]}."))
        if main.get("shap"):
            rd.findings.append(main["shap"]["summary"])
        rd.notes += main["assumptions"]
    elif report_type == "inventory":
        from app.inventory.optimizer import positions
        inv = positions(db)
        s = inv["summary"]
        rd = ReportData(REPORT_TYPES["inventory"], f"Stock position as of {hi:%d %b %Y}")
        rd.kpis = [("Items", str(s["total_items"]))] + [(k, str(v)) for k, v in s["counts"].items()] + [
            ("Stock value (cost)", _m(s["stock_value"])), ("Units to order", f"{s['units_to_order']:,}"),
            ("Order value (cost)", _m(s["recommended_order_value"]))]
        df = pd.DataFrame(inv["items"])
        cols = {"product_name": "Product", "store_code": "Store", "status": "Status", "on_hand": "On hand",
                "avg_daily_demand": "Avg daily demand", "safety_stock": "Safety stock", "reorder_point": "Reorder point",
                "recommended_stock_level": "Target level", "recommended_order_qty": "Order qty",
                "days_of_inventory": "Days of stock", "stockout_risk_pct": "Stock-out risk %", "supplier": "Supplier"}
        rd.sections.append(Section("Items needing attention", table=df[df.status.isin(["Critical", "Low Stock"])][list(cols)].rename(columns=cols),
                                   chart={"kind": "bar", "x": list(s["counts"]), "series": {"Items": list(s["counts"].values())},
                                          "ylabel": "Items"}))
        rd.sections.append(Section("All items", table=df[list(cols)].rename(columns=cols)))
        for it in df[df.status == "Critical"].head(8).itertuples():
            rd.recommendations.append(f"{it.product_name} @ {it.store_code}: {it.recommendation}")
        rd.notes += inv["assumptions"]["notes"]
    else:
        raise ValueError("Unknown report type")
    rd.notes = _synthetic_note(db) + rd.notes
    rd.findings = [f for f in rd.findings if f]
    return rd


# ------------------------------------------------------------------ renderers
def _chart_png(chart: dict) -> bytes:
    import matplotlib  # imported lazily: keeps API start-up memory low
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.2, 2.9 if chart["kind"] != "barh" else 3.6))
    colors = [BRAND, "#f59e0b", "#6366f1", "#ef4444"]
    if chart["kind"] == "line":
        x = pd.to_datetime(chart["x"])
        for i, (name, ys) in enumerate(chart["series"].items()):
            ax.plot(x, pd.to_numeric(pd.Series(ys), errors="coerce"), label=name, color=colors[i % 4], lw=1.6)
        fig.autofmt_xdate()
        if len(chart["series"]) > 1:
            ax.legend(frameon=False)
    elif chart["kind"] == "bar":
        name, ys = next(iter(chart["series"].items()))
        ax.bar([str(v) for v in chart["x"]], ys, color=BRAND)
        plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    else:
        name, ys = next(iter(chart["series"].items()))
        ax.barh([str(v)[:28] for v in chart["x"]], ys, color=BRAND)
    ax.set_ylabel(chart.get("ylabel", "") if chart["kind"] != "barh" else "")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y" if chart["kind"] != "barh" else "x", alpha=0.3)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    return buf.getvalue()


def _fmt(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "–"
    if isinstance(v, float):
        return f"{v:,.2f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def render_pdf(rd: ReportData) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Image,
        KeepTogether,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm, topMargin=1.5 * cm,
                            bottomMargin=1.5 * cm, title=rd.title, author="RetailIQ")
    ss = getSampleStyleSheet()
    brand = colors.HexColor(BRAND)
    h1 = ParagraphStyle("h1", parent=ss["Title"], alignment=0, textColor=colors.HexColor("#0f172a"), fontSize=20, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=brand, fontSize=13, spaceBefore=10, spaceAfter=6)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9.5, leading=13)
    small = ParagraphStyle("s", parent=body, fontSize=8, textColor=colors.HexColor("#64748b"))
    cell = ParagraphStyle("c", parent=body, fontSize=7.5, leading=9)
    story = [Paragraph('<font color="#0f766e"><b>Retail</b></font><b>IQ</b>', ParagraphStyle("logo", parent=body, fontSize=14)),
             Spacer(1, 6), Paragraph(rd.title, h1), Paragraph(rd.period, body),
             Paragraph(f"Generated {datetime.now():%d %b %Y, %H:%M}", small), Spacer(1, 10)]
    for n in rd.notes[:1]:
        story.append(Paragraph(f"<b>{n}</b>", ParagraphStyle("warn", parent=small, textColor=colors.HexColor("#b45309"))))
        story.append(Spacer(1, 6))
    if rd.kpis:
        cells = [[Paragraph(f'<font size="7.5" color="#64748b">{k.upper()}</font><br/><b>{v}</b>', body) for k, v in rd.kpis[i:i + 4]]
                 for i in range(0, len(rd.kpis), 4)]
        for row in cells:
            row += [""] * (4 - len(row))
        t = Table(cells, colWidths=[4.45 * cm] * 4)
        t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                               ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                               ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                               ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        story += [t, Spacer(1, 6)]
    if rd.findings:
        story.append(Paragraph("Key findings", h2))
        story += [Paragraph(f"• {f}", body) for f in rd.findings]
    for sec in rd.sections:
        block = [Paragraph(sec.heading, h2)]
        if sec.text:
            block.append(Paragraph(sec.text, small))
        if sec.chart:
            block.append(Image(io.BytesIO(_chart_png(sec.chart)), width=17.5 * cm, height=(7 if sec.chart["kind"] != "barh" else 8.7) * cm))
        story.append(KeepTogether(block))
        if sec.table is not None and not sec.table.empty:
            df = sec.table.head(40)
            data = [[Paragraph(f"<b>{c}</b>", cell) for c in df.columns]] + \
                   [[Paragraph(_fmt(v), cell) for v in row] for row in df.astype(object).where(df.notna(), None).values.tolist()]
            t = Table(data, repeatRows=1, colWidths=[17.8 * cm / len(df.columns)] * len(df.columns))
            t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ccfbf1")),
                                   ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                                   ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
                                   ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
            story.append(t)
            if len(sec.table) > 40:
                story.append(Paragraph(f"Showing 40 of {len(sec.table)} rows - the Excel/CSV export contains all rows.", small))
    if rd.recommendations:
        story.append(Paragraph("Recommendations", h2))
        story += [Paragraph(f"• {r}", body) for r in rd.recommendations]
    if rd.notes:
        story.append(Paragraph("Notes and assumptions", h2))
        story += [Paragraph(f"• {n}", small) for n in rd.notes]

    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#94a3b8"))
        canvas.drawString(1.6 * cm, 0.9 * cm, f"RetailIQ · {rd.title}")
        canvas.drawRightString(A4[0] - 1.6 * cm, 0.9 * cm, f"Page {doc_.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def render_xlsx(rd: ReportData) -> bytes:
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        summary_rows = [[rd.title], [rd.period], [f"Generated {datetime.now():%Y-%m-%d %H:%M}"], []]
        summary_rows += [["KPI", "Value"]] + [[k, v] for k, v in rd.kpis] + [[]]
        if rd.findings:
            summary_rows += [["Key findings"]] + [[f] for f in rd.findings] + [[]]
        if rd.recommendations:
            summary_rows += [["Recommendations"]] + [[r] for r in rd.recommendations] + [[]]
        if rd.notes:
            summary_rows += [["Notes"]] + [[n] for n in rd.notes]
        pd.DataFrame(summary_rows).to_excel(xw, sheet_name="Summary", index=False, header=False)
        ws = xw.sheets["Summary"]
        ws["A1"].font = Font(size=16, bold=True, color="0F766E")
        ws.column_dimensions["A"].width = 60
        ws.column_dimensions["B"].width = 24
        used = set()
        for sec in rd.sections:
            if sec.table is None or sec.table.empty:
                continue
            name = "".join(ch for ch in sec.heading if ch not in "[]:*?/\\")[:31]
            while name in used:
                name = name[:28] + str(len(used))
            used.add(name)
            sec.table.to_excel(xw, sheet_name=name, index=False)
            ws = xw.sheets[name]
            for c in ws[1]:
                c.font = Font(bold=True, color="FFFFFF")
                c.fill = PatternFill("solid", fgColor="0F766E")
                c.alignment = Alignment(horizontal="center")
            for i, col in enumerate(sec.table.columns, 1):
                width = max(len(str(col)), *(len(_fmt(v)) for v in sec.table[col].head(200))) + 2
                ws.column_dimensions[get_column_letter(i)].width = min(width, 45)
            ws.freeze_panes = "A2"
    return buf.getvalue()


def render_csv(rd: ReportData) -> bytes:
    """CSV holds the main table (the first section with a table) - tabular and machine-readable."""
    for sec in rd.sections:
        if sec.table is not None and not sec.table.empty:
            return sec.table.to_csv(index=False).encode("utf-8-sig")
    return pd.DataFrame(rd.kpis, columns=["KPI", "Value"]).to_csv(index=False).encode("utf-8-sig")


def generate_file(db: Session, report_type: str, fmt: str, out_dir: Path, **kw) -> tuple[Path, ReportData]:
    if fmt not in FORMATS:
        raise ValueError("Format must be pdf, xlsx or csv")
    rd = build(db, report_type, **kw)
    data = {"pdf": render_pdf, "xlsx": render_xlsx, "csv": render_csv}[fmt](rd)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = out_dir / f"retailiq_{report_type}_{stamp}.{fmt}"
    path.write_bytes(data)
    return path, rd

