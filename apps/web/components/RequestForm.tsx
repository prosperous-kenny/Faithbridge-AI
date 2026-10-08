"use client";

import { useState } from "react";
import type { AssistanceResult } from "@/lib/assistance";
import { PRIORITY_STYLES } from "@/lib/assistance";

const SAMPLES = [
  "Family of four needs food support after losing income this month.",
  "Looking for help paying rent to avoid eviction next week.",
  "Need assistance with overdue medical bills for diabetes treatment.",
  "Seeking employment coaching and job placement support.",
];

export default function RequestForm() {
  const [description, setDescription] = useState("");
  const [organizationId, setOrganizationId] = useState("1");
  const [result, setResult] = useState<AssistanceResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    const organization_id = Number(organizationId);
    if (!Number.isInteger(organization_id) || organization_id < 1) {
      setError("Organization ID must be a positive whole number.");
      setLoading(false);
      return;
    }

    try {
      const res = await fetch("/api/assistance", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description, organization_id }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        const detail =
          typeof body?.detail === "string"
            ? body.detail
            : `Request failed (HTTP ${res.status})`;
        const authHint =
          res.status === 401
            ? " Sign-in is not wired to this page yet; point a faith-leader or member at the local API, or set FAITHBRIDGE_ACCESS_TOKEN."
            : "";
        throw new Error(`${detail}${authHint}`);
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

        <label
          htmlFor="organizationId"
          className="mt-6 block font-semibold text-slate-900"
        >
          Organization ID
        </label>
        <p className="mt-1 text-sm text-slate-600">
          The organization whose queue should receive this request.
        </p>
        <input
          id="organizationId"
          type="number"
          min={1}
          step={1}
          value={organizationId}
          onChange={(e) => setOrganizationId(e.target.value)}
          className="mt-2 w-full rounded-lg border border-slate-300 p-3 text-slate-900
            focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-200
            sm:w-64"
        />

        <button
          type="submit"
          disabled={loading || description.trim().length < 10}
          className="fb-btn-primary mt-6"
        >
          {loading ? "Submitting…" : "Submit Request"}
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
            <h2 className="font-semibold text-slate-900">
              Request recorded
            </h2>
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
                #{result.id}
              </dd>
            </div>
          </dl>
        </div>
      )}
    </div>
  );
}