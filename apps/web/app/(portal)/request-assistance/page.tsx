import RequestForm from "@/components/RequestForm";

export const metadata = {
  title: "Request Assistance — FaithBridge AI",
};

export default function RequestAssistancePage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="text-3xl font-bold text-slate-900">
        Request Assistance
      </h1>
      <p className="mt-2 text-slate-600">
        Submit a need to an organization queue. The AI service classifies the
        request and scores its urgency for the faith leaders triaging it.
      </p>
      <div className="mt-10">
        <RequestForm />
      </div>
    </div>
  );
}