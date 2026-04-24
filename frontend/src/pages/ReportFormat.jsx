import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, Download, Loader2, PaintBucket, Type, PieChart } from 'lucide-react';
import { fetchReportDetails, generateReportPdf } from '../services/api';
import { useToast } from '../hooks/useToast';

export default function ReportFormat() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { showToast } = useToast();

  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [report, setReport] = useState(null);
  const [items, setItems] = useState([]);

  const [theme, setTheme] = useState('default');
  const [font, setFont] = useState('Arial');
  const [visualizations, setVisualizations] = useState({});

  useEffect(() => {
    loadReportDetails();
  }, [id]);

  const loadReportDetails = async () => {
    setLoading(true);
    try {
      const data = await fetchReportDetails(id);
      setReport(data.report);
      setItems(data.items);

      const initialViz = {};
      data.items.forEach(item => {
        initialViz[item.id] = 'table';
      });
      setVisualizations(initialViz);
    } catch (error) {
      console.error('Failed to fetch report details', error);
      showToast({ title: 'Failed to load report details', variant: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleVizChange = (itemId, type) => {
    setVisualizations(prev => ({
      ...prev,
      [itemId]: type
    }));
  };

  const handleGeneratePdf = async () => {
    setGenerating(true);
    try {
      const config = {
        theme,
        font,
        visualizations
      };
      const blob = await generateReportPdf(id, config);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = url;
      a.download = `report_${id}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      showToast({ title: 'Report generated successfully', variant: 'success' });
    } catch (error) {
      showToast({ title: 'Failed to generate report', variant: 'error' });
    } finally {
      setGenerating(false);
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
          onClick={() => navigate(`/reports/${id}`)}
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Report
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-2rem)] w-full flex-col gap-6 p-4 md:p-8 overflow-y-auto">
      <div className="mx-auto w-full max-w-4xl pb-12">
        <button
          onClick={() => navigate(`/reports/${id}`)}
          className="group mb-6 inline-flex items-center gap-2 text-sm font-medium text-slate-500 hover:text-indigo-600 transition"
        >
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-white border border-slate-200 group-hover:border-indigo-200 group-hover:bg-indigo-50 transition shadow-sm">
            <ArrowLeft className="h-4 w-4" />
          </div>
          Back to Report Details
        </button>

        <motion.section
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-panel rounded-[32px] border border-slate-200 p-6 shadow-soft md:p-8 mb-8"
        >
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-[0.24em] text-indigo-600">
                Format Report
              </p>
              <h1 className="text-3xl font-semibold text-slate-900">{report.name}</h1>
              <p className="mt-2 text-sm text-slate-500 max-w-2xl">Customize the appearance of your report before generating the PDF.</p>
            </div>
            <button
              onClick={handleGeneratePdf}
              disabled={generating || items.length === 0}
              className="inline-flex shrink-0 items-center gap-2 rounded-2xl bg-indigo-600 px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {generating ? (
                <>
                  <Loader2 className="h-5 w-5 animate-spin" />
                  Generating PDF...
                </>
              ) : (
                <>
                  <Download className="h-5 w-5" />
                  Generate & Download PDF
                </>
              )}
            </button>
          </div>
        </motion.section>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-8">
          <div className="glass-panel p-6 rounded-3xl border border-slate-200 shadow-sm">
            <div className="flex items-center gap-3 mb-4">
              <PaintBucket className="h-5 w-5 text-indigo-500" />
              <h3 className="text-lg font-semibold text-slate-800">Color Theme</h3>
            </div>
            <select
              value={theme}
              onChange={(e) => setTheme(e.target.value)}
              className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="default">Default Light</option>
              <option value="dark">Dark Mode</option>
              <option value="blue">Professional Blue</option>
            </select>
          </div>

          <div className="glass-panel p-6 rounded-3xl border border-slate-200 shadow-sm">
            <div className="flex items-center gap-3 mb-4">
              <Type className="h-5 w-5 text-indigo-500" />
              <h3 className="text-lg font-semibold text-slate-800">Font Family</h3>
            </div>
            <select
              value={font}
              onChange={(e) => setFont(e.target.value)}
              className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="Arial">Arial (Sans-serif)</option>
              <option value="Times New Roman">Times New Roman (Serif)</option>
              <option value="Courier New">Courier New (Monospace)</option>
            </select>
          </div>
        </div>

        <div className="glass-panel rounded-3xl border border-slate-200 shadow-sm p-6 md:p-8">
          <div className="flex items-center gap-3 mb-6 border-b border-slate-100 pb-4">
            <PieChart className="h-5 w-5 text-indigo-500" />
            <h3 className="text-xl font-semibold text-slate-800">Item Visualizations</h3>
          </div>

          <div className="flex flex-col gap-6">
            {items.map((item, index) => (
              <div key={item.id} className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-2xl bg-slate-50 border border-slate-100">
                <div className="flex-1">
                  <div className="flex items-center gap-3">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-700">
                      {index + 1}
                    </span>
                    <h4 className="font-medium text-slate-900">{item.query_text || 'Data Snapshot'}</h4>
                  </div>
                  <p className="mt-1 text-xs text-slate-500 ml-9">
                    {item.data_snapshot?.length || 0} rows of data available.
                  </p>
                </div>

                <div className="w-full sm:w-48">
                  <select
                    value={visualizations[item.id] || 'table'}
                    onChange={(e) => handleVizChange(item.id, e.target.value)}
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="table">Table</option>
                    <option value="bar">Bar Chart</option>
                    <option value="line">Line Chart</option>
                    <option value="pie">Pie Chart</option>
                  </select>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
