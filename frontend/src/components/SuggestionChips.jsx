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
        <div className="flex flex-wrap gap-3">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-11 w-52 animate-pulse rounded-full bg-slate-100" />
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
      <div className="flex flex-wrap gap-3">
        {items.map((item, index) => (
          <motion.button
            key={`${item.number}-${item.name}`}
            type="button"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.05 }}
            onClick={() => onSelect(item.description)}
            className="rounded-full border border-slate-200 bg-slate-50 px-4 py-3 text-left text-sm text-slate-700 transition hover:border-indigo-300 hover:bg-white hover:text-slate-900"
          >
            <span className="font-semibold text-slate-900">{item.name}</span>
            <span className="ml-2 text-slate-500">{item.description}</span>
          </motion.button>
        ))}
      </div>
    </div>
  );
}
