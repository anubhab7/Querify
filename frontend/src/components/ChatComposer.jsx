import { SendHorizontal } from "lucide-react";

export default function ChatComposer({
  value,
  onChange,
  onSubmit,
  disabled,
  placeholder = "Ask about your PostgreSQL data...",
}) {
  return (
    <form
      onSubmit={onSubmit}
      className="glass-panel sticky bottom-0 rounded-[28px] border border-slate-200 px-4 py-4 shadow-soft"
    >
      <div className="flex items-end gap-3">
        <textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          rows={1}
          placeholder={placeholder}
          className="max-h-40 min-h-[52px] flex-1 resize-none border-0 bg-transparent px-2 py-3 text-base text-slate-900 outline-none placeholder:text-slate-400"
        />
        <button
          type="submit"
          disabled={disabled || !value.trim()}
          className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-900 text-white transition hover:bg-indigo-600 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          <SendHorizontal className="h-5 w-5" />
        </button>
      </div>
    </form>
  );
}
