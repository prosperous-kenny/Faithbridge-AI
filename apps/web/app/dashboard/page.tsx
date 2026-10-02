import Link from "next/link";
import { getSystemStatus, IS_BACKEND_CONFIGURED } from "@/lib/api";
import ServiceCard from "@/components/ServiceCard";

export const dynamic = "force-dynamic";

const STAT_LABELS: Record<string, string> = {
  organizations: "Organizations",
  users: "Users",
  programs: "Programs",
  beneficiaries: "Beneficiaries",
  assistance_requests: "Assistance Requests",
  donations: "Donations",
  placements: "Placements",
};

export default async function DashboardPage() {
  const { stats, services } = await getSystemStatus();

  return (
    <div className="mx-auto max-w-6xl px-6 py-16">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Dashboard</h1>
          <p className="mt-2 text-slate-600">
            Live platform data read from PostgreSQL through the API.
          </p>
        </div>
        <Link href="/request" className="fb-btn-primary">
          New Request
        </Link>
      </div>

      {stats ? (
        <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {Object.entries(STAT_LABELS).map(([key, label]) => (
            <div key={key} className="fb-card">
              <p className="text-sm text-slate-500">{label}</p>
              <p className="mt-2 text-3xl font-bold text-slate-900">
                {stats[key as keyof typeof stats]}
              </p>
            </div>
          ))}
        </div>
      ) : (
        <div className="fb-card mt-10 border-amber-200 bg-amber-50">
          <p className="font-semibold text-slate-900">
            {IS_BACKEND_CONFIGURED
              ? "Dashboard data unavailable"
              : "No API connected on this deployment"}
          </p>
          <p className="mt-1 text-sm text-slate-600">
            {IS_BACKEND_CONFIGURED
              ? "The API did not return statistics. Confirm the API and PostgreSQL are running, then reload."
              : "This deployment hosts the frontend only. FaithBridge AI's FastAPI services and PostgreSQL database run separately, so live platform data is unavailable here. Counts appear once an API_URL is configured."}
          </p>
        </div>
      )}

      <h2 className="mt-14 text-xl font-bold text-slate-900">
        Service health
      </h2>
      <div className="mt-6 grid gap-6 md:grid-cols-2">
        {services.map((service) => (
          <ServiceCard key={service.name} service={service} />
        ))}
      </div>
    </div>
  );
}
