import { NextResponse } from "next/server";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON body" }, { status: 400 });
  }

  const description = (body as { description?: string } | null)?.description;
  if (typeof description !== "string" || description.trim().length < 10) {
    return NextResponse.json(
      { detail: "Description must be at least 10 characters" },
      { status: 400 },
    );
  }

  try {
    const res = await fetch(`${API_URL}/api/v1/assistance/requests`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description }),
      cache: "no-store",
    });

    const data = await res.json().catch(() => null);
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { detail: "API service unreachable. Is the API running on port 8000?" },
      { status: 503 },
    );
  }
}
