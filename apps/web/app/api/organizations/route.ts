import { NextResponse } from "next/server";
import { getAccessToken } from "@/lib/session";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

/**
 * GET proxy for listing organizations (admin-only in API).
 */
export async function GET(request: Request) {
  const token = await getAccessToken();
  if (!token) {
    return NextResponse.json(
      {
        detail: "Sign in to load organizations.",
      },
      { status: 401 },
    );
  }

  const { searchParams } = new URL(request.url);
  const url = new URL(`${API_URL}/api/v1/organizations/`);
  const limit = searchParams.get("limit");
  const offset = searchParams.get("offset");
  if (limit) url.searchParams.set("limit", limit);
  if (offset) url.searchParams.set("offset", offset);

  try {
    const res = await fetch(url.toString(), {
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

/**
 * POST proxy for creating organizations (admin-only).
 */
export async function POST(request: Request) {
  const token = await getAccessToken();
  if (!token) {
    return NextResponse.json(
      { detail: "Sign in to create an organization." },
      { status: 401 },
    );
  }
  try {
    const body = await request.json().catch(() => null);
    const res = await fetch(`${API_URL}/api/v1/organizations/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(body),
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
