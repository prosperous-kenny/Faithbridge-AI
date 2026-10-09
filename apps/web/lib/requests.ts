import type { AssistanceRequestDetail } from "./assistance";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

/**
 * Access token for the authenticated queue endpoint. The frontend has no
 * sign-in, so a developer pastes a local-mode faith-leader/admin JWT here.
 */
export const ACCESS_TOKEN = process.env.FAITHBRIDGE_ACCESS_TOKEN;

/** True when a token is configured so the UI can explain a 401, not fake it. */
export const IS_AUTH_CONFIGURED = Boolean(ACCESS_TOKEN);

const TIMEOUT_MS = 8000;

export type QueueQuery = {
  status?: string;
  sort?: "priority" | "newest";
};

export type QueueLoad =
  | { ok: true; requests: AssistanceRequestDetail[] }
  | { ok: false; detail: string; status: number };

export async function loadQueue({
  status,
  sort = "priority",
}: QueueQuery = {}): Promise<QueueLoad> {
  if (!ACCESS_TOKEN) {
    return {
      ok: false,
      status: 401,
      detail:
        "Queue data needs a faith-leader or admin account, but the frontend " +
        "has no sign-in flow yet. Set FAITHBRIDGE_ACCESS_TOKEN to a " +
        "local-mode JWT to load it.",
    };
  }

  const params = new URLSearchParams({ sort, limit: "200" });
  if (status) {
    params.set("status", status);
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(
      `${API_URL}/api/v1/assistance/requests?${params.toString()}`,
      {
        headers: { Authorization: `Bearer ${ACCESS_TOKEN}` },
        cache: "no-store",
        signal: controller.signal,
      },
    );
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      const detail =
        typeof body?.detail === "string" ? body.detail : `HTTP ${res.status}`;
      return { ok: false, detail, status: res.status };
    }
    return {
      ok: true,
      requests: (await res.json()) as AssistanceRequestDetail[],
    };
  } catch (err) {
    const reason = err instanceof Error ? err.message : "unreachable";
    return { ok: false, detail: reason, status: 0 };
  } finally {
    clearTimeout(timer);
  }
}