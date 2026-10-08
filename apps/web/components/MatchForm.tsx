"use client";

import { useEffect, useState } from "react";
import {
  CAUSES,
  formatCurrency,
  type Cause,
  type DonorPreferences,
  type MatchResponse,
} from "@/lib/matching";

function scorePercent(score: number): string {
  return `${Math.round(score * 100)}%`;
}

const CAUSE_STYLES: Record<string, string> = {
  food: "bg-emerald-100 text-emerald-800",
  housing: "bg-sky-100 text-sky-800",
  medical: "bg-rose-100 text-rose-800",
  education: "bg-indigo-100 text-indigo-800",
  employment: "bg-amber-100 text-amber-800",
  emergency: "bg-red-100 text-red-800",
};

export default function MatchForm() {
  const [causes, setCauses] = useState<Cause[]>([]);
  const [budget, setBudget] = useState("");
  const [location, setLocation] = useState("");
  const [matched, setMatched] = useState<MatchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [prefsNote, setPrefsNote] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/preferences", { cache: "no-store" });
        if (!res.ok) return;
        const prefs = (await res.json()) as DonorPreferences | null;
        if (!prefs || cancelled) return;
        setCauses(prefs.causes);
        if (typeof prefs.budget === "number") setBudget(String(prefs.budget));
        if (prefs.location) setLocation(prefs.location);
      } catch {
        // The form works without prefill; the submit path reports 401/503.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  function toggleCause(cause: Cause) {
    setCauses((current) =>
      current.includes(cause)
        ? current.filter((item) => item !== cause)
        : [...current, cause],
    );
  }

  async function findMatches(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setPrefsNote(null);
    setMatched(null);

    const budgetValue = budget.trim() === "" ? null : Number(budget);
    if (budget.trim() !== "" && (!Number.isFinite(budgetValue) || (budgetValue ?? 0) < 0)) {
      setError("Budget must be a non-negative number.");
      return;
    }
    if (causes.length === 0 && budgetValue === null && location.trim() === "") {
      setError("Choose at least one cause, or set a budget or location.");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch("/api/match-donors", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          causes,
          budget: budgetValue,
          location: location.trim() === "" ? null : location.trim(),
        }),
      });
      const body = await res.json().catch(() => null);
      if (!res.ok) {
        const detail =
          typeof body?.detail === "string"
            ? body.detail
            : `Matching failed (HTTP ${res.status})`;
        const authHint =
          res.status === 401
            ? " Sign-in is not wired to this page yet; set FAITHBRIDGE_ACCESS_TOKEN to a donor JWT."
            : "";
        throw new Error(`${detail}${authHint}`);
      }
      setMatched(body as MatchResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  async function savePreferences() {
    setError(null);
    setPrefsNote(null);
    const budgetValue = budget.trim() === "" ? null : Number(budget);
    if (budget.trim() !== "" && (!Number.isFinite(budgetValue) || (budgetValue ?? 0) < 0)) {
      setError("Budget must be a non-negative number.");
      return;
    }
    setSaving(true);
    try {
      const res = await fetch("/api/preferences", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          causes,
          budget: budgetValue,
          location: location.trim() === "" ? null : location.trim(),
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        const detail =
          typeof body?.detail === "string"
            ? body.detail
            : `Saving preferences failed (HTTP ${res.status})`;
        throw new Error(detail);
      }
      setPrefsNote("Saved. Matching now falls back to these preferences.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <form onSubmit={findMatches} className="fb-card">
        <legend className="block font-semibold text-slate-900">
          Causes you want to support
        </legend>
        <p className="mt-1 text-sm text-slate-600">
          Only programs in these categories are candidates; leave all unset to
          match against every cause.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          {CAUSES.map(({ value, label }) => {
            const selected = causes.includes(value);
            return (
              <button
                key={value}
                type="button"
                aria-pressed={selected}
                onClick={() => toggleCause(value)}
                className={`rounded-full border px-3 py-1.5 text-sm font-medium transition ${
                  selected
                    ? "border-amber-500 bg-amber-50 text-amber-900"
                    : "border-slate-200 text-slate-600 hover:border-amber-300 hover:bg-amber-50"
                }`}
              >
                {label}
              </button>
            );
          })}
        </div>

        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          <div>
            <label
              htmlFor="budget"
              className="block font-semibold text-slate-900"
            >
              Monthly budget (₦)
            </label>
            <p className="mt-1 text-sm text-slate-600">
              Programs needing more than this still rank, but score lower.
            </p>
            <input
              id="budget"
              type="number"
              min={0}
              step="any"
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
              placeholder="e.g. 50000"
              className="mt-2 w-full rounded-lg border border-slate-300 p-3 text-slate-900
                placeholder:text-slate-400 focus:border-amber-500 focus:outline-none
                focus:ring-2 focus:ring-amber-200"
            />
          </div>
          <div>
            <label
              htmlFor="location"
              className="block font-semibold text-slate-900"
            >
              Location
            </label>
            <p className="mt-1 text-sm text-slate-600">
              Programs in this area rank higher; others still appear.
            </p>
            <input
              id="location"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="e.g. Lagos"
              className="mt-2 w-full rounded-lg border border-slate-300 p-3 text-slate-900
                placeholder:text-slate-400 focus:border-amber-500 focus:outline-none
                focus:ring-2 focus:ring-amber-200"
            />
          </div>
        </div>

        <div className="mt-6 flex flex-wrap gap-3">
          <button
            type="submit"
            disabled={loading}
            className="fb-btn-primary"
          >
            {loading ? "Matching…" : "Find matches"}
          </button>
          <button
            type="button"
            onClick={savePreferences}
            disabled={saving}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold
              text-slate-700 transition hover:border-amber-400 hover:bg-amber-50"
          >
            {saving ? "Saving…" : "Save as my preferences"}
          </button>
        </div>
      </form>

      {prefsNote && (
        <div className="rounded-lg border border-green-200 bg-green-50 px-5 py-4">
          <p className="text-sm font-semibold text-green-800">{prefsNote}</p>
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-5 py-4">
          <p className="font-semibold text-red-800">Matching failed</p>
          <p className="mt-1 text-sm text-red-700">{error}</p>
        </div>
      )}

      {matched && (
        <section aria-label="Match results">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold text-slate-900">Ranked programs</h2>
            <span className="text-xs uppercase tracking-wide text-slate-500">
              engine {matched.engine}
            </span>
          </div>

          {matched.matches.length === 0 && (
            <p className="mt-4 text-slate-600">
              No active programs matched your criteria. Try widening the
              causes or budget.
            </p>
          )}

          <ol className="mt-4 space-y-4">
            {matched.matches.map((match, index) => (
              <li key={match.program_id} className="fb-card">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold text-slate-400">
                        #{index + 1}
                      </span>
                      <h3 className="font-semibold text-slate-900">
                        {match.program_name}
                      </h3>
                      <span
                        className={`rounded-full px-2.5 py-0.5 text-xs font-bold capitalize ${
                          CAUSE_STYLES[match.category] ?? CAUSE_STYLES.food
                        }`}
                      >
                        {match.category}
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-slate-600">
                      {match.organization_name}
                      {match.location ? ` · ${match.location}` : ""}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-2xl font-bold text-amber-700">
                      {scorePercent(match.match_score)}
                    </p>
                    <p className="text-xs uppercase tracking-wide text-slate-500">
                      match
                    </p>
                  </div>
                </div>

                <div className="mt-3 flex flex-wrap gap-2">
                  <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700">
                    Budget {formatCurrency(match.budget_needed)}
                  </span>
                  <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700">
                    {match.open_cases} open case
                    {match.open_cases === 1 ? "" : "s"} in the queue
                  </span>
                  {match.matches_causes && (
                    <span className="rounded-full bg-green-100 px-3 py-1 text-xs font-semibold text-green-800">
                      Your cause
                    </span>
                  )}
                  {match.matches_budget && (
                    <span className="rounded-full bg-green-100 px-3 py-1 text-xs font-semibold text-green-800">
                      Fits budget
                    </span>
                  )}
                  {match.matches_location && (
                    <span className="rounded-full bg-green-100 px-3 py-1 text-xs font-semibold text-green-800">
                      In your area
                    </span>
                  )}
                </div>

                {match.reason && (
                  <p className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700">
                    {match.reason}
                  </p>
                )}

                <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className="h-full rounded-full bg-amber-500"
                    style={{ width: scorePercent(match.match_score) }}
                  />
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}