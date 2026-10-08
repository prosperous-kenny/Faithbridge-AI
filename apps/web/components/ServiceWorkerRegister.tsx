"use client";

import { useEffect } from "react";

/**
 * Registers the PWA service worker (Phase 7) after mount.
 *
 * Production only: a caching service worker during `next dev` hides edits
 * behind a stale shell. Registration failure must never break the app —
 * offline support is an enhancement, the site works without it.
 */
export default function ServiceWorkerRegister() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") return;
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker
      .register("/sw.js")
      .catch(() => undefined);
  }, []);

  return null;
}
