import { NextResponse } from "next/server";
import { getAccessToken } from "@/lib/session";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON body" }, { status: 400 });
  }

  const data = (body as { description?: string; organization_id?: unknown } | null) ?? {};
  const description = data.description;
  const organization_id = data.organization_id;

  if (typeof description !== "string" || description.trim().length < 10) {
    return NextResponse.json(
      { detail: "Description must be at least 10 characters" },
      { status: 400 },
    );
  }
  if (
    typeof organization_id !== "number" ||
    !Number.isInteger(organization_id) ||
    organization_id < 1
  ) {
    return NextResponse.json(
      { detail: "A positive integer organization_id is required" },
      { status: 400 },
    );
  }

  try {
    const token = await getAccessToken();
    const res = await fetch(`${API_URL}/api/v1/assistance/requests`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ description, organization_id }),
      cache: "no-store",
    });

    const data = await res.json().catch(() => null);

    if (res.status === 401 && !token) {
      return NextResponse.json(
        {
          ...(data ?? {}),
          detail: "Sign in to submit a request.",
        },
        { status: 401 },
      );
    }

    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { detail: "API service unreachable. Is the API running on port 8000?" },
      { status: 503 },
    );
  }
}