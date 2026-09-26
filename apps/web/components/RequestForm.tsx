"use client";

import { useState } from "react";
import type { AssistanceResult } from "@/lib/assistance";

const SAMPLES = [
  "Family of four needs food support after losing income this month.",
  "Looking for help paying rent to avoid eviction next week.",
  "Need assistance with overdue medical bills for diabetes treatment.",
  "Seeking employment coaching and job placement support.",
];

const PRIORITY_STYLES: Record<string, string> = {
  critical: "bg-red-100 text-red-800",
  high: "bg-orange-100 text-orange-800",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-slate-100 text-slate-700",
};

export default function RequestForm() {
  const [description, setDescription] = useState("");
  const [result, setResult] = useState<AssistanceResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await fetch("/api/assistance", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `Request failed (HTTP ${res.status})`);
      }

      setResult((await res.json()) as AssistanceResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <form onSubmit={submit} className="fb-card">
        <label
          htmlFor="description"
          className="block font-semibold text-slate-900"
        >
          Describe the need
        </label>
        <p className="mt-1 text-sm text-slate-600">
          The AI service will classify this request and score its urgency.
        </p>
        <textarea
          id="description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={5}
          required
          minLength={10}
          maxLength={2000}
          placeholder="A family needs help with..."
          className="mt-4 w-full rounded-lg border border-slate-300 p-3 text-slate-900
            placeholder:text-slate-400 focus:border-amber-500 focus:outline-none
            focus:ring-2 focus:ring-amber-200"
        />

        <div className="mt-3 flex flex-wrap gap-2">
          {SAMPLES.map((sample) => (
            <button
              key={sample}
              type="button"
              onClick={() => setDescription(sample)}
              className="rounded-full border border-slate-200 px-3 py-1 text-xs
                text-slate-600 transition hover:border-amber-400 hover:bg-amber-50"
            >
              {sample.slice(0, 32)}…
            </button>
          ))}
        </div>

        <button
          type="submit"
          disabled={loading || description.trim().length < 10}
          className="fb-btn-primary mt-6"
        >
          {loading ? "Classifying…" : "Classify Request"}
        </button>
      </form>

      {error && (
        <div className="mt-6 rounded-lg border border-red-200 bg-red-50 px-5 py-4">
          <p className="font-semibold text-red-800">Request failed</p>
          <p className="mt-1 text-sm text-red-700">{error}</p>
        </div>
      )}

      {result && (
        <div className="fb-card mt-6 border-green-200 bg-green-50">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-semibold text-slate-900">Classification</h2>
            <span
              className={`rounded-full px-3 py-1 text-xs font-bold uppercase ${
                PRIORITY_STYLES[result.priority] ?? PRIORITY_STYLES.low
              }`}
            >
              {result.priority}
            </span>
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">
                Category
              </dt>
              <dd className="mt-1 font-semibold capitalize text-slate-900">
                {result.category}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">
                Urgency
              </dt>
              <dd className="mt-1 font-semibold text-slate-900">
                {result.urgency_score}/100
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">
                Status
              </dt>
              <dd className="mt-1 font-semibold capitalize text-slate-900">
                {result.status}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">
                Reference
              </dt>
              <dd className="mt-1 font-mono text-sm text-slate-700">
                {result.id}
              </dd>
            </div>
          </dl>
        </div>
      )}
    </div>
  );
}
