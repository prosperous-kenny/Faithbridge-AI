import { NextResponse } from "next/server";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

/**
 * Optional access token used to reach the authenticated assistance endpoints.
 * The frontend has no sign-in flow yet, so a developer can paste a local-mode
 * JWT here; without it, the API's own 401 is surfaced to the form.
 */
const ACCESS_TOKEN = process.env.FAITHBRIDGE_ACCESS_TOKEN;

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
    const res = await fetch(`${API_URL}/api/v1/assistance/requests`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(ACCESS_TOKEN ? { Authorization: `Bearer ${ACCESS_TOKEN}` } : {}),
      },
      body: JSON.stringify({ description, organization_id }),
      cache: "no-store",
    });

    const data = await res.json().catch(() => null);

    if (res.status === 401 && !ACCESS_TOKEN) {
      return NextResponse.json(
        {
          ...(data ?? {}),
          detail:
            "This request needs a signed-in user, but the frontend has no " +
            "sign-in flow yet. Set FAITHBRIDGE_ACCESS_TOKEN to a local-mode " +
            "JWT so the proxy can authenticate to the API.",
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