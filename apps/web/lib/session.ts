import { cookies } from "next/headers";

/**
 * Name of the httpOnly cookie that carries the API access token. The token is
 * set by /api/auth/login after the API accepts the credentials, and is only
 * ever read on the server (Server Components and Route Handlers).
 */
export const SESSION_COOKIE = "fb_session";

export type Session = {
  token: string;
  userId: number | null;
  role: string;
};

/**
 * Decode a JWT payload without verifying its signature.
 *
 * This is a convenience for server-side rendering only: the API verifies the
 * token on every request and is the sole authority on what a caller may do.
 * Nothing security-sensitive is decided from these claims — they are used to
 * label the UI and to decide which controls are worth showing.
 */
function decodePayload(token: string): Record<string, unknown> | null {
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(
      base64.length + ((4 - (base64.length % 4)) % 4),
      "=",
    );
    const parsed: unknown = JSON.parse(
      Buffer.from(padded, "base64").toString("utf8"),
    );
    return typeof parsed === "object" && parsed !== null
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

/** The raw access token from the session cookie, or undefined when signed out. */
export async function getAccessToken(): Promise<string | undefined> {
  const cookieStore = await cookies();
  return cookieStore.get(SESSION_COOKIE)?.value;
}

/**
 * The current session, or null when there is no valid-looking access token.
 * Expiry is checked locally so a stale cookie is treated as signed out before
 * it produces a round of 401s.
 */
export async function getSession(): Promise<Session | null> {
  const token = await getAccessToken();
  if (!token) return null;

  const claims = decodePayload(token);
  if (!claims || claims.type !== "access") return null;

  const exp = claims.exp;
  if (typeof exp === "number" && exp * 1000 <= Date.now()) return null;

  const sub = claims.sub;
  const userId = typeof sub === "string" ? Number(sub) : NaN;

  return {
    token,
    userId: Number.isFinite(userId) ? userId : null,
    role: typeof claims.role === "string" ? claims.role : "",
  };
}
