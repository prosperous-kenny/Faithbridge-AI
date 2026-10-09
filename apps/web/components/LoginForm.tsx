"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function LoginForm({ next }: { next: string }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const body = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(
          typeof body?.detail === "string"
            ? body.detail
            : `Sign-in failed (HTTP ${res.status})`,
        );
      }
      router.replace(next);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={submit} className="fb-card">
      <label htmlFor="email" className="block font-semibold text-slate-900">
        Email
      </label>
      <input
        id="email"
        type="email"
        autoComplete="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="you@example.org"
        className="mt-2 w-full rounded-lg border border-slate-300 p-3 text-slate-900
          placeholder:text-slate-400 focus:border-amber-500 focus:outline-none
          focus:ring-2 focus:ring-amber-200"
      />

      <label
        htmlFor="password"
        className="mt-6 block font-semibold text-slate-900"
      >
        Password
      </label>
      <input
        id="password"
        type="password"
        autoComplete="current-password"
        required
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className="mt-2 w-full rounded-lg border border-slate-300 p-3 text-slate-900
          focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-200"
      />

      <button
        type="submit"
        disabled={loading || !email || !password}
        className="fb-btn-primary mt-6 w-full"
      >
        {loading ? "Signing in…" : "Sign in"}
      </button>

      {error && (
        <div className="mt-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3">
          <p className="text-sm font-semibold text-red-800">{error}</p>
        </div>
      )}
    </form>
  );
}
