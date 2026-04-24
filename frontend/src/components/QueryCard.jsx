import { motion, AnimatePresence } from "framer-motion";
import { Bot, Code2, LoaderCircle, UserRound, BookmarkPlus } from "lucide-react";
import { useState, useRef, useEffect } from "react";
import ResultsTable from "./ResultsTable";

export default function QueryCard({ item, reports = [], onAddToReport }) {
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

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
                    <div className="mb-3 flex items-center justify-between">
                      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
                        Results
                      </p>
                      <div className="relative" ref={dropdownRef}>
                        <button
                          onClick={() => setDropdownOpen(!dropdownOpen)}
                          title="Add to Report"
                          className="flex items-center justify-center rounded-full p-2 text-indigo-500 transition-colors hover:bg-indigo-50 hover:text-indigo-700 focus:outline-none"
                        >
                          <BookmarkPlus className="h-5 w-5" />
                        </button>
                        
                        <AnimatePresence>
                          {dropdownOpen && (
                            <motion.div
                              initial={{ opacity: 0, y: 8, scale: 0.95 }}
                              animate={{ opacity: 1, y: 0, scale: 1 }}
                              exit={{ opacity: 0, y: 8, scale: 0.95 }}
                              transition={{ duration: 0.15, ease: "easeOut" }}
                              className="absolute right-0 top-full mt-2 w-64 origin-top-right overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl focus:outline-none z-50"
                            >
                              <div className="py-2">
                                <div className="px-4 py-2 border-b border-slate-100 mb-1">
                                  <p className="text-xs font-bold uppercase tracking-wider text-slate-500">Save to Report</p>
                                </div>
                                {reports.length === 0 ? (
                                  <div className="px-4 py-3 text-sm text-slate-500 italic">
                                    No reports available
                                  </div>
                                ) : (
                                  <div className="max-h-60 overflow-y-auto custom-scrollbar">
                                    {reports.map((r) => (
                                      <button
                                        key={r.id}
                                        onClick={() => {
                                          setDropdownOpen(false);
                                          onAddToReport(r.id);
                                        }}
                                        className="block w-full px-4 py-2.5 text-left text-sm font-medium text-slate-700 hover:bg-indigo-50 hover:text-indigo-700 transition-colors"
                                      >
                                        <span className="truncate block">{r.name}</span>
                                      </button>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </div>
                    </div>
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
