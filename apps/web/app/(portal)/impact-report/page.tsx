import { EXPORT_FORMATS, exportUrl, loadImpactReport } from "@/lib/dashboard";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Impact Report — FaithBridge AI",
};

const DIMENSION_LABELS: Record<string, string> = {
  families: "Families supported",
  education: "Education",
  employment: "Employment",
  food_security: "Food security",
  healthcare: "Healthcare",
};

function ExportLink({ format }: { format: (typeof EXPORT_FORMATS)[number] }) {
  return (
    <a
      href={exportUrl(format)}
      className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
    >
      Export {format.toUpperCase()}
    </a>
  );
}

export default async function ImpactReportPage() {
  const report = await loadImpactReport();

  return (
    <div className="mx-auto max-w-4xl px-6 py-16">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Impact Report</h1>
          <p className="mt-2 text-slate-600">
            The Community Impact Score (100 = all targets met) with the
            dimension breakdown behind it, plus the monthly outcome totals.
          </p>
        </div>
        {report.ok && (
          <div className="flex gap-2">
            <ExportLink format="csv" />
            <ExportLink format="pdf" />
          </div>
        )}
      </div>

      {!report.ok ? (
        <div
          className={`fb-card mt-10 ${
            report.status === 401
              ? "border-amber-200 bg-amber-50"
              : "border-slate-300 bg-slate-100"
          }`}
        >
          <p className="font-semibold text-slate-900">
            {report.status === 401
              ? "Impact report requires a faith-leader or admin account"
              : "Impact report unavailable"}
          </p>
          <p className="mt-1 text-sm text-slate-600">{report.detail}</p>
        </div>
      ) : (
        <>
          <div className="fb-card mt-10 flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-sm uppercase tracking-wide text-slate-500">
                Community Impact Score
              </p>
              <p className="mt-1 text-5xl font-bold text-slate-900">
                {report.report.score}
                <span className="text-xl font-normal text-slate-500">/100</span>
              </p>
            </div>
            <p className="max-w-xs text-sm text-slate-600">
              {report.report.period_start && report.report.period_end ? (
                <>
                  Totals measured from{" "}
                  {report.report.period_start.slice(0, 10)} to{" "}
                  {report.report.period_end.slice(0, 10)}.
                </>
              ) : (
                "Measure outcomes by recording impact events; totals appear here once recorded."
              )}
            </p>
          </div>

          <h2 className="mt-12 text-xl font-bold text-slate-900">
            Component breakdown
          </h2>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            {Object.entries(report.report.components).map(
              ([dimension, component]) => (
                <div key={dimension} className="fb-card">
                  <div className="flex items-center justify-between">
                    <p className="font-medium capitalize text-slate-800">
                      {DIMENSION_LABELS[dimension] ?? dimension}
                    </p>
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">
                      weight {(component.weight * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="mt-3 flex items-end justify-between">
                    <span className="text-3xl font-bold text-slate-900">
                      {component.value}
                    </span>
                    <span className="text-sm text-slate-500">
                      target {component.target}
                    </span>
                  </div>
                  <div className="mt-3 h-2 rounded-full bg-slate-100">
                    <div
                      className="h-2 rounded-full bg-amber-500"
                      style={{
                        width: `${Math.min(100, (component.value / component.target) * 100)}%`,
                      }}
                    />
                  </div>
                </div>
              ),
            )}
          </div>

          <h2 className="mt-12 text-xl font-bold text-slate-900">
            Monthly totals
          </h2>
          <div className="fb-card mt-4">
            {report.report.months.length === 0 ? (
              <p className="text-sm text-slate-500">
                No monthly totals yet — run the rollup after recording impact
                events.
              </p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-500">
                    <th className="py-2">Period</th>
                    <th className="py-2">Metric</th>
                    <th className="py-2 text-right">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {report.report.months.map((m) => (
                    <tr
                      key={`${m.period_start}-${m.metric}`}
                      className="border-b border-slate-100"
                    >
                      <td className="py-2 text-slate-600">
                        {m.period_start.slice(0, 10)} → {m.period_end.slice(0, 10)}
                      </td>
                      <td className="py-2 font-medium text-slate-800">{m.metric}</td>
                      <td className="py-2 text-right">{m.total}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
}