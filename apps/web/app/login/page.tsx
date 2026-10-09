import Link from "next/link";
import { redirect } from "next/navigation";
import LoginForm from "@/components/LoginForm";
import { getSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Sign in — FaithBridge AI",
};

/**
 * Only allow a same-site path as the post-login destination, so a crafted
 * ``?next=`` cannot bounce the user to another origin after a real sign-in.
 */
function safeNext(value: string | undefined): string {
  if (value && value.startsWith("/") && !value.startsWith("//")) {
    return value;
  }
  return "/dashboard";
}

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const { next } = await searchParams;
  const target = safeNext(next);

  if (await getSession()) {
    redirect(target);
  }

  return (
    <div className="mx-auto max-w-md px-6 py-16">
      <h1 className="text-3xl font-bold text-slate-900">Sign in</h1>
      <p className="mt-2 text-slate-600">
        Sign in to triage assistance requests, review impact, or match donor
        programs. Accounts are created by your organization.
      </p>

      <div className="mt-8">
        <LoginForm next={target} />
      </div>

      <p className="mt-6 text-sm text-slate-500">
        <Link href="/" className="font-medium text-amber-700 hover:underline">
          Back to home
        </Link>
      </p>
    </div>
  );
}
