import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { ArrowLeft, Trash2, Download, Loader2, DatabaseZap, SearchCode, Database } from 'lucide-react';
import { fetchReportDetails, deleteReportItem, generateReportPdf } from '../services/api';
import { useToast } from '../hooks/useToast';

export default function ReportDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [report, setReport] = useState(null);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    loadReportDetails();
  }, [id]);

  const loadReportDetails = async () => {
    setLoading(true);
    try {
      const data = await fetchReportDetails(id);
      setReport(data.report);
      setItems(data.items);
      
      const stored = JSON.parse(localStorage.getItem("querify_report_titles") || "{}");
      stored[id] = data.report.name;
      localStorage.setItem("querify_report_titles", JSON.stringify(stored));
      window.dispatchEvent(new Event("querify:report-titles"));
    } catch (error) {
      console.error('Failed to fetch report details', error);
      showToast({ title: 'Failed to load report details', variant: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteItem = async (itemId) => {
    if (!window.confirm("Are you sure you want to remove this item?")) return;
    try {
      await deleteReportItem(itemId);
      showToast({ title: 'Item removed successfully', variant: 'success' });
      loadReportDetails();
    } catch (error) {
      showToast({ title: 'Failed to delete item', variant: 'error' });
    }
  };

  if (loading) {
    return (
      <div className="flex h-full w-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  if (!report) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center p-8">
        <h2 className="text-xl font-semibold text-rose-600">Report not found</h2>
        <button 
          className="mt-4 flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-indigo-600 transition"
          onClick={() => navigate('/reports')}
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Reports
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-2rem)] w-full flex-col gap-6 p-4 md:p-8 overflow-y-auto">
      <div className="mx-auto w-full max-w-5xl pb-12">
        <button 
          onClick={() => navigate('/reports')}
          className="group mb-6 inline-flex items-center gap-2 text-sm font-medium text-slate-500 hover:text-indigo-600 transition"
        >
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-white border border-slate-200 group-hover:border-indigo-200 group-hover:bg-indigo-50 transition shadow-sm">
            <ArrowLeft className="h-4 w-4" />
          </div>
          Back to Reports Dashboard
        </button>

        <motion.section
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-panel rounded-[32px] border border-slate-200 p-6 shadow-soft md:p-8"
        >
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-[0.24em] text-indigo-600">
                Report Details
              </p>
              <h1 className="text-3xl font-semibold text-slate-900">{report.name}</h1>
              {report.description && (
                <p className="mt-2 text-sm text-slate-500 max-w-2xl">{report.description}</p>
              )}
            </div>
            <button
              onClick={() => navigate(`/reports/${id}/format`)}
              disabled={items.length === 0}
              className="inline-flex shrink-0 items-center gap-2 rounded-2xl bg-indigo-600 px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
            >
              Format Report
            </button>
          </div>
        </motion.section>

        <div className="mt-8">
          <div className="mb-6 flex items-center gap-2 text-sm font-semibold text-slate-700">
            <DatabaseZap className="h-5 w-5 text-emerald-500" />
            Report Items ({items.length})
          </div>

          {items.length === 0 ? (
            <div className="rounded-[32px] border border-dashed border-slate-300 bg-white/50 p-12 text-center shadow-sm">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 mb-4">
                <SearchCode className="h-6 w-6 text-slate-400" />
              </div>
              <h3 className="text-lg font-medium text-slate-900">No items in this report yet</h3>
              <p className="mt-2 text-sm text-slate-500">
                Go to the chat interface to add queries and insights to this report.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-6">
              <AnimatePresence>
                {items.map((item, index) => (
                  <motion.div
                    key={item.id}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    className="glass-panel group relative overflow-hidden rounded-[32px] border border-slate-200 bg-white shadow-soft transition-all hover:border-slate-300"
                  >
                    <div className="flex items-start justify-between border-b border-slate-100 bg-slate-50/50 p-6">
                      <div className="flex items-start gap-4 pr-12">
                        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-sm font-bold text-indigo-700">
                          {index + 1}
                        </div>
                        <div>
                          <h3 className="text-lg font-semibold text-slate-900">
                            {item.query_text || 'Snapshot'}
                          </h3>
                        </div>
                      </div>
                      
                      <button
                        onClick={() => handleDeleteItem(item.id)}
                        className="absolute right-6 top-6 rounded-full p-2 text-slate-400 opacity-0 transition-all hover:bg-rose-50 hover:text-rose-500 group-hover:opacity-100 focus:opacity-100"
                        title="Remove Item"
                      >
                        <Trash2 className="h-5 w-5" />
                      </button>
                    </div>

                    <div className="p-6">
                      {item.explanation && (
                        <div className="mb-6 rounded-2xl bg-indigo-50/50 border border-indigo-100 p-4">
                          <p className="text-sm leading-relaxed text-indigo-900/80">
                            {item.explanation}
                          </p>
                        </div>
                      )}

                      {item.data_snapshot && item.data_snapshot.length > 0 && (
                        <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200 shadow-sm">
                          <div className="overflow-x-auto max-h-[300px] overflow-y-auto custom-scrollbar">
                            <table className="w-full text-left text-sm text-slate-600">
                              <thead className="sticky top-0 z-10 bg-slate-50 shadow-sm border-b border-slate-200">
                                <tr>
                                  {Object.keys(item.data_snapshot[0]).map((key) => (
                                    <th
                                      key={key}
                                      className="whitespace-nowrap px-4 py-3 font-semibold text-slate-900"
                                    >
                                      {key.replace(/_/g, ' ')}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-slate-100 bg-white">
                                {item.data_snapshot.slice(0, 5).map((row, i) => (
                                  <tr key={i} className="hover:bg-slate-50/50 transition">
                                    {Object.values(row).map((val, colIdx) => (
                                      <td key={colIdx} className="whitespace-nowrap px-4 py-3">
                                        {typeof val === 'boolean' ? val.toString() : val}
                                      </td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}
                      {item.data_snapshot && item.data_snapshot.length > 5 && (
                        <p className="mt-3 text-xs font-medium text-slate-400">
                          Showing top 5 rows out of {item.data_snapshot.length} total.
                        </p>
                      )}
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
