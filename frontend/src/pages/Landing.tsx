import { Link } from "react-router-dom";
import {
  ArrowRight, BarChart3, Bot, Boxes, CheckCircle2, Database, FileText, LineChart, Lightbulb, Microscope, ShieldCheck,
  Smartphone, UsersRound,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useAuth } from "@/hooks/useAuth";
import { useTheme } from "@/hooks/useTheme";

const QUESTIONS = [
  "Which products generate the highest revenue?", "Which products are losing sales?",
  "What will demand look like in the coming weeks?", "Which products need restocking?",
  "Which customers are most valuable?", "Which stores perform better than others?",
  "What factors influence sales?", "What should management do next?",
];

const FEATURES = [
  { icon: <BarChart3 />, title: "BI dashboard", text: "Eight KPIs and ten interactive charts, all recalculated from the database whenever you change the date, store, category or product filters." },
  { icon: <LineChart />, title: "AI demand forecasting", text: "Naive, moving-average, Holt-Winters, Random Forest and XGBoost models compared on time-based splits, with prediction intervals and SHAP explanations." },
  { icon: <Boxes />, title: "Inventory optimisation", text: "Safety stock, reorder points, EOQ, days of cover and stock-out risk for every store and product, with documented assumptions." },
  { icon: <UsersRound />, title: "Customer intelligence", text: "RFM scoring, K-Means segmentation, CLV estimates, cohort retention and a playbook for each segment." },
  { icon: <Microscope />, title: "Automated EDA", text: "Descriptive statistics, correlations, distributions, box plots and outliers, with findings written in plain language." },
  { icon: <Database />, title: "Data management", text: "Upload CSV/Excel, get a data-quality report and run a transparent cleaning pipeline that never silently drops rows." },
  { icon: <Lightbulb />, title: "Business insights", text: "Declining products, anomalies, weak stores and shortages, with measured findings kept separate from hypotheses." },
  { icon: <Bot />, title: "AI assistant", text: "Ask questions in plain English. Answers come from verified calculations, with an optional LLM to explain them." },
  { icon: <FileText />, title: "Reports", text: "Daily, weekly, monthly, product, customer, forecast and inventory reports as PDF, Excel or CSV." },
];

