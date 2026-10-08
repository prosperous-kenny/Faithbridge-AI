import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "FaithBridge AI",
  description:
    "Transforming faith-based giving into measurable community impact.",
};

const NAV = [
  { href: "/", label: "Home" },
  { href: "/dashboard", label: "Dashboard" },
  { href: "/request-assistance", label: "Submit Request" },
  { href: "/requests", label: "Leader Queue" },
  { href: "/status", label: "System Status" },
];

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" data-scroll-behavior="smooth">
      <body className="flex min-h-screen flex-col font-sans">
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-4">
            <Link href="/" className="flex items-center gap-2">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-600 text-lg font-bold text-white">
                F
              </span>
              <span className="text-lg font-bold text-slate-900">
                FaithBridge <span className="text-amber-600">AI</span>
              </span>
            </Link>
            <nav className="flex flex-wrap gap-1">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="rounded-lg px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>

        <main className="flex-1">{children}</main>

        <footer className="border-t border-slate-200 bg-slate-50">
          <div className="mx-auto max-w-6xl px-6 py-8">
            <p className="text-sm text-slate-500">
              FaithBridge AI — Phase 0 development build. Running locally
              against PostgreSQL 16.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
