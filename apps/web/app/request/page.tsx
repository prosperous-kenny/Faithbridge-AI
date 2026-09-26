import RequestForm from "@/components/RequestForm";

export const metadata = {
  title: "Submit Request — FaithBridge AI",
};

export default function RequestPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="text-3xl font-bold text-slate-900">
        Submit an Assistance Request
      </h1>
      <p className="mt-2 text-slate-600">
        This form exercises the full request path: Next.js route handler →
        FastAPI → AI classification service → response.
      </p>
      <div className="mt-10">
        <RequestForm />
      </div>
    </div>
  );
}
