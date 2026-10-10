export interface Organization {
  id: number;
  name: string;
  org_type: string;
  created_at: string;
  updated_at: string;
}

const BASE =
  process.env.API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";

export async function loadOrganizations({
  limit,
  offset,
  token,
}: {
  limit?: number;
  offset?: number;
  token: string;
}): Promise<Organization[]> {
  const url = new URL(`${BASE}/api/v1/organizations/`);
  if (limit !== undefined) url.searchParams.set("limit", String(limit));
  if (offset !== undefined) url.searchParams.set("offset", String(offset));

  const res = await fetch(url.toString(), {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    const msg = detail?.detail ?? detail?.error ?? res.statusText;
    throw new Error(`Failed to load organizations (${res.status}): ${msg}`);
  }
  const data = await res.json().catch(() => null);
  return Array.isArray(data) ? (data as Organization[]) : [];
}
