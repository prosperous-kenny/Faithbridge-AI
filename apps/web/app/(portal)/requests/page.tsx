import Link from "next/link";
import { loadQueue } from "@/lib/requests";
import type { AssistanceRequestDetail } from "@/lib/assistance";
import {
  PRIORITY_STYLES,
  STATUS_STYLES,
  STATUSES,
} from "@/lib/assistance";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Leader Queue — FaithBridge AI",
};

function Timestamp({ created_at }: { created_at: string }) {
  return (
    <time className="text-sm text-slate-500" dateTime={created_at}>
      {new Date(created_at).toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })}
    </time>
  );
}

function QueueCard({ request }: { request: AssistanceRequestDetail }) {
  const person = request.beneficiary.person;
  return (
    <li className="fb-card">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span
              className={`rounded-full px-3 py-1 text-xs font-bold uppercase ${
                PRIORITY_STYLES[request.priority] ?? PRIORITY_STYLES.low
              }`}
            >
              {request.priority}
            </span>
            <span
              className={`rounded-full px-3 py-1 text-xs font-bold uppercase ${
                STATUS_STYLES[request.status] ?? STATUS_STYLES.submitted
              }`}
            >
              {request.status}
            </span>
          </div>
          <p className="mt-2 capitalize text-sm font-medium text-slate-500">
            {request.category}
            {" · "}case #{request.id}
          </p>
        </div>
        <div className="text-right">
          <p className="text-2xl font-bold text-slate-900">
            {request.urgency_score}
            <span className="text-sm font-normal text-slate-500">/100</span>
          </p>
          <Timestamp created_at={request.created_at} />
        </div>
      </div>

      <p className="mt-4 text-slate-800">{request.description}</p>

      <div className="mt-4 border-t border-slate-100 pt-3 text-sm text-slate-600">
        {request.beneficiary.consented && person ? (
          <p>
            <span className="font-semibold">{person.full_name}</span>
            {" · "}
            {person.email}
            {" · household of "}
            {request.beneficiary.household_size}
          </p>
        ) : (
          <p>
            Anonymous beneficiary
            {" · household of "}
            {request.beneficiary.household_size}
            {request.beneficiary.consented
              ? ""
              : " — PII hidden until consent (PRD §22)"}
          </p>
        )}
      </div>
    </li>
  );
}

export default async function RequestsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; sort?: string }>;
}) {
  const { status, sort: sortRaw } = await searchParams;
  const sort =
    sortRaw === "newest" || sortRaw === "priority" ? sortRaw : "priority";
  const filtered = STATUSES.includes(status as (typeof STATUSES)[number])
    ? (status as string)
    : undefined;
  const load = await loadQueue({ status: filtered, sort });

  return (
    <div className="mx-auto max-w-4xl px-6 py-16">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Leader Queue</h1>
          <p className="mt-2 text-slate-600">
            Open assistance requests, sorted by urgency for triage. Beneficiary
            identity is shown only where consent exists.
          </p>
        </div>
        <Link href="/request-assistance" className="fb-btn-primary">
          New Request
        </Link>
      </div>

      <div className="mt-8 flex flex-wrap gap-2">
        <Link
          href="/requests"
          className={`rounded-full px-3 py-1 text-sm font-medium ${
            filtered === undefined
              ? "bg-slate-900 text-white"
              : "bg-white text-slate-600 hover:bg-slate-100"
          }`}
        >
          All
        </Link>
        {STATUSES.map((s) => (
          <Link
            key={s}
            href={`/requests?status=${s}`}
            className={`rounded-full px-3 py-1 text-sm font-medium capitalize ${
              filtered === s
                ? "bg-slate-900 text-white"
                : "bg-white text-slate-600 hover:bg-slate-100"
            }`}
          >
            {s}
          </Link>
        ))}
      </div>

      {!load.ok ? (
        <div className="fb-card mt-8 border-slate-300 bg-slate-100">
          <p className="font-semibold text-slate-900">
            {load.status === 401
              ? "Queue requires sign-in"
              : "Queue data unavailable"}
          </p>
          <p className="mt-1 text-sm text-slate-700">{load.detail}</p>
        </div>
      ) : load.requests.length === 0 ? (
        <div className="fb-card mt-8 border-slate-200 bg-white">
          <p className="font-semibold text-slate-900">No requests</p>
          <p className="mt-1 text-sm text-slate-600">
            There are no assistance requests{" "}
            {filtered ? `with status “${filtered}”` : "in the queue"} right
            now. New submissions appear here once triaged by faith leaders.
          </p>
        </div>
      ) : (
        <ul className="mt-8 grid gap-6">
          {load.requests.map((request) => (
            <QueueCard key={request.id} request={request} />
          ))}
        </ul>
      )}
    </div>
  );
}