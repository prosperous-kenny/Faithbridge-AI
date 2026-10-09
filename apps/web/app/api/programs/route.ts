import { NextResponse } from "next/server";
import { getAccessToken } from "@/lib/session";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

/**
 * GET proxy for the public program directory. Donors see active programs
 * only — the pool the matching endpoint ranks against (PRD §20).
 */
export async function GET() {
  const token = await getAccessToken();
  if (!token) {
    return NextResponse.json(
      {
        detail: "Sign in to load the program directory.",
      },
      { status: 401 },
    );
  }
  try {
    const res = await fetch(`${API_URL}/api/v1/programs/`, {
      headers: { Authorization: `Bearer ${token}` },
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