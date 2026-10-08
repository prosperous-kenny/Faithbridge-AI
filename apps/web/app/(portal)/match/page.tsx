import MatchForm from "@/components/MatchForm";

export const metadata = {
  title: "Donor Matching — FaithBridge AI",
};

export default function MatchPage() {
  return (
    <div className="mx-auto max-w-4xl px-6 py-16">
      <h1 className="text-3xl font-bold text-slate-900">Donor Matching</h1>
      <p className="mt-2 text-slate-600">
        Tell FaithBridge which causes, budget and area matter to you, and it
        ranks the programs with live demand behind them. Summary counts only —
        no beneficiary is ever named here.
      </p>
      <div className="mt-10">
        <MatchForm />
      </div>
    </div>
  );
}