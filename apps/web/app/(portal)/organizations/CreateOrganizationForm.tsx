"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const ORG_TYPES = ["church", "mosque", "ministry", "ngo"] as const;

export default function CreateOrganizationForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [orgType, setOrgType] = useState<(typeof ORG_TYPES)[number]>("church");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccess(null);

    try {
      const res = await fetch("/api/organizations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, org_type: orgType }),
      });

      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        const msg =
          detail?.detail ?? detail?.error ?? res.statusText ?? "Creation failed";
        throw new Error(msg);
      }

      setSuccess("Organization created successfully.");
      setName("");
      setOrgType("church");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label
          htmlFor="org-name"
          className="block text-sm font-medium text-slate-700"
        >
          Organization name
        </label>
        <input
          id="org-name"
          name="name"
          type="text"
          required
          minLength={1}
          maxLength={200}
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
          placeholder="e.g., Grace Community Church"
        />
      </div>

      <div>
        <label
          htmlFor="org-type"
          className="block text-sm font-medium text-slate-700"
        >
          Organization type
        </label>
        <select
          id="org-type"
          name="org_type"
          value={orgType}
          onChange={(e) => setOrgType(e.target.value as typeof ORG_TYPES[number])}
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
        >
          {ORG_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>

      {error ? (
        <p className="text-sm text-red-600" role="alert">
          {error}
        </p>
      ) : null}
      {success ? (
        <p className="text-sm text-green-700" role="status">
          {success}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={submitting || !name.trim()}
        className="inline-flex justify-center rounded-md border border-transparent bg-amber-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-amber-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {submitting ? "Creating…" : "Create organization"}
      </button>
    </form>
  );
}
