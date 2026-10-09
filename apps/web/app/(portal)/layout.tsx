import Link from "next/link";
import { redirect } from "next/navigation";
import SignOutButton from "@/components/SignOutButton";
import { getSession } from "@/lib/session";

const ROLE_LABELS: Record<string, string> = {
  community_member: "Community member",
  donor: "Donor",
  faith_leader: "Faith leader",
  admin: "Administrator",
};

export default async function PortalLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const session = await getSession();
  if (!session) {
    redirect("/login");
  }

  return (
    <div className="bg-slate-50">
      <div className="border-b border-amber-200 bg-amber-50">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-6 py-4">
          <p className="text-sm font-semibold text-amber-900">
            FaithBridge Assistance Portal
          </p>
          <nav className="flex flex-wrap items-center gap-2">
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
            <span className="ml-2 rounded-full bg-white px-3 py-1 text-xs font-semibold uppercase tracking-wide text-amber-900">
              {ROLE_LABELS[session.role] ?? session.role ?? "Signed in"}
            </span>
            <SignOutButton />
          </nav>
        </div>
      </div>
      {children}
    </div>
  );
}
