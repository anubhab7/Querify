import { motion, AnimatePresence } from 'framer-motion';
import { BarChart2, Plus, FileText, Loader2, FolderClosed } from 'lucide-react';
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useToast } from '../hooks/useToast';
import { fetchReports, createReport } from '../services/api';

export default function ReportsDashboard() {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openDialog, setOpenDialog] = useState(false);
  const [newReport, setNewReport] = useState({ name: '', description: '' });
  const navigate = useNavigate();
  const { showToast } = useToast();

  useEffect(() => {
    loadReports();
  }, []);

  const loadReports = async () => {
    setLoading(true);
    try {
      const data = await fetchReports();
      setReports(data);
      const titleMap = Object.fromEntries(data.map((report) => [report.id, report.name]));
      localStorage.setItem("querify_report_titles", JSON.stringify(titleMap));
      window.dispatchEvent(new Event("querify:report-titles"));
    } catch (error) {
      console.error('Failed to fetch reports', error);
      showToast({ title: 'Failed to fetch reports', variant: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleCreateReport = async (e) => {
    e.preventDefault();
    if (!newReport.name.trim()) return;
    try {
      await createReport(newReport);
      setOpenDialog(false);
      setNewReport({ name: '', description: '' });
      loadReports();
      showToast({ title: 'Report created successfully', variant: 'success' });
    } catch (error) {
      console.error('Failed to create report', error);
      showToast({ title: 'Failed to create report', variant: 'error' });
    }
  };

  return (
    <div className="flex h-full w-full flex-col gap-6 overflow-y-auto w-full p-4 md:p-8">
      {/* Header Section */}
      <motion.section
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-panel rounded-[32px] border border-slate-200 p-6 shadow-soft md:p-8 shrink-0 relative overflow-hidden"
      >
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between relative z-10">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 mb-2">
              <BarChart2 className="h-4 w-4 text-emerald-600" />
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-600">
                Analytics
              </p>
            </div>
            <h1 className="text-3xl font-semibold text-slate-900">Reports Dashboard</h1>
            <p className="mt-2 text-sm text-slate-500">
              Manage your saved reports and generate comprehensive PDF summaries.
            </p>
          </div>
          <button
            onClick={() => setOpenDialog(true)}
            className="inline-flex items-center gap-2 rounded-2xl bg-indigo-600 px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
          >
            <Plus className="h-5 w-5" />
            Create Report
          </button>
        </div>
      </motion.section>

      {/* Content Section */}
      {loading ? (
         <div className="flex flex-1 items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
         </div>
      ) : reports.length === 0 ? (
        <motion.div 
          initial={{ opacity: 0 }} 
          animate={{ opacity: 1 }} 
          transition={{ delay: 0.1 }}
          className="flex flex-1 flex-col items-center justify-center rounded-[32px] border border-dashed border-slate-300 bg-white/50 p-12 text-center"
        >
          <div className="rounded-full bg-slate-200/50 p-4 mb-4">
            <FolderClosed className="h-8 w-8 text-slate-400" />
          </div>
          <h3 className="text-lg font-semibold text-slate-900">No reports found</h3>
          <p className="mt-2 text-sm text-slate-500 max-w-sm">
            Create a new report to start saving your queries and generating insights.
          </p>
          <button
            onClick={() => setOpenDialog(true)}
            className="mt-6 inline-flex items-center gap-2 rounded-full border border-slate-300 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 hover:text-indigo-600"
          >
            <Plus className="h-4 w-4" />
            Create Your First Report
          </button>
        </motion.div>
      ) : (
        <motion.div 
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 pb-8"
        >
          <AnimatePresence>
            {reports.map((report, idx) => (
              <motion.div
                key={report.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.05 }}
                className="group flex flex-col justify-between rounded-[32px] border border-slate-200 bg-white p-6 shadow-sm transition-all hover:border-indigo-300 hover:shadow-soft"
              >
                <div>
                  <div className="mb-4 inline-flex rounded-2xl bg-slate-50 p-3 text-slate-500 group-hover:bg-indigo-50 group-hover:text-indigo-600 transition-colors">
                    <FileText className="h-6 w-6" />
                  </div>
                  <h3 className="text-lg font-semibold text-slate-900 line-clamp-1">{report.name}</h3>
                  <p className="mt-2 text-sm text-slate-500 line-clamp-2 h-10">
                    {report.description || 'No description provided.'}
                  </p>
                </div>
                
                <div className="mt-6 flex items-center justify-between border-t border-slate-100 pt-4">
                  <span className="inline-flex items-center rounded-lg bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">
                    {report.item_count} {report.item_count === 1 ? 'Item' : 'Items'}
                  </span>
                  <button
                    onClick={() => navigate(`/reports/${report.id}`)}
                    className="text-sm font-medium text-indigo-600 hover:text-indigo-700 flex items-center transition"
                  >
                    View Details
                  </button>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </motion.div>
      )}

      {/* Dialog */}
      <AnimatePresence>
        {openDialog && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div 
              initial={{ opacity: 0 }} 
              animate={{ opacity: 1 }} 
              exit={{ opacity: 0 }} 
              className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm"
              onClick={() => setOpenDialog(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              className="relative w-full max-w-lg rounded-[32px] border border-slate-200 bg-white p-8 shadow-xl"
            >
              <h2 className="text-xl font-semibold text-slate-900">Create New Report</h2>
              <form onSubmit={handleCreateReport} className="mt-6 space-y-4">
                <div>
                  <label htmlFor="name" className="block text-sm font-medium text-slate-700">
                    Report Name
                  </label>
                  <input
                    type="text"
                    id="name"
                    required
                    autoFocus
                    value={newReport.name}
                    onChange={(e) => setNewReport({ ...newReport, name: e.target.value })}
                    className="mt-2 block w-full rounded-2xl border-0 p-3.5 text-slate-900 shadow-sm ring-1 ring-inset ring-slate-300 placeholder:text-slate-400 focus:ring-2 focus:ring-inset focus:ring-indigo-600 text-sm leading-6 outline-none transition-all"
                    placeholder="E.g., Q3 Sales Performance"
                  />
                </div>
                <div>
                  <label htmlFor="description" className="block text-sm font-medium text-slate-700">
                    Description <span className="text-slate-400 font-normal">(Optional)</span>
                  </label>
                  <textarea
                    id="description"
                    rows={3}
                    value={newReport.description}
                    onChange={(e) => setNewReport({ ...newReport, description: e.target.value })}
                    className="mt-2 block w-full rounded-2xl border-0 p-3.5 text-slate-900 shadow-sm ring-1 ring-inset ring-slate-300 placeholder:text-slate-400 focus:ring-2 focus:ring-inset focus:ring-indigo-600 text-sm leading-6 resize-none outline-none transition-all"
                    placeholder="What is this report about?"
                  />
                </div>
                <div className="mt-8 flex justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => setOpenDialog(false)}
                    className="rounded-2xl px-5 py-3 text-sm font-semibold text-slate-600 hover:bg-slate-50 transition"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={!newReport.name.trim()}
                    className="rounded-2xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition"
                  >
                    Create Report
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
