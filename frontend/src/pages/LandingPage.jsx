import { motion } from "framer-motion";
import { Database, Lock, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useToast } from "../hooks/useToast";
import { createChat } from "../services/chats";
import { getErrorMessage } from "../services/api";

const initialForm = {
  host: "",
  port: 5432,
  database: "",
  username: "",
  password: "",
  ssl: false,
};

export default function LandingPage() {
  const [form, setForm] = useState(initialForm);
  const [submitting, setSubmitting] = useState(false);
  const { showToast } = useToast();
  const navigate = useNavigate();

  async function handleSubmit(event) {
    event.preventDefault();
    try {
      setSubmitting(true);
      const data = await createChat(form);
      showToast({
        variant: "success",
        title: "Connection created",
        description: "Your database session is ready.",
      });
      navigate(`/chat/${data.session_id}`);
    } catch (error) {
      showToast({
        variant: "error",
        title: "Connection failed",
        description: getErrorMessage(error),
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-[calc(100vh-160px)] max-w-6xl items-center">
      <div className="grid w-full gap-8 lg:grid-cols-[1.1fr_0.9fr]">
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          className="self-center"
        >
          <div className="max-w-2xl">
            <p className="text-sm font-semibold uppercase tracking-[0.3em] text-indigo-600">
              Fresh Connection
            </p>
            <h1 className="mt-4 text-5xl font-semibold leading-tight text-slate-900">
              Ask better questions of your PostgreSQL data.
            </h1>
            <p className="mt-6 text-lg leading-8 text-slate-600">
              Connect a database, generate KPI prompts automatically, and explore results through a clean Gemini-style workspace.
            </p>
          </div>

          <div className="mt-10 grid gap-4 sm:grid-cols-3">
            {[
              { icon: Database, title: "Live SQL", copy: "Natural language into validated PostgreSQL queries." },
              { icon: ShieldCheck, title: "Secure Sessions", copy: "JWT-protected chats with reusable database context." },
              { icon: Lock, title: "Readable Results", copy: "Sortable tables built for analysis, not raw dumps." },
            ].map((item) => (
              <div key={item.title} className="rounded-3xl border border-white/60 bg-white/70 p-5 shadow-soft">
                <item.icon className="h-5 w-5 text-indigo-600" />
                <p className="mt-4 font-semibold text-slate-900">{item.title}</p>
                <p className="mt-2 text-sm leading-6 text-slate-600">{item.copy}</p>
              </div>
            ))}
          </div>
        </motion.div>

        <motion.form
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          onSubmit={handleSubmit}
          className="glass-panel rounded-[32px] border border-slate-200 p-7 shadow-soft"
        >
          <div className="mb-6 flex items-center gap-3">
            <div className="rounded-2xl bg-slate-900 p-3 text-white">
              <Database className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-2xl font-semibold text-slate-900">Connect Database</h2>
              <p className="text-sm text-slate-500">Create a new chat session from fresh credentials.</p>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Host">
              <input
                required
                value={form.host}
                onChange={(event) => setForm((current) => ({ ...current, host: event.target.value }))}
                className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-indigo-400"
              />
            </Field>
            <Field label="Port">
              <input
                required
                type="number"
                value={form.port}
                onChange={(event) => setForm((current) => ({ ...current, port: Number(event.target.value) }))}
                className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-indigo-400"
              />
            </Field>
            <Field label="Database Name">
              <input
                required
                value={form.database}
                onChange={(event) => setForm((current) => ({ ...current, database: event.target.value }))}
                className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-indigo-400"
              />
            </Field>
            <Field label="Username">
              <input
                required
                value={form.username}
                onChange={(event) => setForm((current) => ({ ...current, username: event.target.value }))}
                className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-indigo-400"
              />
            </Field>
            <Field label="Password" className="sm:col-span-2">
              <input
                required
                type="password"
                value={form.password}
                onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))}
                className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-indigo-400"
              />
            </Field>
          </div>

          <label className="mt-5 flex items-center justify-between rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
            <div>
              <p className="text-sm font-medium text-slate-800">Require SSL</p>
              <p className="text-sm text-slate-500">Enable this when your PostgreSQL server expects secure connections.</p>
            </div>
            <input
              type="checkbox"
              checked={form.ssl}
              onChange={(event) => setForm((current) => ({ ...current, ssl: event.target.checked }))}
              className="h-5 w-5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
            />
          </label>

          <button
            type="submit"
            disabled={submitting}
            className="mt-6 inline-flex w-full items-center justify-center rounded-2xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600 disabled:bg-slate-300"
          >
            {submitting ? "Connecting..." : "Start New Chat"}
          </button>
        </motion.form>
      </div>
    </div>
  );
}

function Field({ label, className = "", children }) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-2 block text-sm font-medium text-slate-700">{label}</span>
      {children}
    </label>
  );
}
