import { motion } from "framer-motion";
import { Bot, Code2, LoaderCircle, UserRound } from "lucide-react";

import ResultsTable from "./ResultsTable";

export default function QueryCard({ item }) {
  const results = Array.isArray(item?.results)
    ? item.results.filter((row) => row && typeof row === "object" && !Array.isArray(row))
    : [];
  const isErrorOnlyReply = Boolean(item.error && !item.sql_query && results.length === 0);

  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-4"
    >
      <div className="flex justify-end">
        <div className="flex max-w-3xl flex-row-reverse items-start gap-3">
          <div className="rounded-2xl bg-slate-900 p-2 text-white">
            <UserRound className="h-4 w-4" />
          </div>
          <div className="rounded-[26px] rounded-tr-md bg-slate-900 px-5 py-4 text-sm leading-7 text-white shadow-soft">
            {item.user_input}
          </div>
        </div>
      </div>

      <div className="flex justify-start">
        <div className="flex w-full min-w-0 max-w-5xl items-start gap-3">
          <div className="rounded-2xl bg-emerald-100 p-2 text-emerald-600">
            <Bot className="h-4 w-4" />
          </div>
          <div className="min-w-0 w-full rounded-[28px] rounded-tl-md border border-slate-200 bg-white p-5 shadow-soft">
            {item.pending ? (
              <div className="flex items-center gap-3 rounded-2xl border border-slate-100 bg-slate-50 px-4 py-4 text-sm text-slate-600">
                <LoaderCircle className="h-4 w-4 animate-spin text-indigo-600" />
                Generating SQL...
              </div>
            ) : isErrorOnlyReply ? (
              <div className="break-words rounded-2xl border border-rose-200 bg-rose-50 px-4 py-4 text-sm leading-7 text-rose-700">
                {item.error}
              </div>
            ) : (
              <div className="grid gap-5">
                <div>
                  <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
                    <Code2 className="h-4 w-4" />
                    SQL Query
                  </div>
                  <pre className="max-w-full overflow-x-auto rounded-2xl bg-slate-950 p-4 text-sm leading-7 text-slate-100">
                    <code>{item.sql_query || "-- No SQL generated --"}</code>
                  </pre>
                </div>

                <div>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
                    Explanation
                  </p>
                  <p className="break-words text-sm leading-7 text-slate-700">
                    {item.explanation || "No explanation returned."}
                  </p>
                </div>

                {item.error ? (
                  <div className="break-words rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                    {item.error}
                  </div>
                ) : null}

                {results.length > 0 ? (
                  <div>
                    <p className="mb-3 text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
                      Results
                    </p>
                    <ResultsTable rows={results} />
                  </div>
                ) : null}
              </div>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  );
}
