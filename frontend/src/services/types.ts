// Shapes of the main API responses (kept loose where the payload is purely presentational).
export type Role = "admin" | "analyst";
export interface User {
  id: number; email: string; full_name: string; job_title?: string | null; role: Role;
  is_active: boolean; created_at?: string; last_login_at?: string | null;
}
export interface TokenResponse { access_token: string; expires_in: number; user: User }

export interface FilterOptions {
  date_min: string | null; date_max: string | null;
  stores: { id: number; code: string; name: string; state: string }[];
  categories: { id: number; name: string }[];
  products: { id: number; sku: string; name: string; category_id: number }[];
  sales_rows: number; synthetic_data: boolean;
}

export interface Kpis {
  total_revenue: number; total_orders: number; units_sold: number; avg_order_value: number;
  total_products: number; num_stores: number; revenue_growth_pct: number | null;
  previous_period: { start: string; end: string; revenue: number } | null;
  forecasted_revenue_30d: number | null; forecast_method: string | null;
  period: { start: string; end: string; days: number };
  definitions: Record<string, string>;
}
export interface ProductPerf {
  product_id: number; sku: string; name: string; category: string; revenue: number; units: number;
  prev_revenue: number; change_pct: number | null;
}
export interface Dashboard {
  empty?: boolean;
  kpis: Kpis;
  revenue_over_time: { granularity: "day" | "week"; points: { date: string; revenue: number; units: number }[] };
  monthly_comparison: { years: string[]; points: Record<string, string | number>[] };
  by_category: { category: string; revenue: number; units: number; share_pct: number }[];
  top_products: ProductPerf[]; worst_products: ProductPerf[];
  stores: { store_id: number; code: string; name: string; state: string; revenue: number; units: number; revenue_per_day: number; growth_pct: number | null }[];
  by_weekday: { weekday: string; weekday_full: string; avg_revenue: number; avg_units: number }[];
  by_month: { month: string; total_revenue: number; avg_daily_revenue: number }[];
  revenue_distribution: { unit: string; bins: { range: string; from: number; to: number; count: number }[]; stats: { mean: number; median: number; std: number; n: number } | null };
  demand_trends: { products: string[]; points: Record<string, string | number>[] };
}

export interface Dataset {
  id: number; name: string; original_filename: string; kind: string; kind_label: string; n_rows: number; n_cols: number;
  status: string; is_synthetic: boolean; description?: string | null; imported_rows?: number | null;
  has_cleaned: boolean; has_rejected: boolean; created_at: string; updated_at: string;
}
export interface QualityColumn {
  name: string; dtype: string; inferred_type: string; missing: number; missing_pct: number; unique: number;
  sample_values: string[]; issues: string[]; min?: number; max?: number; mean?: number; outliers?: number; negative_values?: number;
}
export interface QualityReport {
  n_rows: number; n_cols: number; duplicate_rows: number; total_missing: number; detected_kind: string;
  detected_kind_label: string; required_columns: string[]; quality_score: number; columns: QualityColumn[];
}
export interface CleaningSummary {
  kind: string; rows_in: number; rows_clean: number; rows_rejected: number;
  steps: { step: string; detail: string; affected: number; changes?: Record<string, unknown> }[];
}
export interface Preview { columns: string[]; rows: (string | number | null)[][] }

export interface ModelResult {
  name: string; label: string; is_selected: boolean; mape_note?: string | null;
  validation: Record<string, number | null>; test: Record<string, number | null>;
}
export interface ForecastResult {
  run_id: number; created_at?: string;
  product: { id: number; sku: string; name: string }; store: { id: number; code: string; name: string } | null;
  horizon: number; eval_window_days: number; splits: Record<"train" | "validation" | "test", [string, string]>;
  selection_metric: string; best_model: string; best_model_label: string; models: ModelResult[];
  history: { date: string; actual: number }[]; backtest: Record<string, number | string | null>[];
  forecast: { date: string; predicted: number; lower: number; upper: number }[];
  interval: { coverage: number; method: string };
  summary: { total_predicted_units: number; avg_daily_units: number; recent_avg_daily_units: number; change_vs_recent_pct: number | null };
  shap: null | {
    model: string; model_label: string; note: string | null; summary: string;
    importance: { feature: string; label: string; mean_abs_shap: number; share_pct: number }[];
    first_forecast_day: { date: string; base_value: number; scale: string; contributions: { feature: string; label: string; value: number; contribution: number }[] };
  };
  assumptions: string[]; runtime_seconds: number;
}

export type InvStatus = "Critical" | "Low Stock" | "Overstocked" | "Healthy";
export interface InventoryItem {
  id: number; store_id: number; store_code: string; store_name: string; product_id: number; sku: string; product_name: string;
  category: string; supplier_id: number | null; supplier: string | null; on_hand: number; on_hand_source: string;
  lead_time_days: number; review_period_days: number; service_level: number; min_order_qty: number; pack_size: number;
  unit_cost: number | null; order_cost: number; holding_cost_rate: number; replenishment_policy: string;
  avg_daily_demand: number; demand_std: number; demand_source: string; expected_demand_lead_time: number;
  expected_demand_cycle: number; safety_stock: number; reorder_point: number; recommended_stock_level: number;
  recommended_order_qty: number; eoq: number | null; days_of_inventory: number | null; stockout_risk_pct: number;
  status: InvStatus; recommendation: string; stock_value: number; order_value: number; z: number;
}
export interface InventoryResponse {
  items: InventoryItem[];
  summary: { counts: Record<InvStatus, number>; total_items: number; stock_value: number; recommended_order_value: number; units_to_order: number };
  assumptions: { demand_window_days: number; overstock_days_of_cover: number; notes: string[] };
}

export interface Insight {
  category: string; severity: "critical" | "warning" | "positive" | "info"; title: string; finding: string;
  possible_causes: string[]; recommendation: string; metrics: Record<string, unknown>; link?: string | null;
}

export interface Notification { id: number; title: string; message: string; level: string; link?: string | null; is_read: boolean; created_at: string }
export interface ReportRow { id: number; title: string; file_format: string; report_type: string; created_at: string; available?: boolean }
