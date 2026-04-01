import { ArrowDownWideNarrow, ArrowUpWideNarrow } from "lucide-react";
import { useMemo, useState } from "react";

function compareValues(a, b) {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;

  if (typeof a === "number" && typeof b === "number") {
    return a - b;
  }

  return String(a).localeCompare(String(b), undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

export default function ResultsTable({ rows }) {
  const [sortConfig, setSortConfig] = useState(null);

  const columns = useMemo(() => {
    if (!rows?.length) return [];
    return Array.from(
      rows.reduce((set, row) => {
        Object.keys(row).forEach((key) => set.add(key));
        return set;
      }, new Set()),
    );
  }, [rows]);

  const sortedRows = useMemo(() => {
    if (!sortConfig) return rows || [];

    const nextRows = [...(rows || [])];
    nextRows.sort((left, right) => {
      const result = compareValues(left[sortConfig.key], right[sortConfig.key]);
      return sortConfig.direction === "asc" ? result : result * -1;
    });
    return nextRows;
  }, [rows, sortConfig]);

  function toggleSort(key) {
    setSortConfig((current) => {
      if (!current || current.key !== key) {
        return { key, direction: "asc" };
      }
      if (current.direction === "asc") {
        return { key, direction: "desc" };
      }
      return null;
    });
  }

  if (!rows?.length) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-5 text-sm text-slate-500">
        Query returned no rows.
      </div>
    );
  }

  return (
    <div className="w-full max-w-full overflow-hidden rounded-3xl border border-slate-200 bg-white">
      <div className="w-full overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              {columns.map((column) => {
                const isActive = sortConfig?.key === column;
                return (
                  <th
                    key={column}
                    className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-[0.18em] text-slate-500"
                  >
                    <button
                      type="button"
                      onClick={() => toggleSort(column)}
                      className="inline-flex items-center gap-2 transition hover:text-indigo-600"
                    >
                      <span>{column}</span>
                      {isActive && sortConfig.direction === "desc" ? (
                        <ArrowDownWideNarrow className="h-4 w-4" />
                      ) : (
                        <ArrowUpWideNarrow className={`h-4 w-4 ${isActive ? "text-indigo-600" : ""}`} />
                      )}
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {sortedRows.map((row, rowIndex) => (
              <tr key={rowIndex} className="transition hover:bg-slate-50">
                {columns.map((column) => (
                  <td key={`${rowIndex}-${column}`} className="max-w-xs px-4 py-3 align-top text-slate-700">
                    <span className="break-words">{String(row[column] ?? "—")}</span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
