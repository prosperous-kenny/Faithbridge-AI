export type Cause =
  | "food"
  | "housing"
  | "medical"
  | "education"
  | "employment"
  | "emergency";

export const CAUSES: { value: Cause; label: string }[] = [
  { value: "food", label: "Food Assistance" },
  { value: "housing", label: "Housing & Shelter" },
  { value: "medical", label: "Medical Care" },
  { value: "education", label: "Education" },
  { value: "employment", label: "Employment Support" },
  { value: "emergency", label: "Emergency Relief" },
];

export type DonorPreferences = {
  causes: Cause[];
  budget: number | null;
  location: string | null;
};

export type MatchItem = {
  program_id: number;
  program_name: string;
  organization_name: string;
  category: string;
  location: string | null;
  budget_needed: number | null;
  open_cases: number;
  match_score: number;
  matches_causes: boolean;
  matches_budget: boolean;
  matches_location: boolean;
  reason: string;
};

export type MatchResponse = {
  engine: string;
  matches: MatchItem[];
};

export function formatCurrency(amount: number | null | undefined): string {
  if (amount === null || amount === undefined) return "—";
  return new Intl.NumberFormat("en-NG", {
    style: "currency",
    currency: "NGN",
    maximumFractionDigits: 0,
  }).format(amount);
}