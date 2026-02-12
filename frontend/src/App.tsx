import { useState } from "react";
import { Search, Sparkles } from "lucide-react";

export default function App() {
  const [query, setQuery] = useState("");
  const [response, setResponse] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const handleQuery = async () => {
    if (!query.trim()) return;
    setIsLoading(true);
    setError("");
    setResponse("");

    try {
      const backendUrl = import.meta.env.VITE_BACKEND_URL;
      if (!backendUrl) throw new Error("VITE_BACKEND_URL not set");

      const res = await fetch(
        `${backendUrl}?query=${encodeURIComponent(query)}`
      );

      if (!res.ok) throw new Error("Failed to fetch response");

      const data = await res.json();
      if (data.status === "success") {
        setResponse(data.data);
      } else {
        throw new Error(data.message || "Unexpected error");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-linear-to-b from-neutral-950 via-neutral-900 to-neutral-950 text-white flex flex-col">
      {/* Header */}
      <header className="py-6 text-center">
        <h1 className="text-4xl md:text-5xl font-semibold tracking-tight">
          Perplexity<span className="text-orange-500">.</span>
        </h1>
        <p className="text-gray-400 mt-2">
          Ask questions. Get concise, sourced answers.
        </p>
      </header>

      {/* Main */}
      <main className="flex-1 flex flex-col items-center justify-center px-4">
        {/* Search box */}
        <div className="w-full max-w-2xl">
          <div className="relative group">
            <Search className="absolute left-5 top-1/2 -translate-y-1/2 text-gray-500 group-focus-within:text-orange-500" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !isLoading && handleQuery()}
              placeholder="Ask anything…"
              disabled={isLoading}
              className="w-full rounded-2xl bg-neutral-900 border border-neutral-700 py-4 pl-14 pr-28 text-base text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-orange-500/40"
            />

            <button
              onClick={handleQuery}
              disabled={isLoading}
              className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-2 rounded-xl bg-orange-500 px-4 py-2 text-sm font-medium text-black hover:bg-orange-400 disabled:opacity-60"
            >
              <Sparkles size={16} />
              Ask
            </button>
          </div>

          {/* Helper text */}
          <p className="mt-3 text-center text-sm text-gray-500">
            Press <span className="text-gray-300">Enter</span> to search the web
          </p>
        </div>

        {/* Loading */}
        {isLoading && (
          <div className="mt-10 flex items-center gap-3 text-gray-400">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-orange-500 border-t-transparent" />
            <span>Searching and summarising…</span>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mt-8 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-400">
            {error}
          </div>
        )}

        {/* Response */}
        {response && !isLoading && (
          <section className="mt-12 w-full max-w-3xl">
            <div className="rounded-2xl border border-neutral-800 bg-neutral-900/70 p-6 shadow-xl">
              <h2 className="mb-4 text-lg font-semibold text-gray-200">
                Answer
              </h2>
              <p className="whitespace-pre-wrap leading-relaxed text-gray-300">
                {response}
              </p>
            </div>
          </section>
        )}
      </main>

      {/* Footer */}
      <footer className="py-4 text-center text-xs text-gray-500">
        Built with React, Tailwind & LLMs
      </footer>
    </div>
  );
}
