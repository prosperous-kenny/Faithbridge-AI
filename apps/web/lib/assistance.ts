export type Priority = "critical" | "high" | "medium" | "low" | string;

export type AssistanceResult = {
  id: number;
  organization_id: number;
  description: string;
  category: string;
  urgency_score: number;
  priority: string;
  status: string;
  created_at: string;
};

export type PersonSummary = {
  id: number;
  full_name: string;
  email: string;
};

export type BeneficiarySummary = {
  id: number;
  organization_id: number;
  household_size: number;
  consented: boolean;
  person: PersonSummary | null;
};

export type AssistanceRequestDetail = {
  id: number;
  description: string;
  category: string;
  urgency_score: number;
  priority: string;
  status: string;
  created_at: string;
  beneficiary: BeneficiarySummary;
};

export const STATUSES = [
  "submitted",
  "triaged",
  "approved",
  "fulfilled",
  "declined",
] as const;

export const PRIORITY_STYLES: Record<string, string> = {
  critical: "bg-red-100 text-red-800",
  high: "bg-orange-100 text-orange-800",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-slate-100 text-slate-700",
};

export const STATUS_STYLES: Record<string, string> = {
  submitted: "bg-slate-100 text-slate-700",
  triaged: "bg-blue-100 text-blue-800",
  approved: "bg-green-100 text-green-800",
  fulfilled: "bg-emerald-100 text-emerald-800",
  declined: "bg-red-100 text-red-800",
};