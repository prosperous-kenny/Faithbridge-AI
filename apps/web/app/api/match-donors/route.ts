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
 * Proxy for POST /api/v1/ai/match-donors (PRD §21). Validates the inline
 * overrides locally so contract mistakes surface as a readable 400 instead of
 * a DNS error, then forwards to the API which merges them with saved prefs.
 */
export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON body" }, { status: 400 });
  }

  const data = (body as
    | { causes?: unknown; budget?: unknown; location?: unknown }
    | null) ?? {};
  const causes = data.causes ?? undefined;
  const budget = data.budget ?? undefined;
  const location =
    typeof data.location === "string" && data.location.trim() ? data.location : undefined;

  if (causes !== undefined) {
    if (
      !Array.isArray(causes) ||
      causes.some((cause) => typeof cause !== "string" || !KNOWN_CAUSES.includes(cause))
    ) {
      return NextResponse.json(
        { detail: `causes must be a subset of ${KNOWN_CAUSES.join(", ")}` },
        { status: 400 },
      );
    }
  }
  if (budget !== undefined && (typeof budget !== "number" || budget < 0)) {
    return NextResponse.json(
      { detail: "budget must be a non-negative number" },
      { status: 400 },
    );
  }

  const payload: Record<string, unknown> = {};
  if (causes !== undefined) payload.causes = causes;
  if (budget !== undefined) payload.budget = budget;
  if (location !== undefined) payload.location = location;

  try {
    const res = await fetch(`${API_URL}/api/v1/ai/match-donors`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(ACCESS_TOKEN ? { Authorization: `Bearer ${ACCESS_TOKEN}` } : {}),
      },
      body: JSON.stringify(payload),
      cache: "no-store",
    });

    const data = await res.json().catch(() => null);
    if (res.status === 401 && !ACCESS_TOKEN) {
      return NextResponse.json(
        {
          ...(data ?? {}),
          detail:
            "Matching needs a signed-in donor, but the frontend has no " +
            "sign-in flow yet. Set FAITHBRIDGE_ACCESS_TOKEN to a local-mode " +
            "donor JWT so the proxy can authenticate to the API.",
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