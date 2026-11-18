<div align="center">

<img src="frontend/public/icons/icon-192.png" width="84" alt="RetailIQ logo" />

# RetailIQ

### AI-Powered Business Intelligence, Sales Analytics, Demand Forecasting & Inventory Optimisation

**Turn Retail Data Into Smarter Decisions.**

FastAPI · PostgreSQL · SQLAlchemy/Alembic · pandas · scikit-learn · XGBoost · statsmodels · SHAP · React · TypeScript · Tailwind · shadcn/ui · Recharts · PWA

</div>

![RetailIQ dashboard](docs/screenshots/dashboard-light.png)

> **Data notice.** The bundled demo data is **synthetic**: computer-generated in the exact file format of the
> [M5 Walmart forecasting dataset](https://www.kaggle.com/competitions/m5-forecasting-accuracy/data).
> It is **not** real Walmart data and is labelled as synthetic everywhere in the app. The same ingestion
> pipeline loads the real M5 files (see [Dataset information](#9-dataset-information)).

---

## Table of contents
1. [Project overview](#1-project-overview)
2. [Problem statement](#2-problem-statement)
3. [Business objectives](#3-business-objectives)
4. [Features](#4-features)
5. [Technology stack](#5-technology-stack)
6. [System architecture](#6-system-architecture)
7. [Database architecture](#7-database-architecture)
8. [Machine-learning methodology](#8-machine-learning-methodology)
9. [Dataset information](#9-dataset-information)
10. [Model evaluation methodology](#10-model-evaluation-methodology)
11. [Installation](#11-installation)
12. [Running the application](#12-running-the-application)
13. [Screenshots](#13-screenshots)
14. [API documentation](#14-api-documentation)
15. [Future improvements](#15-future-improvements)
- [Testing](#testing) · [Deployment](#deployment) · [Project structure](#project-structure) · [Known limitations](#known-limitations)

---

## 1. Project overview
RetailIQ is a full-stack retail analytics platform. It ingests sales, product, store, calendar, price and
customer data into a normalised PostgreSQL database, then layers on:

- a **BI dashboard** whose KPIs and charts are all computed in SQL from the database,
- a **data-management module** with an automated, transparent cleaning pipeline,
- **automated EDA** with plain-language findings,
- **customer intelligence** (RFM + K-Means + CLV + cohort retention),
- **ML demand forecasting** comparing five models on time-based splits, with SHAP explanations,
- **inventory optimisation** (safety stock, reorder point, EOQ, stock-out risk),
- a **business-insights engine** that separates measured findings from hypotheses,
- an **AI assistant** that answers questions from verified calculations (with an optional LLM),
- **PDF / Excel / CSV reports**,

all in one responsive **Progressive Web App** that installs on Windows, macOS, Android and iOS.

## 2. Problem statement
Retailers collect large amounts of transactional data but often cannot answer basic operational questions
quickly: *What is selling? What is declining? How much will we sell next month? What must we reorder today?
Which customers matter most?* Spreadsheets do not scale, and generic BI tools do not forecast or recommend
actions. RetailIQ turns raw data into **answers and recommended actions**, and is explicit about uncertainty
and assumptions.

## 3. Business objectives
| # | Business question | Where RetailIQ answers it |
|---|---|---|
| 1 | Which products generate the highest revenue? | Dashboard → Top 10 products; Reports → Product performance |
| 2 | Which products are losing sales? | Dashboard → Worst performers; Insights → declining products |
| 3 | What will demand look like in the coming weeks? | Forecasting (7/14/30/60 days) |
| 4 | Which products need restocking? | Inventory → Critical / Low Stock items; Assistant |
| 5 | Which customers are most valuable? | Customer Intelligence → RFM segments, CLV, top customers |
| 6 | Which stores perform better than others? | Dashboard → Store-wise performance; Insights |
| 7 | What factors influence sales? | EDA (correlations, events), Forecasting → SHAP drivers |
| 8 | What should management do? | Insights → recommendations; Reports |

## 4. Features
**Authentication & security:** sign-up, login, logout, forgot/reset password, profile, change password;
bcrypt password hashing; JWT bearer tokens; role-based access (**Admin**: manage users, datasets & settings;
**Analyst**: upload data, dashboards, forecasts, reports); rate limiting; upload validation; CORS; security headers.

**Dashboard:** 8 KPI cards (Total Revenue, Total Orders, Units Sold, Average Order Value, Total Products,
Number of Stores, Revenue Growth, Forecasted Revenue) and 10 interactive charts (revenue over time, monthly
year-over-year comparison, revenue by category, top 10 products, worst performers, store performance, sales
by weekday, sales by month, revenue distribution, product demand trends). Date presets, custom range, and store,
category and product filters; every chart refreshes from the database.

**Data management:** CSV/XLSX/XLS upload (25 MB limit), preview, row/column counts, missing values,
duplicates, wrong data types, invalid values, outliers, quality score; cleaning pipeline (standardise names →
trim text → convert types → handle duplicates → validate required fields → validate values → report missing
values → flag outliers), with a **step-by-step change log**. Rejected rows are **kept in a downloadable file with
the reason**, never silently deleted. You can download raw, cleaned and rejected files, import into the warehouse,
and see the full dataset history.

**EDA:** mean, median, mode, std, min/max, quartiles, skewness, kurtosis; correlation matrix; histograms; box
plots (optionally grouped); scatter with trend line and Pearson r; missing-value and outlier analysis; column
pickers; findings in business language, generated from the data; downloadable Seaborn charts.

**Customer intelligence:** RFM scoring, 7 segments (Champions, Loyal, Potential Loyalists, New, Need
Attention, At Risk, Lost); K-Means with k chosen by silhouette score; CLV estimate; repeat-purchase rate;
90-day retention; monthly cohort retention heat-map; frequency distribution; top customers; a recommended
playbook per segment. If no customer data exists, the page explains why and links to the upload page.

**Forecasting:** see [§8](#8-machine-learning-methodology). Choose a product, a store or all stores, and a
7/14/30/60-day horizon. You get actual vs predicted with an 80 % interval, a model comparison table, a back-test
chart, SHAP global importance and first-day drivers, and CSV/PDF downloads.

**Inventory:** expected demand, safety stock, reorder point, recommended stock level, recommended order (pack size,
MOQ, EOQ policy), days of inventory, stock-out probability, and status (Healthy / Low Stock / Critical /
Overstocked). Lead time, service level, stock, supplier, costs and policy are editable per item; suppliers can be
managed; alerts become notifications; documented formulas and assumptions are shown in the app.

**Insights engine:** revenue trend, declining/growing products, anomalies (robust z-score), top/fastest
categories, under-performing stores, shortages, overstock, seasonality. Each insight has a **measured finding**,
**supporting data**, **possible explanations (hypotheses)** and a **recommendation**.

**AI assistant:** a chat interface. Questions map to a whitelist of read-only analytics functions;
**user text is never executed as SQL**. If `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` is set, an LLM writes a short
explanation of the verified results, labelled *AI-generated explanation*. Without a key it runs in rule-based
mode and never crashes.

**Reports:** Daily, Weekly, Monthly, Product, Customer, Forecast and Inventory reports in **PDF** (KPIs,
Matplotlib charts, tables, findings, recommendations, notes, generation date), **Excel** (summary sheet plus one
formatted sheet per table) and **CSV**.

**PWA & UX:** installable manifest, icons, iOS splash screens, service worker (app shell + offline
fallback; API never cached), mobile drawer navigation, touch-friendly targets, no page-level horizontal
scrolling, light/dark/system theme, skeleton loaders, empty states, error states with retry, toasts.

## 5. Technology stack
| Layer | Technologies |
|---|---|
| Frontend | React 18, TypeScript, Vite 5, Tailwind CSS 3, shadcn/ui-style components (Radix UI + CVA), Recharts, Lucide React, React Router 6, TanStack Query, Sonner |
| Backend | Python 3.10–3.13, FastAPI, Pydantic v2, pydantic-settings, Uvicorn |
| Data science | pandas, NumPy, SciPy, scikit-learn, XGBoost, statsmodels, SHAP, Matplotlib, Seaborn |
| Database | PostgreSQL 16 (SQLite fallback for zero-setup local runs), SQLAlchemy 2.0, Alembic |
| Auth | bcrypt, PyJWT (HS256), role-based dependencies |
| Reports | ReportLab (PDF), openpyxl (Excel) |
| Deployment | Docker, Docker Compose, nginx; single-container image for PaaS |
| Testing | pytest (81 tests), Vitest + Testing Library (10 tests), Playwright (manual end-to-end and mobile checks) |

## 6. System architecture
```mermaid
flowchart LR
  subgraph Client["Browser / installed PWA (Windows · macOS · Android · iOS)"]
    UI["React + TypeScript SPA<br/>Tailwind · shadcn/ui · Recharts"]
    SW["Service worker<br/>app shell + offline page"]
  end
  UI -- "JSON over HTTPS<br/>JWT bearer token" --> API
  subgraph Server["FastAPI backend"]
    API["REST API<br/>/api/*"] --> AUTH["Auth & RBAC<br/>bcrypt · JWT · rate limit"]
    API --> SVC["Services<br/>ingestion · cleaning · reports · assistant · insights"]
    SVC --> AN["Analytics<br/>sales SQL · EDA · RFM/K-Means"]
    SVC --> FC["Forecasting<br/>features · 5 models · SHAP"]
    SVC --> INV["Inventory optimiser"]
  end
  AN & FC & INV & SVC --> DB[("PostgreSQL<br/>SQLAlchemy + Alembic")]
  FC --> MS[["models/*.joblib"]]
  SVC --> FS[["data/uploads · data/processed · reports/"]]
  SVC -. optional .-> LLM["LLM API<br/>(Anthropic / OpenAI)"]
```
* **Dashboard aggregations run in SQL** (`GROUP BY` in the database). Joining the `calendar` table supplies
  weekday/month/fiscal week without database-specific date functions, so the same code runs on PostgreSQL and SQLite.
* In development, Vite proxies `/api` to FastAPI. In Docker, nginx serves the build and proxies `/api`. In the
  single-container image, FastAPI serves the built frontend itself.

## 7. Database architecture
21 tables, created by the Alembic migration `backend/alembic/versions/0001_initial_schema.py`, with primary keys,
foreign keys (cascade/restrict as appropriate), unique constraints, check constraints and indexes.

```mermaid
erDiagram
  categories ||--o{ products : contains
  products ||--o{ sales : sold_as
  stores ||--o{ sales : sells
  calendar ||--o{ sales : on_day
  products ||--o{ prices : priced
  stores ||--o{ prices : priced_in
  products ||--o{ inventory : stocked
  stores ||--o{ inventory : holds
  suppliers |o--o{ inventory : supplies
  products ||--o{ forecast_runs : forecast_for
  stores |o--o{ forecast_runs : forecast_in
  forecast_runs ||--o{ forecasts : produces
  forecast_runs ||--o{ model_evaluations : scored_by
  users ||--o{ datasets : uploads
  datasets ||--o{ data_quality_reports : profiled_by
  datasets ||--o{ customers : imports
  customers ||--o{ customer_transactions : places
  customers ||--|| customer_segments : segmented_as
  users ||--o{ notifications : receives
  users ||--o{ reports : generates
```
| Table | Purpose | Key constraints |
|---|---|---|
| `users` | accounts, bcrypt hash, role, reset-token hash | unique email; enum role |
| `categories`, `stores`, `products` | dimensions | unique name / code / sku; FK product→category |
| `calendar` | one row per date: events, SNAP flags, fiscal week | PK date |
| `prices` | weekly sell price per store × product | unique (store, product, week); price ≥ 0 |
| `sales` | daily units & revenue per store × product | unique (date, store, product); units ≥ 0; indexes (store, date), (product, date) |
| `inventory`, `suppliers` | stock position & replenishment parameters | unique (store, product); on_hand ≥ 0; 0 < service level < 1 |
| `forecast_runs`, `forecasts`, `model_evaluations` | every forecast with its splits, predictions and **real** metrics | FK cascade to run |
| `datasets`, `data_quality_reports` | upload history, raw/cleaned profiles, cleaning log | FK cascade |
| `customers`, `customer_transactions`, `customer_segments` | uploaded customer data and RFM/K-Means results | unique (dataset, external_id) |
| `notifications`, `reports`, `app_settings` | alerts, generated files, admin-editable assumptions | |

**Migration commands** (run from `backend/`):
```bash
alembic upgrade head                              # create / upgrade the schema
alembic downgrade base                            # drop everything
alembic revision --autogenerate -m "describe"     # after changing app/models/*
```

## 8. Machine-learning methodology
**Target:** daily units for one product in one store (or summed over all stores). Days without sales are
re-inserted as zeros.

**Features** (`backend/app/forecasting/features.py`):
| Group | Features |
|---|---|
| Historical sales | lag 1, 7, 14, 28 days |
| Moving averages / rolling statistics | 7- and 28-day rolling mean, 7-day rolling std (on the series **shifted by one day**) |
| Calendar | day of week, weekend, month, day of month, week of year |
| Holidays & events | event flag, event type (National / Cultural / Religious / Sporting), day-before-event |
| SNAP | SNAP benefit day for the store's state (M5 feature) |
| Price | weekly price, price ÷ 4-week average, promotion flag |

**Leakage prevention:** every target-derived feature for day *t* uses data up to *t−1*. Tests assert that the
vectorised training features and the single-step features used during recursive forecasting are identical
(`tests/test_forecasting.py`).

**Models** (`backend/app/forecasting/models.py`):
1. **Naive baseline:** same weekday last week (seasonal naive)
2. **Moving average:** mean of the last 28 days
3. **Exponential smoothing:** Holt-Winters, damped additive trend + weekly seasonality (statsmodels)
4. **Random Forest:** scikit-learn, 200 trees
5. **XGBoost:** Tweedie objective (suited to intermittent retail counts, popular in the M5 competition)

Tree models forecast **recursively**: each prediction is fed back as a lag for the next day, exactly as in production.

**Prediction intervals:** empirical 10th/90th percentiles of the selected model's hold-out errors (validation +
test), added to the point forecast and clipped at zero, giving an 80 % interval.

**Explainability:** SHAP `TreeExplainer` on the tree model: global mean |SHAP| ranking and the feature
contributions for the first forecast day. If the winning model is not tree-based, the app explains the best tree
model instead and says so. SHAP describes what the model learned (association), not causation.

**Customer segmentation:** RFM quintile scores (1–5) → rule-based segments; K-Means on standardised
log(R, F, M), k ∈ {3…6} chosen by silhouette score; CLV = AOV × orders/year × lifespan × margin (assumptions
are editable in Settings).

**Inventory:** safety stock = z·σ·√L; reorder point = D<sub>L</sub> + SS; target = D<sub>L+R</sub> + SS;
EOQ = √(2DS/H); stock-out risk = 1 − Φ((stock − D<sub>L</sub>)/(σ√L)). D comes from the latest forecast, or
recent average demand if no forecast exists.

## 9. Dataset information
**Primary dataset: M5 Forecasting (Walmart).** It contains daily unit sales for 3,049 products in 10 stores
across California, Texas and Wisconsin, with a calendar (events, SNAP days) and weekly prices.
`backend/app/services/m5_ingestion.py` maps it into the schema: the wide `d_1…d_1941` table is melted to long
format, joined to the calendar and weekly prices, and revenue is calculated. Only days with sales are stored. Loading
is idempotent and supports subsets (stores, items, dates), because the full dataset (~59M cells) is too large for a
laptop demo.

**Using the real M5 data:**
1. Download `calendar.csv`, `sell_prices.csv`, `sales_train_evaluation.csv` from
   <https://www.kaggle.com/competitions/m5-forecasting-accuracy/data> (Kaggle login required) into `data/m5/`.
2. From `backend/`:
   ```bash
   python -m scripts.seed --m5-dir ../data/m5 --stores CA_1,TX_1,WI_1 --max-items 60 --start-date 2014-01-01
   ```
   M5 has **no stock levels**, so stock is initialised as an explicitly *assumed* 14 days of cover (flagged
   `assumed` in the UI) until you enter real figures.

**Bundled synthetic sample** (`data/sample/`, created by `backend/app/services/sample_data.py`):
| File | Content |
|---|---|
| `m5_synthetic/` | M5-format files: 10 stores × 30 products × 730 days (Nov 2024 – Oct 2026). Weekly/yearly seasonality, trends, holidays, Christmas closures, SNAP effects, promotions with price elasticity, negative-binomial noise. Includes synthetic stock levels and suppliers. |
| `customer_transactions_synthetic.csv` | ~1,200 synthetic customers / 33k transaction lines for the RFM module. It is **independent** of the M5 data, because M5 has no customer information and none is ever derived from it. |
| `messy_sales_sample.csv` | 428 rows with deliberate problems (missing values, duplicates, `$` prices, a bad date, negative units, an outlier) for trying the cleaning pipeline. |

Regenerate with `python -m app.services.sample_data` (deterministic seeds).

**Upload formats.** *Daily sales:* `date, store, product, units` (+ optional `price, category, product_name, state`).
*Customer transactions:* `customer_id, order_id, order_date, amount` (+ optional `quantity, category, store, city`).
Common alternative column names (e.g. `InvoiceNo`, `Item-ID`, `Units Sold`) are mapped automatically.

## 10. Model evaluation methodology
```
|────────────── train ──────────────|── validation (E days) ──|── test (E days) ──|→ future (H days)
E = min(max(H, 14), 56)
```
1. Every model is trained on **train** and forecasts **validation** → the **lowest validation WAPE** wins (RMSE breaks ties).
2. Every model is re-trained on **train + validation** and forecasts **test**. These test scores are the reported
   accuracy, because the test window played no part in choosing the model.
3. The winner is re-trained on all data to forecast the future.

| Metric | Definition | Note |
|---|---|---|
| MAE | mean \|forecast − actual\| | in units per day |
| RMSE | √mean(error²) | penalises big misses |
| MAPE | mean \|error\| / actual | **only** when ≥ 90 % of days have sales; otherwise reported as *n/a* with the reason |
| WAPE | Σ\|error\| / Σ actual | robust with zero-sales days, so used for model selection |
| Bias | Σ(forecast − actual) / Σ actual | > 0 over-forecast, < 0 under-forecast |

All metrics are computed on real hold-out data and stored in `model_evaluations`. Nothing is hard-coded. On the
synthetic sample, typical single-store item test WAPE is roughly 25–45 %, and ML models usually beat the naive
baseline, though not always. Highly intermittent items (< 1 unit/day) give very high WAPE for every model, as
expected.

## 11. Installation
Prerequisites: **Python 3.10–3.13**, **Node.js 18+** (20 LTS recommended), and optionally **PostgreSQL 14+**
or **Docker Desktop**.

### Option A: local development (Windows PowerShell)
```powershell
cd RetailIQ
copy .env.example .env          # then edit SECRET_KEY (and DATABASE_URL, see below)

# Backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1    # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements-dev.txt
alembic upgrade head            # create tables
python -m scripts.seed          # demo users + SYNTHETIC sample data (~10 s)

# Frontend (new terminal)
cd frontend
npm install
```
macOS / Linux: same steps with `cp .env.example .env` and `source .venv/bin/activate`.

**Database choice:** with PostgreSQL installed, create a database and set
`DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/retailiq` in `.env`. To try the app without
PostgreSQL, **delete the value** (`DATABASE_URL=`) and a SQLite file `data/retailiq.db` is used automatically.

> Anaconda users: you can use `conda create -n retailiq python=3.12` and `conda activate retailiq` instead of the venv.

### Option B: Docker (PostgreSQL + API + web)
```bash
cp .env.example .env            # set POSTGRES_PASSWORD and SECRET_KEY
docker compose up --build
```
Open <http://localhost:8080>. Migrations and the demo data run automatically on first start.

## 12. Running the application
```powershell
# terminal 1 - API on http://localhost:8000  (Swagger UI at /docs)
cd backend; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload

# terminal 2 - web app on http://localhost:5173
cd frontend; npm run dev
```
**Demo accounts** (created by the seed script; change them in production):

| Role | Email | Password |
|---|---|---|
| Admin | `admin@retailiq.dev` | `Admin@12345` |
| Analyst | `analyst@retailiq.dev` | `Analyst@12345` |

The login page also has one-click **Admin demo** / **Analyst demo** buttons.

**Install as an app:** open the site in Chrome/Edge (desktop or Android) and choose *Install app* (⊕ icon in the
address bar or ⋮ menu). In Safari on iPhone/iPad, tap Share → *Add to Home Screen*. Installation needs HTTPS or
`localhost`. To test on a phone on your Wi-Fi, use `npm run dev` (it listens on your LAN IP) or deploy online.

**Production build locally:** `cd frontend && npm run build`, then set `FRONTEND_DIST=../frontend/dist` and run
uvicorn: the API serves the web app on port 8000.

## 13. Screenshots
| Dashboard (light) | Dashboard (dark) |
|---|---|
| ![](docs/screenshots/dashboard-light.png) | ![](docs/screenshots/dashboard-dark.png) |
| **Demand forecasting** | **Inventory optimisation** |
| ![](docs/screenshots/forecasting.png) | ![](docs/screenshots/inventory.png) |
| **Customer intelligence** | **Exploratory analysis** |
| ![](docs/screenshots/customers.png) | ![](docs/screenshots/eda.png) |
| **Business insights** | **AI assistant** |
| ![](docs/screenshots/insights.png) | ![](docs/screenshots/assistant.png) |
| **Data management** | **Mobile** |
| ![](docs/screenshots/data-management.png) | <img src="docs/screenshots/mobile-dashboard.png" width="260" /> |

## 14. API documentation
Interactive docs: **<http://localhost:8000/docs>** (Swagger) and `/redoc`. All endpoints except auth and
health require `Authorization: Bearer <token>`.

| Method & path | Role | Description |
|---|---|---|
| `POST /api/auth/register` · `POST /api/auth/login` | public | create account / get JWT |
| `GET·PATCH /api/auth/me` · `POST /api/auth/change-password` | user | profile |
| `POST /api/auth/forgot-password` · `POST /api/auth/reset-password` | public | password reset (rate-limited) |
| `GET·POST /api/admin/users` · `PATCH·DELETE /api/admin/users/{id}` | admin | user management |
| `GET /api/admin/settings` · `PUT /api/admin/settings/{section}` | user / admin | business assumptions |
| `GET /api/meta/filters` | user | stores, categories, products, date range |
| `GET /api/dashboard?start&end&stores&categories&products` | user | KPIs + 10 chart datasets |
| `GET /api/datasets` · `POST /api/datasets/upload` | user | history / upload (CSV, XLSX) |
| `GET /api/datasets/{id}` · `POST …/clean` · `POST …/import` · `GET …/download/{raw\|cleaned\|rejected}` | user | quality report, cleaning, import, downloads |
| `DELETE /api/datasets/{id}` | admin | delete dataset |
| `GET /api/datasets/samples[/{name}]` | user | bundled sample files |
| `GET /api/eda/{sources,summary,histogram,box,scatter,correlation,plot.png}` | user | EDA |
| `GET /api/customers/analysis?dataset_id` | user | RFM, clusters, CLV, retention |
| `POST /api/forecasting/run` `{product_id, store_id?, horizon}` | user | train, compare, forecast |
| `GET /api/forecasting/{history,runs,runs/{id},runs/{id}/download}` | user | series, history, CSV |
| `GET /api/inventory?store_id&category_id&status&search` · `PATCH /api/inventory/{id}` | user | positions / configure item |
| `GET·POST /api/suppliers` · `PUT /api/suppliers/{id}` · `POST /api/inventory/alerts` | user | suppliers, alerts |
| `GET /api/insights` | user | insights engine |
| `POST /api/assistant/ask` `{question}` · `GET /api/assistant/info` | user | assistant (rate-limited) |
| `GET /api/reports/types` · `POST /api/reports` · `GET /api/reports` · `GET /api/reports/{id}/download` | user | reports |
| `GET /api/notifications` · `POST …/read-all` · `POST …/{id}/read` | user | notifications |
| `GET /api/health` | public | liveness + DB check |

## 15. Future improvements
- Global (cross-product) ML model with hierarchical reconciliation, LightGBM, and Optuna hyper-parameter search
- Background job queue (Celery/RQ) for long forecasts and batch re-forecasting of all items
- Email delivery for password resets, scheduled reports and stock alerts
- Redis-backed rate limiting and caching for multi-instance deployments
- Price-elasticity and promotion-uplift modelling; what-if simulations
- Multi-tenant organisations, audit log, SSO (OAuth/OIDC), httpOnly-cookie sessions with refresh tokens
- Playwright end-to-end tests in CI (GitHub Actions)

---

## Testing
```bash
cd backend && pytest                       # 81 tests on a temporary SQLite DB (migrations included)
TEST_DATABASE_URL=postgresql+psycopg://retailiq:retailiq@localhost:5432/retailiq_test pytest   # same suite on PostgreSQL
cd frontend && npm test && npm run lint    # 10 Vitest tests + TypeScript type check
```
Backend tests cover authentication (hashing, JWT expiry, RBAC, reset flow, rate limiting), API endpoints,
dashboard figures checked against independent SQL, filters, upload validation, the cleaning pipeline
(nothing silently dropped, outliers flagged not removed), database constraints, forecasting (metrics, leakage,
time-split ordering, model selection), inventory formulas (including the spec's "Milk" example), customer
analytics, insights, all assistant intents without an LLM, and all 7 report types × 3 formats.

## Deployment
**Option 1 (recommended, free): Render Blueprint + Neon PostgreSQL.** The repo contains `render.yaml`:
in Render choose *New → Blueprint*, select the GitHub repo, and paste a Neon connection string into `DATABASE_URL`
(leave it empty for a temporary SQLite demo that resets on every restart). Render generates `SECRET_KEY`, and the
blueprint switches on `PROTECT_DEMO_ACCOUNTS` and turns off on-screen reset tokens. Peak memory is about 420 MB, within
the free 512 MB instance. The free instance sleeps after 15 minutes idle; the first visit afterwards takes about a minute.

**Option 1b: one container + managed PostgreSQL on any Docker host (Render / Railway / Fly.io).**
1. Push the project to GitHub.
2. Create a managed PostgreSQL database (Render, Railway, Neon or Supabase) and copy its connection string.
3. Create a *Web Service* from the repo using the root `Dockerfile`. Set the environment variables
   `DATABASE_URL`, `SECRET_KEY` (long random string), `EXPOSE_RESET_TOKEN=false`, `CORS_ORIGINS=https://<your-app-domain>`,
   and optionally `SEED_DEMO_DATA=true` and an LLM key.
4. Deploy. The container runs `alembic upgrade head`, loads the demo data (if enabled) and serves both the web app and the
   API on `$PORT`. HTTPS from the host makes the PWA installable.

**Option 2: Docker Compose on a VM** (e.g. a small cloud VM): install Docker, copy the project, set `.env`,
`docker compose up -d --build`, and put a reverse proxy with HTTPS (Caddy / nginx + Let's Encrypt) in front of port 8080.

**Option 3: split hosting:** frontend on Vercel/Netlify (`npm run build`, set `VITE_API_URL=https://api.example.com`,
SPA rewrite to `index.html`), backend container on Render/Railway with `CORS_ORIGINS` set to the frontend URL.

Production checklist: strong `SECRET_KEY`; `EXPOSE_RESET_TOKEN=false`; change or remove the demo accounts;
restrict `CORS_ORIGINS`; HTTPS only; regular database backups.

## Project structure
```
RetailIQ/
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI routers: auth, admin, datasets, analytics, operations
│   │   ├── core/           # config, security (bcrypt/JWT), RBAC dependencies, rate limiter, logging
│   │   ├── models/         # SQLAlchemy ORM models (21 tables)
│   │   ├── schemas/        # Pydantic request/response models
│   │   ├── database/       # engine + session
│   │   ├── services/       # M5 ingestion, sample data, data quality/cleaning, import, insights, assistant, reports
│   │   ├── analytics/      # sales SQL analytics, EDA, customer RFM/K-Means
│   │   ├── forecasting/    # features, models, metrics, pipeline, SHAP
│   │   ├── inventory/      # optimiser
│   │   └── main.py         # app entry point
│   ├── alembic/            # migrations
│   ├── scripts/            # seed.py, docker-entrypoint.sh
│   ├── tests/              # pytest suite
│   └── requirements.txt
├── frontend/
│   ├── src/{components,pages,layouts,charts,services,hooks,utils,lib,test}
│   ├── public/             # manifest, service worker, offline page, icons, splash screens
│   └── package.json
├── data/{sample,processed,uploads,m5}
├── models/                 # saved forecast models (joblib)
├── notebooks/              # 01_retailiq_walkthrough.ipynb - the data science step by step
├── reports/                # generated reports
├── docs/screenshots/
├── docker-compose.yml · Dockerfile · .env.example · .gitignore
```

## Known limitations
- The demo data is **synthetic**; conclusions drawn from it do not describe a real business.
- M5 has no basket IDs, so "Total Orders" counts *sales transactions* (store × product × day records with sales); the
  definition is shown in the KPI tooltip.
- Forecasts are per series and trained on demand (~2–5 s each); there is no batch re-forecasting job yet.
- The rate limiter is in-memory (per process). Use Redis when running several backend instances.
- No email server: in development the password-reset link is shown on screen (`EXPOSE_RESET_TOKEN=true`).
- JWTs are stored in `localStorage` (simple and works in installed PWAs); httpOnly cookies would harden this further.
- Docker images were not built in the development environment (Docker Hub was not reachable there). The compose file
  is syntax-validated and the same steps were run natively.
