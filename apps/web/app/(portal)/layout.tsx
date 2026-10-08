import Link from "next/link";

export default function PortalLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="bg-slate-50">
      <div className="border-b border-amber-200 bg-amber-50">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-6 py-4">
          <p className="text-sm font-semibold text-amber-900">
            FaithBridge Assistance Portal
          </p>
          <nav className="flex gap-2">
            <Link
              href="/dashboard"
              className="rounded-lg px-3 py-1.5 text-sm font-medium text-amber-900 transition hover:bg-amber-100"
            >
              Dashboard
            </Link>
            <Link
              href="/impact-report"
              className="rounded-lg px-3 py-1.5 text-sm font-medium text-amber-900 transition hover:bg-amber-100"
            >
              Impact report
            </Link>
            <Link
              href="/request-assistance"
              className="rounded-lg px-3 py-1.5 text-sm font-medium text-amber-900 transition hover:bg-amber-100"
            >
              Submit a need
            </Link>
            <Link
              href="/requests"
              className="rounded-lg px-3 py-1.5 text-sm font-medium text-amber-900 transition hover:bg-amber-100"
            >
              Leader queue
            </Link>
            <Link
              href="/match"
              className="rounded-lg px-3 py-1.5 text-sm font-medium text-amber-900 transition hover:bg-amber-100"
            >
              Donor match
            </Link>
          </nav>
        </div>
      </div>
      {children}
    </div>
  );
}