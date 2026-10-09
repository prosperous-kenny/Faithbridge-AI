/**
 * Plain HTML form posting to the logout route handler. Works without client
 * JavaScript: the handler clears the cookie and 303-redirects to /login.
 */
export default function SignOutButton() {
  return (
    <form action="/api/auth/logout" method="post">
      <button
        type="submit"
        className="rounded-lg px-3 py-1.5 text-sm font-medium text-amber-900 transition hover:bg-amber-100"
      >
        Sign out
      </button>
    </form>
  );
}
