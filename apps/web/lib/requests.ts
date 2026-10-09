import type { AssistanceRequestDetail } from "./assistance";
import { getAccessToken } from "./session";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

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
  const token = await getAccessToken();
  if (!token) {
    return {
      ok: false,
      status: 401,
      detail: "Sign in with a faith-leader or admin account to view the queue.",
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
        headers: { Authorization: `Bearer ${token}` },
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