import Link from "next/link";
import { getSystemStatus } from "@/lib/api";
import {
  loadCommunityInsights,
  type CommunityInsights,
  type TrendPoint,
} from "@/lib/dashboard";
import ServiceCard from "@/components/ServiceCard";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Dashboard — FaithBridge AI",
};

const STAT_LABELS: Record<string, string> = {
  organizations: "Organizations",
  users: "Users",
  programs: "Programs",
  beneficiaries: "Beneficiaries",
  assistance_requests: "Assistance Requests",
  donations: "Donations",
  placements: "Placements",
  impact_events: "Impact Events",
};

function TrendChart({ trends }: { trends: TrendPoint[] }) {
  const max = Math.max(1, ...trends.map((t) => Math.max(t.submitted, t.distributed_amount)));
  return (
    <div className="space-y-4">
      {trends.map((trend) => (
        <div key={trend.period} className="flex items-center gap-3">
          <span className="w-16 shrink-0 text-sm font-medium text-slate-600">
            {trend.period}
          </span>
          <div className="flex flex-1 items-center gap-1" title="submitted">
            <div
              className="h-6 rounded bg-slate-700"
              style={{ width: `${Math.max(4, (trend.submitted / max) * 100)}%` }}
            />
            <span className="w-12 text-xs text-slate-500">{trend.submitted}</span>
          </div>
          <div className="flex flex-1 items-center gap-1" title="distributed amount">
            <div
              className="h-6 rounded bg-amber-500"
              style={{
                width: `${Math.max(4, (trend.distributed_amount / max) * 100)}%`,
              }}
            />
            <span className="w-12 text-xs text-slate-500">
              ${trend.distributed_amount}
            </span>
          </div>
        </div>
      ))}
      {trends.length === 0 && (
        <p className="text-sm text-slate-500">
          No activity recorded yet — trends appear as requests and donations
          enter the organization.
        </p>
      )}
    </div>
  );
}

function Insights({ insights }: { insights: CommunityInsights }) {
  const { donation_effectiveness: effectiveness } = insights;
  return (
    <div className="space-y-10">
      <section>
        <h2 className="text-xl font-bold text-slate-900">Monthly trends</h2>
        <div className="fb-card mt-4">
          <div className="mb-4 flex gap-6 text-xs font-medium text-slate-500">
            <span className="flex items-center gap-2">
              <span className="inline-block h-3 w-3 rounded bg-slate-700" />
              Requests submitted (bar)
            </span>
            <span className="flex items-center gap-2">
              <span className="inline-block h-3 w-3 rounded bg-amber-500" />
              USD distributed (bar)
            </span>
          </div>
          <TrendChart trends={insights.trends} />
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <div className="fb-card">
          <h2 className="text-lg font-semibold text-slate-900">
            High-need categories
          </h2>
          {insights.high_need_categories.length === 0 ? (
            <p className="mt-3 text-sm text-slate-500">
              No open requests to rank yet.
            </p>
          ) : (
            <table className="mt-4 w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-500">
                  <th className="py-2">Category</th>
                  <th className="py-2">Open</th>
                  <th className="py-2">Fulfilled</th>
                  <th className="py-2 text-right">Avg urgency</th>
                </tr>
              </thead>
              <tbody>
                {insights.high_need_categories.map((c) => (
                  <tr key={c.category} className="border-b border-slate-100 capitalize">
                    <td className="py-2 font-medium text-slate-800">{c.category}</td>
                    <td className="py-2">{c.open}</td>
                    <td className="py-2">{c.fulfilled}</td>
                    <td className="py-2 text-right">{c.avg_urgency}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="fb-card">
          <h2 className="text-lg font-semibold text-slate-900">
            Donation effectiveness
          </h2>
          <dl className="mt-4 grid grid-cols-2 gap-4">
            <div>
              <dt className="text-xs uppercase text-slate-500">Pledged</dt>
              <dd className="mt-1 text-2xl font-bold text-slate-900">
                ${effectiveness.pledged_amount.toLocaleString()}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase text-slate-500">Paid</dt>
              <dd className="mt-1 text-2xl font-bold text-slate-900">
                ${effectiveness.paid_amount.toLocaleString()}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase text-slate-500">Allocated</dt>
              <dd className="mt-1 text-2xl font-bold text-slate-900">
                ${effectiveness.allocated_amount.toLocaleString()}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase text-slate-500">Distributed</dt>
              <dd className="mt-1 text-2xl font-bold text-emerald-700">
                ${effectiveness.distributed_amount.toLocaleString()}
              </dd>
            </div>
          </dl>
          <p className="mt-4 text-xs text-slate-500">
            Per program:{" "}
            {effectiveness.per_program.length === 0
              ? "no donations tied to a program yet"
              : effectiveness.per_program
                  .map((p) => `${p.name}: $${p.distributed_amount.toLocaleString()}`)
                  .join(" · ")}
          </p>
        </div>
      </section>
    </div>
  );
}

export default async function PortalDashboardPage() {
  const [{ stats, services }, insightsLoad] = await Promise.all([
    getSystemStatus(),
    loadCommunityInsights(),
  ]);

  return (
    <div className="mx-auto max-w-6xl px-6 py-16">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Dashboard</h1>
          <p className="mt-2 text-slate-600">
            Real aggregates for your organization — trends, demand, and where
            the money went. No individual identity is shown (PRD §22).
          </p>
        </div>
        <div className="flex gap-3">
          <Link href="/impact-report" className="fb-btn-secondary">
            Impact report
          </Link>
          <Link href="/request-assistance" className="fb-btn-primary">
            New Request
          </Link>
        </div>
      </div>

      <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {stats &&
          Object.entries(STAT_LABELS).map(([key, label]) => (
            <div key={key} className="fb-card">
              <p className="text-sm text-slate-500">{label}</p>
              <p className="mt-2 text-3xl font-bold text-slate-900">
                {stats[key as keyof typeof stats]}
              </p>
            </div>
          ))}
      </div>

      {!insightsLoad.ok ? (
        <div
          className={`fb-card mt-10 ${
            insightsLoad.status === 401
              ? "border-amber-200 bg-amber-50"
              : "border-slate-300 bg-slate-100"
          }`}
        >
          <p className="font-semibold text-slate-900">
            {insightsLoad.status === 401
              ? "Insights require a faith-leader or admin account"
              : "Insights unavailable"}
          </p>
          <p className="mt-1 text-sm text-slate-600">{insightsLoad.detail}</p>
        </div>
      ) : (
        <div className="mt-10">
          <Insights insights={insightsLoad.insights} />
        </div>
      )}

      <h2 className="mt-14 text-xl font-bold text-slate-900">Service health</h2>
      <div className="mt-6 grid gap-6 md:grid-cols-2">
        {services.map((service) => (
          <ServiceCard key={service.name} service={service} />
        ))}
      </div>
    </div>
  );
}