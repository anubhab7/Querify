import { motion } from "framer-motion";
import { Sparkles } from "lucide-react";

export default function SuggestionChips({ items, onSelect, loading }) {
  if (loading) {
    return (
      <div className="rounded-3xl border border-slate-200 bg-white/80 p-5 shadow-soft">
        <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-slate-700">
          <Sparkles className="h-4 w-4 text-emerald-500" />
          KPI Suggestions
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
              <div className="mb-3 flex items-center gap-2">
                <div className="h-2.5 w-2.5 animate-pulse rounded-full bg-emerald-400" />
                <div className="h-4 w-24 animate-pulse rounded bg-slate-200" />
              </div>
              <div className="h-4 w-3/4 animate-pulse rounded bg-slate-200" />
              <div className="mt-2 h-4 w-full animate-pulse rounded bg-slate-100" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!items?.length) {
    return null;
  }

  return (
    <div className="rounded-3xl border border-slate-200 bg-white/85 p-5 shadow-soft">
      <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-slate-700">
        <Sparkles className="h-4 w-4 text-emerald-500" />
        Suggested KPI prompts
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {items.map((item, index) => (
          <motion.button
            key={`${item.number}-${item.name}`}
            type="button"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.05 }}
            onClick={() => onSelect(item.description)}
            className="rounded-2xl border border-slate-200 bg-slate-50/90 p-4 text-left text-sm text-slate-700 shadow-sm transition hover:border-indigo-300 hover:bg-white hover:text-slate-900"
          >
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-emerald-600">
              <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" />
              KPI {item.number}
            </div>
            <p className="font-semibold text-slate-900">{item.name}</p>
            <p className="mt-2 leading-6 text-slate-500">{item.description}</p>
          </motion.button>
        ))}
      </div>
    </div>
  );
}