export default function Landing() {
  const { user } = useAuth();
  const { resolved } = useTheme();
  return (
    <div className="min-h-[100dvh] overflow-x-hidden">
      <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-4 sm:px-6">
          <Logo />
          <nav className="ml-6 hidden items-center gap-6 text-sm text-muted-foreground md:flex">
            <a href="#features" className="hover:text-foreground">Features</a>
            <a href="#how" className="hover:text-foreground">How it works</a>
            <a href="#trust" className="hover:text-foreground">Methodology</a>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <ThemeToggle />
            {user ? (
              <Button asChild><Link to="/app/dashboard">Open app <ArrowRight /></Link></Button>
            ) : (
              <>
                <Button asChild variant="ghost" className="hidden sm:inline-flex"><Link to="/login">Log in</Link></Button>
                <Button asChild><Link to="/signup">Get started</Link></Button>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative">
        <div className="absolute inset-0 -z-10 bg-grid opacity-40 [mask-image:radial-gradient(ellipse_at_top,black_30%,transparent_70%)]" />
        <div className="absolute left-1/2 top-0 -z-10 h-72 w-[42rem] -translate-x-1/2 rounded-full bg-primary/20 blur-3xl" />
        <div className="mx-auto max-w-6xl px-4 pb-10 pt-14 text-center sm:px-6 sm:pt-20">
          <span className="inline-flex items-center gap-2 rounded-full border bg-background/70 px-3 py-1 text-xs font-medium text-muted-foreground">
            <span className="h-1.5 w-1.5 rounded-full bg-primary" /> Retail analytics · Forecasting · Inventory
          </span>
          <h1 className="mx-auto mt-5 max-w-3xl text-4xl font-semibold leading-[1.1] tracking-tight sm:text-5xl lg:text-6xl">
            Turn Retail Data Into <span className="bg-gradient-to-r from-teal-500 to-sky-500 bg-clip-text text-transparent">Smarter Decisions</span>
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-base text-muted-foreground sm:text-lg">
            RetailIQ turns raw sales, product, store and customer data into forecasts, stock recommendations and plain-language insights your team can act on.
          </p>
          <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
            <Button asChild size="lg"><Link to={user ? "/app/dashboard" : "/signup"}>Start analysing <ArrowRight /></Link></Button>
            <Button asChild size="lg" variant="outline"><Link to="/login">Try the demo account</Link></Button>
          </div>
          <div className="mx-auto mt-12 max-w-5xl rounded-2xl border bg-card p-2 shadow-2xl shadow-primary/10">
            <img src={resolved === "dark" ? "/screenshots/dashboard-dark.png" : "/screenshots/dashboard-light.png"}
              alt="RetailIQ dashboard showing revenue KPIs and charts" className="w-full rounded-xl border" loading="lazy"
              onError={(e) => { (e.currentTarget.parentElement as HTMLElement).style.display = "none"; }} />
          </div>
        </div>
      </section>

      {/* Questions */}
      <section className="border-y bg-muted/30">
        <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6">
          <h2 className="text-center text-2xl font-semibold tracking-tight sm:text-3xl">Answers to the questions retailers actually ask</h2>
          <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {QUESTIONS.map((q) => (
              <div key={q} className="flex items-start gap-2.5 rounded-xl border bg-card p-4 text-sm">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-primary" />{q}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="mx-auto max-w-6xl scroll-mt-20 px-4 py-16 sm:px-6">
        <p className="text-center text-sm font-semibold uppercase tracking-wider text-primary">Platform</p>
        <h2 className="mt-2 text-center text-2xl font-semibold tracking-tight sm:text-3xl">Everything from raw data to decisions</h2>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="group rounded-2xl border bg-card p-5 transition-all hover:-translate-y-0.5 hover:shadow-lg">
              <div className="mb-4 inline-flex rounded-xl bg-primary/10 p-2.5 text-primary [&_svg]:size-5">{f.icon}</div>
              <h3 className="font-semibold">{f.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{f.text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="scroll-mt-20 border-y bg-muted/30">
        <div className="mx-auto grid max-w-6xl gap-6 px-4 py-16 sm:px-6 md:grid-cols-3">
          {[
            ["1", "Bring your data", "Load the M5 Walmart files, upload CSV/Excel exports, or start with the clearly labelled synthetic sample."],
            ["2", "Analyse & forecast", "Clean and explore the data, compare five forecasting models and score customer segments."],
            ["3", "Act on it", "Follow restock recommendations and insights, ask the assistant, and share PDF/Excel reports."],
          ].map(([n, t, d]) => (
            <div key={n} className="rounded-2xl border bg-card p-6">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">{n}</span>
              <h3 className="mt-4 font-semibold">{t}</h3>
              <p className="mt-1.5 text-sm text-muted-foreground">{d}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Methodology / trust */}
      <section id="trust" className="mx-auto max-w-6xl scroll-mt-20 px-4 py-16 sm:px-6">
        <div className="grid gap-6 md:grid-cols-3">
          {[
            [<ShieldCheck key="s" />, "Honest analytics", "Time-based train/validation/test splits, no data leakage, real accuracy scores, and findings kept separate from hypotheses."],
            [<Smartphone key="m" />, "Works everywhere", "One responsive Progressive Web App for Windows, macOS, Android and iOS. Install it to your home screen."],
            [<Database key="d" />, "Built on solid foundations", "FastAPI, PostgreSQL, SQLAlchemy and Alembic, scikit-learn, XGBoost, statsmodels and SHAP."],
          ].map(([icon, t, d]) => (
            <div key={t as string} className="flex gap-4">
              <div className="h-fit rounded-xl bg-primary/10 p-2.5 text-primary [&_svg]:size-5">{icon}</div>
              <div><h3 className="font-semibold">{t}</h3><p className="mt-1 text-sm text-muted-foreground">{d}</p></div>
            </div>
          ))}
        </div>
        <div className="mt-14 rounded-2xl bg-[#0b1220] px-6 py-10 text-center text-white sm:px-12">
          <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">Ready to see your retail data clearly?</h2>
          <p className="mx-auto mt-2 max-w-xl text-slate-300">Log in with a demo account and explore every module in under a minute.</p>
          <Button asChild size="lg" className="mt-6 bg-teal-500 text-slate-950 hover:bg-teal-400"><Link to="/login">Explore the demo <ArrowRight /></Link></Button>
        </div>
      </section>

      <footer className="border-t">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-4 py-6 text-xs text-muted-foreground sm:flex-row sm:px-6">
          <Logo className="scale-90" />
          <p>The demo workspace uses clearly labelled synthetic data in the M5 format. It is not real Walmart data.</p>
        </div>
      </footer>
    </div>
  );
}
