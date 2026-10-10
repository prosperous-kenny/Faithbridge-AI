import { redirect } from "next/navigation";
import { getSession } from "@/lib/session";
import { loadOrganizations, Organization } from "@/lib/organizations";
import CreateOrganizationForm from "./CreateOrganizationForm";

export default async function OrganizationsPage() {
  const session = await getSession();
  if (!session) {
    redirect("/login");
  }

  // Only admins can create/list organizations
  if (session.role !== "admin") {
    redirect("/dashboard");
  }

  let organizations: Organization[] = [];
  try {
    organizations = await loadOrganizations({ token: session.token });
  } catch (err) {
    organizations = [];
    console.error("Failed to load organizations", err);
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold text-slate-900">
          Organizations
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          Manage organizations (tenancy boundary). Faith leaders are assigned to
          organizations by an administrator.
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
          <header className="border-b border-slate-200 px-6 py-4">
            <h2 className="text-lg font-semibold text-slate-900">
              Create organization
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              Add a new church, mosque, ministry, or NGO.
            </p>
          </header>
          <div className="px-6 py-6">
            <CreateOrganizationForm />
          </div>
        </section>

        <section className="rounded-xl border border-slate-200 bg-white shadow-sm lg:col-span-2">
          <header className="border-b border-slate-200 px-6 py-4">
            <h2 className="text-lg font-semibold text-slate-900">
              Existing organizations
            </h2>
          </header>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
                    ID
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
                    Name
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
                    Type
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
                    Created
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {organizations.length === 0 ? (
                  <tr>
                    <td
                      colSpan={4}
                      className="px-6 py-4 text-sm text-slate-500"
                    >
                      No organizations found.
                    </td>
                  </tr>
                ) : (
                  organizations.map((org) => (
                    <tr key={org.id}>
                      <td className="px-6 py-3 text-sm text-slate-700">
                        {org.id}
                      </td>
                      <td className="px-6 py-3 text-sm font-medium text-slate-900">
                        {org.name}
                      </td>
                      <td className="px-6 py-3 text-sm text-slate-700">
                        {org.org_type}
                      </td>
                      <td className="px-6 py-3 text-sm text-slate-700">
                        {new Date(org.created_at).toLocaleString()}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}
