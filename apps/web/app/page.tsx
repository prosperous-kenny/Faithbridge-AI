import Link from "next/link";

const PILLARS = [
  {
    title: "Intelligent Triage",
    body: "Assistance requests are classified and scored for urgency the moment they arrive, so leaders act on the most critical needs first.",
    icon: "◎",
  },
  {
    title: "Donor Matching",
    body: "Connect giving to verified programs with transparent allocation, so every contribution reaches a real household.",
    icon: "◈",
  },
  {
    title: "Impact Reporting",
    body: "Track outcomes against the donation ledger so faith leaders can report real community impact, not just dollars distributed.",
    icon: "▲",
  },
];

const ROLES = [
  {
    role: "Faith Leaders",
    body: "Triage requests, coordinate volunteers, and see what your community needs next.",
  },
  {
    role: "Donors",
    body: "Direct giving to the programs closest to the need, with full allocation visibility.",
  },
  {
    role: "Administrators",
    body: "Manage organizations, programs, and reporting across the whole network.",
  },
];

export default function Home() {
  return (
    <div>
      <section className="bg-gradient-to-b from-amber-50 to-white">
        <div className="mx-auto max-w-6xl px-6 py-20 text-center">
          <span className="inline-block rounded-full bg-amber-100 px-4 py-1.5 text-sm font-semibold text-amber-800">
            Phase 0 — Development Build
          </span>
          <h1 className="mx-auto mt-6 max-w-3xl text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl">
            Turning faith-based giving into{" "}
            <span className="text-amber-600">measurable impact</span>
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-slate-600">
            FaithBridge AI helps faith-based organizations identify community
            needs, prioritize assistance, and prove the impact of every dollar.
          </p>
          <div className="mt-10 flex flex-wrap justify-center gap-4">
            <Link href="/dashboard" className="fb-btn-primary">
              Open Dashboard
            </Link>
            <Link href="/request" className="fb-btn-secondary">
              Submit an Assistance Request
            </Link>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 py-20">
        <h2 className="text-center text-3xl font-bold text-slate-900">
          How it works
        </h2>
        <div className="mt-12 grid gap-8 md:grid-cols-3">
          {PILLARS.map((pillar) => (
            <div key={pillar.title} className="fb-card">
              <span className="text-2xl text-amber-600">{pillar.icon}</span>
              <h3 className="mt-4 text-lg font-semibold text-slate-900">
                {pillar.title}
              </h3>
              <p className="mt-2 text-slate-600">{pillar.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="bg-slate-50 py-20">
        <div className="mx-auto max-w-6xl px-6">
          <h2 className="text-center text-3xl font-bold text-slate-900">
            Built for three roles
          </h2>
          <div className="mt-12 grid gap-8 md:grid-cols-3">
            {ROLES.map((item) => (
              <div
                key={item.role}
                className="rounded-xl border border-slate-200 bg-white p-6"
              >
                <h3 className="font-semibold text-slate-900">{item.role}</h3>
                <p className="mt-2 text-slate-600">{item.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-3xl px-6 py-20 text-center">
        <h2 className="text-3xl font-bold text-slate-900">
          See the platform working
        </h2>
        <p className="mt-4 text-slate-600">
          The development build is live on this machine. Check the system
          status page to confirm the API, AI service, and PostgreSQL are all
          responding.
        </p>
        <Link href="/status" className="fb-btn-primary mt-8">
          Check System Status
        </Link>
      </section>
    </div>
  );
}
