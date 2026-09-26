import { getSystemStatus } from "@/lib/api";
import ServiceCard from "@/components/ServiceCard";

export const dynamic = "force-dynamic";

export default async function StatusPage() {
  const { services, stats, checkedAt } = await getSystemStatus();
  const allHealthy = services.every((s) => s.ok) && stats !== null;

  return (
    <div className="mx-auto max-w-4xl px-6 py-16">
      <h1 className="text-3xl font-bold text-slate-900">System Status</h1>
      <p className="mt-2 text-slate-600">
        Live health checks against the local development stack.
      </p>

      <div
        className={`mt-6 rounded-lg border px-5 py-4 ${
          allHealthy
            ? "border-green-200 bg-green-50"
            : "border-amber-200 bg-amber-50"
        }`}
      >
        <p className="font-semibold text-slate-900">
          {allHealthy
            ? "All services operational"
            : "One or more services are unavailable"}
        </p>
        <p className="mt-1 text-sm text-slate-600">
          Checked at{" "}
          {new Date(checkedAt).toLocaleTimeString("en-US", {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          })}
        </p>
      </div>

      <div className="mt-8 grid gap-6 md:grid-cols-2">
        {services.map((service) => (
          <ServiceCard key={service.name} service={service} />
        ))}
      </div>

      <div className="fb-card mt-8">
        <h2 className="font-semibold text-slate-900">Database connectivity</h2>
        {stats ? (
          <p className="mt-2 text-slate-600">
            The API successfully queried PostgreSQL and returned live row counts
            across all tables.
          </p>
        ) : (
          <p className="mt-2 text-slate-600">
            Row counts unavailable — the API could not reach the database.
          </p>
        )}
      </div>
    </div>
  );
}
