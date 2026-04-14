import { motion } from "framer-motion";
import { Sparkles } from "lucide-react";

export default function SuggestionChips({ items, onSelect, loading, error }) {
  if (loading) {
    return (
      <div className="rounded-3xl border border-slate-200 bg-white/80 p-6 shadow-soft">
        <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-slate-700">
          <Sparkles className="h-4 w-4 text-emerald-500" />
          KPI Suggestions
        </div>
        <div className="flex min-h-[176px] flex-col items-center justify-center rounded-3xl border border-dashed border-slate-200 bg-slate-50/80 px-5 py-10 text-center">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-slate-200 border-t-emerald-500" />
          <p className="mt-4 text-base font-semibold text-slate-900">Loading KPIs</p>
          <p className="mt-2 max-w-md text-sm leading-6 text-slate-500">
            Gemini is analyzing the connected schema and preparing suggested KPI prompts.
          </p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-3xl border border-amber-200 bg-amber-50/70 p-5 shadow-soft">
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-amber-900">
          <Sparkles className="h-4 w-4 text-amber-600" />
          KPI Suggestions
        </div>
        <div className="rounded-2xl border border-amber-200 bg-white/70 p-4 text-sm text-amber-950">
          <p className="font-semibold">KPI suggestions could not be loaded.</p>
          <p className="mt-2 leading-6 text-amber-900/80">{error}</p>
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
