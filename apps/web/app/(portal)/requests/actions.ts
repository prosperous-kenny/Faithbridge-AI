"use server";

import { revalidatePath } from "next/cache";
import { getAccessToken } from "@/lib/session";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

/**
 * Advance an assistance request along its lifecycle. The API enforces both the
 * role that may do this and which transitions are legal, so this action only
 * needs to forward the intent and refresh the queue. Buttons are rendered for
 * valid next states only, which keeps a rejected transition off the happy path.
 */
export async function updateRequestStatus(formData: FormData): Promise<void> {
  const requestId = Number(formData.get("request_id"));
  const status = String(formData.get("status") ?? "");

  if (!Number.isInteger(requestId) || requestId < 1 || !status) {
    return;
  }

  const token = await getAccessToken();
  if (!token) {
    return;
  }

  try {
    await fetch(`${API_URL}/api/v1/assistance/requests/${requestId}/status`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ status }),
      cache: "no-store",
    });
  } catch {
    // Unreachable API: the revalidation below re-renders the unchanged queue.
  }

  revalidatePath("/requests");
}
