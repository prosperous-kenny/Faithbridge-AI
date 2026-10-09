import type {
  DashboardStats,
  ReadinessStatus,
  SystemStatus,
} from "./types";

const API_URL = process.env.API_URL ?? "http://localhost:8000";
const AI_URL = process.env.AI_SERVICE_URL ?? "http://localhost:8200";

export const ACCESS_TOKEN = process.env.FAITHBRIDGE_ACCESS_TOKEN;
export const IS_AUTH_CONFIGURED = Boolean(ACCESS_TOKEN);

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
  // Same guard as lib/api.ts: a frontend-only deployment has nothing to
  // probe, and a localhost timeout would only render a false outage.
  if (!IS_BACKEND_CONFIGURED) {
    return { services: [], stats: null, checkedAt: new Date().toISOString() };
  }

  const [api, ai, stats] = await Promise.all([
    probe("API", `${API_URL}/health/ready`, (json) => {
      const body = json as ReadinessStatus;
      return `database ${body.database}`;
    }),
    probe("AI service", `${AI_URL}/health`, () => "reachable"),
    fetch(
      `${API_URL}/api/v1/dashboard/stats`,
      ACCESS_TOKEN
        ? { cache: "no-store", headers: { Authorization: `Bearer ${ACCESS_TOKEN}` } }
        : { cache: "no-store" },
    )
      .then((res) => (res.ok ? (res.json() as Promise<DashboardStats>) : null))
      .catch(() => null),
  ]);

  return {
    services: [api, ai],
    stats,
    checkedAt: new Date().toISOString(),
  };
}

// --- Phase 5 aggregate loads (portal dashboard + impact report) -------------

export type TrendPoint = {
  period: string;
  submitted: number;
  fulfilled: number;
  pledged_amount: number;
  paid_amount: number;
  distributed_amount: number;
};

export type HighNeedCategory = {
  category: string;
  open: number;
  fulfilled: number;
  avg_urgency: number;
};

export type ProgramEffectiveness = {
  program_id: number;
  name: string;
  pledged_amount: number;
  distributed_amount: number;
};

export type CommunityInsights = {
  organization_id: number;
  trends: TrendPoint[];
  high_need_categories: HighNeedCategory[];
  donation_effectiveness: {
    pledged_amount: number;
    paid_amount: number;
    allocated_amount: number;
    distributed_amount: number;
    per_program: ProgramEffectiveness[];
  };
};

export type ReportMonth = {
  period_start: string;
  period_end: string;
  metric: string;
  total: number;
};

export type ImpactReport = {
  organization_id: number;
  score: number;
  components: Record<
    string,
    { value: number; weight: number; target: number }
  >;
  months: ReportMonth[];
  period_start: string | null;
  period_end: string | null;
};

export type InsightsLoad =
  | { ok: true; insights: CommunityInsights }
  | { ok: false; detail: string; status: number };

export type ImpactReportLoad =
  | { ok: true; report: ImpactReport }
  | { ok: false; detail: string; status: number };

async function authFetch(path: string): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    return await fetch(`${API_URL}${path}`, {
      headers: { Authorization: `Bearer ${ACCESS_TOKEN ?? ""}` },
      cache: "no-store",
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

type LoadResult<T> =
  | { ok: true; value: T }
  | { ok: false; detail: string; status: number };

async function toLoad<T>(
  res: Response,
  pick: (json: unknown) => T,
): Promise<LoadResult<T>> {
  if (res.status === 401) {
    return {
      ok: false,
      status: 401,
      detail:
        "Insight data needs a faith-leader or admin account, but the frontend " +
        "has no sign-in flow yet. Set FAITHBRIDGE_ACCESS_TOKEN to a " +
        "local-mode JWT to load it.",
    };
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail =
      typeof body?.detail === "string" ? body.detail : `HTTP ${res.status}`;
    return { ok: false, status: res.status, detail };
  }
  return { ok: true, value: pick(await res.json()) };
}

async function load<T>(
  path: string,
  pick: (json: unknown) => T,
): Promise<LoadResult<T>> {
  if (!ACCESS_TOKEN) {
    return { ok: false, status: 401, detail: "Not authenticated" };
  }
  let res: Response;
  try {
    res = await authFetch(path);
  } catch (err) {
    return {
      ok: false,
      status: 0,
      detail: err instanceof Error ? err.message : "unreachable",
    };
  }
  return toLoad(res, pick);
}

export async function loadCommunityInsights(): Promise<InsightsLoad> {
  const out = await load(
    "/api/v1/dashboard/community-insights",
    (json) => json as CommunityInsights,
  );
  return out.ok ? { ok: true, insights: out.value } : out;
}

export async function loadImpactReport(): Promise<ImpactReportLoad> {
  const out = await load(
    "/api/v1/dashboard/impact-report",
    (json) => json as ImpactReport,
  );
  return out.ok ? { ok: true, report: out.value } : out;
}

export const EXPORT_FORMATS = ["csv", "pdf"] as const;

export function exportUrl(format: (typeof EXPORT_FORMATS)[number]): string {
  return `${API_URL}/api/v1/dashboard/impact-report/export?format=${format}`;
}