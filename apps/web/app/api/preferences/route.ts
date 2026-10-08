import { NextResponse } from "next/server";

const API_URL = process.env.API_URL ?? "http://localhost:8000";
const ACCESS_TOKEN = process.env.FAITHBRIDGE_ACCESS_TOKEN;

const KNOWN_CAUSES = [
  "food",
  "housing",
  "medical",
  "education",
  "employment",
  "emergency",
];

/**
 * GET/PUT for a donor's saved matching preferences (PRD Use Case 2). The PUT
 * is a full replacement of the three fields, matching the API's upsert
 * semantics; the caller only needs an authenticated donor token.
 */
export async function GET() {
  if (!ACCESS_TOKEN) {
    return NextResponse.json(
      {
        detail:
          "Preferences need a signed-in donor, but the frontend has no " +
          "sign-in flow yet. Set FAITHBRIDGE_ACCESS_TOKEN to a local-mode " +
          "donor JWT so the proxy can authenticate to the API.",
      },
      { status: 401 },
    );
  }
  try {
    const res = await fetch(`${API_URL}/api/v1/donors/preferences/`, {
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

export async function PUT(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON body" }, { status: 400 });
  }

  const data = (body as
    | { causes?: unknown; budget?: unknown; location?: unknown }
    | null) ?? {};
  if (
    !Array.isArray(data.causes) ||
    data.causes.some(
      (cause) => typeof cause !== "string" || !KNOWN_CAUSES.includes(cause),
    )
  ) {
    return NextResponse.json(
      { detail: `causes must be a subset of ${KNOWN_CAUSES.join(", ")}` },
      { status: 400 },
    );
  }
  if (data.budget !== undefined && data.budget !== null) {
    if (typeof data.budget !== "number" || data.budget < 0) {
      return NextResponse.json(
        { detail: "budget must be a non-negative number" },
        { status: 400 },
      );
    }
  }
  const location =
    typeof data.location === "string" && data.location.trim() ? data.location : undefined;
  const budget = data.budget === undefined ? null : data.budget;

  if (!ACCESS_TOKEN) {
    return NextResponse.json(
      {
        detail:
          "Preferences need a signed-in donor, but the frontend has no " +
          "sign-in flow yet. Set FAITHBRIDGE_ACCESS_TOKEN to a local-mode " +
          "donor JWT so the proxy can authenticate to the API.",
      },
      { status: 401 },
    );
  }

  try {
    const res = await fetch(`${API_URL}/api/v1/donors/preferences/`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${ACCESS_TOKEN}`,
      },
      body: JSON.stringify({
        causes: data.causes,
        budget: typeof budget === "number" ? budget : null,
        location: location ?? null,
      }),
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