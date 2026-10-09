import { NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/session";

/**
 * Sign-out: clear the session cookie and send the browser back to the login
 * page. A 303 makes the browser follow up with a GET so a refresh does not
 * re-submit the POST.
 */
export async function POST(request: Request) {
  const response = NextResponse.redirect(new URL("/login", request.url), {
    status: 303,
  });
  response.cookies.delete(SESSION_COOKIE);
  return response;
}
