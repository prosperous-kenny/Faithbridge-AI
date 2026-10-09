import type { DashboardStats, ReadinessStatus, SystemStatus } from "./types";

const API_URL = process.env.API_URL ?? "http://localhost:8000";
const AI_URL = process.env.AI_SERVICE_URL ?? "http://localhost:8200";

const TIMEOUT_MS = 8000;

/**
 * True when no API host is configured, which is the case on a frontend-only
 * deployment such as Netlify. Lets the UI explain the gap instead of
 * implying a real outage.
 */
export const IS_BACKEND_CONFIGURED = Boolean(process.env.API_URL);

async function probe(
  name: string,
  url: string,
  parse: (json: unknown) => string,
): Promise<SystemStatus["services"][number]> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(url, { cache: "no-store", signal: controller.signal });
    if (!res.ok) {
      return { name, url, ok: false, detail: `HTTP ${res.status}` };
    }
    return { name, url, ok: true, detail: parse(await res.json()) };
  } catch (err) {
    const reason = err instanceof Error ? err.message : "unreachable";
    return { name, url, ok: false, detail: reason };
  } finally {
    clearTimeout(timer);
  }
}

export async function getSystemStatus(): Promise<SystemStatus> {
  // Frontend-only deployment (no API_URL): probing the localhost fallbacks
  // would take 4s and then render a misleading "Offline" against services
  // that were never reachable from here. Report no services instead and let
  // each page explain the gap.
  if (!IS_BACKEND_CONFIGURED) {
    return { services: [], stats: null, checkedAt: new Date().toISOString() };
  }

  const token = process.env.FAITHBRIDGE_ACCESS_TOKEN;
  const [api, ai, stats] = await Promise.all([
    probe("API", `${API_URL}/health/ready`, (json) => {
      const body = json as ReadinessStatus;
      return `database ${body.database}`;
    }),
    probe("AI service", `${AI_URL}/health`, () => "reachable"),
    fetch(`${API_URL}/api/v1/dashboard/stats`, {
      cache: "no-store",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((res) => (res.ok ? (res.json() as Promise<DashboardStats>) : null))
      .catch(() => null),
  ]);

  return {
    services: [api, ai],
    stats,
    checkedAt: new Date().toISOString(),
  };
}
