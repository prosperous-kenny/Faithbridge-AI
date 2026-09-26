import type { ServiceStatus } from "@/lib/types";

export default function ServiceCard({ service }: { service: ServiceStatus }) {
  return (
    <div className="fb-card">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-slate-900">{service.name}</h2>
        <span
          className={`rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wide ${
            service.ok
              ? "bg-green-100 text-green-800"
              : "bg-red-100 text-red-800"
          }`}
        >
          {service.ok ? "Online" : "Offline"}
        </span>
      </div>
      <p className="mt-2 text-sm text-slate-600">{service.detail}</p>
      <p className="mt-2 break-all font-mono text-xs text-slate-400">
        {service.url}
      </p>
    </div>
  );
}
