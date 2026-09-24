export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-8">
      <h1 className="text-4xl font-bold">FaithBridge AI</h1>
      <p className="max-w-xl text-center text-lg text-gray-600">
        Transforming faith-based giving into measurable community impact.
      </p>
      <p className="text-sm text-gray-400">Web application scaffold — API: {process.env.NEXT_PUBLIC_API_URL}</p>
    </main>
  );
}