import { NextResponse } from "next/server";

const API_URL = process.env.API_URL ?? "http://localhost:8000";
const ACCESS_TOKEN = process.env.FAITHBRIDGE_ACCESS_TOKEN;

/**
 * GET proxy for the public program directory. Donors see active programs
 * only — the pool the matching endpoint ranks against (PRD §20).
 */
export async function GET() {
  if (!ACCESS_TOKEN) {
    return NextResponse.json(
      {
        detail:
          "The program directory needs an authenticated user, but the " +
          "frontend has no sign-in flow yet. Set FAITHBRIDGE_ACCESS_TOKEN to " +
          "a local-mode JWT so the proxy can authenticate to the API.",
      },
      { status: 401 },
    );
  }
  try {
    const res = await fetch(`${API_URL}/api/v1/programs/`, {
      headers: { Authorization: `Bearer ${ACCESS_TOKEN}` },
      cache: "no-store",
    });
    return NextResponse.json(await res.json().catch(() => null), {
      status: res.status,
    });
  } catch {
    return NextResponse.json(
      { detail: "API service unreachable. Is the API running on port 8000?" },
      { status: 503 },
    );
  }
}