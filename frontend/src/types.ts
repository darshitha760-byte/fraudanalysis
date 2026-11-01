export type Role = "admin" | "analyst" | "viewer";
export interface User {
  id: number;
  full_name: string;
  email: string;
  role: Role;
  is_active: boolean;
}
export interface Transaction {
  id: number;
  transaction_id: string;
  customer_id: number;
  amount: number;
  currency: string;
  merchant_name: string | null;
  transaction_date: string;
  status: string;
  risk_score: number | null;
  risk_level: string | null;
}
export interface Paginated<T> {
  data: T[];
  pagination: { page: number; limit: number; total: number; pages: number };
}
export interface Overview {
  total_transactions: number;
  total_alerts: number;
  pending_alerts: number;
  under_review_alerts: number;
  high_risk_customers_count: number;
  fraud_confirmation_rate: number;
  false_positive_rate: number;
  risk_distribution: Record<string, number>;
}
export interface TransactionStats {
  total_transactions: number;
  total_volume: number;
  average_amount: number;
  high_risk_transactions: number;
  medium_risk_transactions: number;
  low_risk_transactions: number;
}
export interface Trend { date: string; transaction_count: number; total_volume: number }
export interface CustomerRisk {
  customer_id: string;
  total_transactions: number;
  high_risk_count: number;
  fraud_rate: number;
  average_transaction_amount: number;
  risk_profile: string;
  suspicious_patterns: string[];
}
export interface Alert {
  alert_id: number;
  transaction_id: number;
  risk_score: number;
  risk_level: string;
  alert_status: string;
  alert_severity: string;
  created_at: string;
}
export interface AlertDetail extends Alert {
  customer_id: number;
  triggered_rules: string[];
  analyst_notes: string | null;
}
export type Algorithm = "random_forest" | "logistic_regression" | "isolation_forest";
export interface Model {
  id: string;
  name: string;
  version: string;
  training_date: string | null;
  dataset_size: number | null;
  total_samples: number | null;
  data_source: string;
  evaluation_only: boolean;
  metrics: {
    accuracy?: number;
    precision?: number;
    recall?: number;
    f1_score?: number;
    roc_auc?: number | null;
    confusion_matrix?: Record<string, number>;
  };
  cv_mean: number | null;
  feature_importance: number[];
  feature_names: string[];
}
export interface Rule {
  id: number;
  rule_id: string;
  name: string;
  description: string;
  rule_type: string;
  is_enabled: boolean;
  severity: string;
  risk_weight: number;
  threshold_value: number | null;
}
export interface AuditEvent {
  id: number;
  timestamp: string;
  actor: string;
  action: string;
  target_type: string;
  target_id: string;
  status: string;
  details: string;
}
