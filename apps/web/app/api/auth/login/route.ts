import { NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/session";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

/**
 * Sign-in proxy: exchange email/password for an API token, then store that
 * token in an httpOnly cookie. The browser never sees the token, so an XSS
 * payload cannot read it; the API remains the authority that validates it on
 * every subsequent server-side request.
 */
export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON body" }, { status: 400 });
  }

  const data =
    (body as { email?: unknown; password?: unknown } | null) ?? {};
  const email = typeof data.email === "string" ? data.email.trim() : "";
  const password = typeof data.password === "string" ? data.password : "";

  if (!email || !password) {
    return NextResponse.json(
      { detail: "Email and password are required." },
      { status: 400 },
    );
  }

  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      { detail: "API service unreachable. Is the API running?" },
      { status: 503 },
    );
  }

  const payload = (await res.json().catch(() => null)) as
    | { access_token?: unknown; expires_in?: unknown; detail?: unknown }
    | null;

  if (!res.ok) {
    return NextResponse.json(
      payload ?? { detail: "Sign-in failed." },
      { status: res.status },
    );
  }

  const token = payload?.access_token;
  if (typeof token !== "string" || !token) {
    return NextResponse.json(
      { detail: "Sign-in failed: no token returned." },
      { status: 502 },
    );
  }

  const maxAge =
    typeof payload?.expires_in === "number" ? payload.expires_in : 60 * 60 * 24 * 7;

  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge,
  });
  return response;
}
