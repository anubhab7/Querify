import { motion } from "framer-motion";
import { DatabaseZap, Layers3, LoaderCircle, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import ChatComposer from "../components/ChatComposer";
import QueryCard from "../components/QueryCard";
import SuggestionChips from "../components/SuggestionChips";
import { useToast } from "../hooks/useToast";
import { getErrorMessage } from "../services/api";
import { getChatHistory, getChatStatus, getSchema } from "../services/chats";
import { getKpis, runQuery } from "../services/query";

export default function ChatPage() {
  const { chatId } = useParams();
  const { showToast } = useToast();
  const [historyTitle, setHistoryTitle] = useState("Chat");
  const [messages, setMessages] = useState([]);
  const [status, setStatus] = useState(null);
  const [schema, setSchema] = useState("");
  const [schemaOpen, setSchemaOpen] = useState(false);
  const [kpis, setKpis] = useState([]);
  const [kpiLoading, setKpiLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [workspaceRefreshing, setWorkspaceRefreshing] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const bottomRef = useRef(null);

  function normalizeMessages(nextMessages) {
    if (!Array.isArray(nextMessages)) return [];
    return nextMessages.map((message, index) => ({
      ...message,
      id: message.id || message.created_at || `message-${index}`,
      results: Array.isArray(message.results)
        ? message.results.filter((row) => row && typeof row === "object" && !Array.isArray(row))
        : [],
    }));
  }
  
  async function loadWorkspace({ silent = false } = {}) {
    try {
      if (silent) {
        setWorkspaceRefreshing(true);
      } else {
        setHistoryLoading(true);
      }
      setKpiLoading(true);

      const [historyData, kpiData, statusData] = await Promise.all([
        getChatHistory(chatId),
        getKpis({ session_id: chatId }),
        getChatStatus(chatId),
      ]);

      setHistoryTitle(historyData.title);
      const savedTitles = JSON.parse(localStorage.getItem("querify_chat_titles") || "{}");
      localStorage.setItem(
        "querify_chat_titles",
        JSON.stringify({ ...savedTitles, [chatId]: historyData.title }),
      );
      window.dispatchEvent(new Event("querify:chat-titles"));
      setMessages(normalizeMessages(historyData.messages));
      setKpis(Array.isArray(kpiData?.kpis) ? kpiData.kpis : []);
      setStatus(statusData);
    } catch (error) {
      showToast({
        variant: "error",
        title: "Workspace load failed",
        description: getErrorMessage(error),
      });
    } finally {
      setHistoryLoading(false);
      setKpiLoading(false);
      setWorkspaceRefreshing(false);
    }
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  useEffect(() => {
    loadWorkspace();
  }, [chatId]);

  const headerCopy = useMemo(() => {
    if (status?.reachable) {
      return "Connected and ready for follow-up questions.";
    }
    if (status && !status.reachable) {
      return status.message;
    }
    return "Checking database reachability...";
  }, [status]);

  async function submitQuery(rawInput) {
    const userInput = rawInput.trim();
    if (!userInput || submitting) return;

    setPrompt("");
    setSubmitting(true);

    try {
      const response = await runQuery({
        session_id: chatId,
        user_input: userInput,
        preferred_model: "gemini",
      });

      setMessages((current) => [
        ...current,
        {
          ...response,
          user_input: userInput,
          id: crypto.randomUUID(),
          results: Array.isArray(response?.results)
            ? response.results.filter((row) => row && typeof row === "object" && !Array.isArray(row))
            : [],
        },
      ]);

      if (response.error) {
        showToast({
          variant: "error",
          title: "Query returned an issue",
          description: response.error,
        });
      }
    } catch (error) {
      showToast({
        variant: "error",
        title: "Query failed",
        description: getErrorMessage(error),
      });
      setPrompt(userInput);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleQuerySubmit(event) {
    event?.preventDefault();
    await submitQuery(prompt);
  }

  async function handleSchemaToggle() {
    if (schema) {
      setSchemaOpen((current) => !current);
      return;
    }

    try {
      const data = await getSchema(chatId);
      setSchema(data.schema);
      setSchemaOpen(true);
    } catch (error) {
      showToast({
        variant: "error",
        title: "Schema load failed",
        description: getErrorMessage(error),
      });
    }
  }

  if (historyLoading) {
    return (
      <div className="grid gap-6">
        <div className="animate-pulse rounded-[32px] border border-slate-200 bg-white p-8 shadow-soft">
          <div className="h-5 w-40 rounded bg-slate-100" />
          <div className="mt-4 h-4 w-2/3 rounded bg-slate-100" />
        </div>
        <div className="animate-pulse rounded-[32px] border border-slate-200 bg-white p-8 shadow-soft">
          <div className="h-48 rounded bg-slate-100" />
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-6">
      <motion.section
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-panel rounded-[32px] border border-slate-200 p-6 shadow-soft"
      >
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-indigo-600">
              Active Chat
            </p>
            <h1 className="mt-2 text-3xl font-semibold text-slate-900">{historyTitle}</h1>
            <p className="mt-2 text-sm text-slate-500">{headerCopy}</p>
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={handleSchemaToggle}
              className="inline-flex items-center gap-2 rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-indigo-300 hover:text-indigo-700"
            >
              <Layers3 className="h-4 w-4" />
              {schemaOpen ? "Hide Schema" : "View Schema"}
            </button>
            <button
              type="button"
              onClick={() => loadWorkspace({ silent: true })}
              disabled={workspaceRefreshing}
              className="inline-flex items-center gap-2 rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-indigo-300 hover:text-indigo-700"
            >
              <RefreshCw className={`h-4 w-4 ${workspaceRefreshing ? "animate-spin" : ""}`} />
              {workspaceRefreshing ? "Refreshing" : "Refresh"}
            </button>
          </div>
        </div>

        {schemaOpen ? (
          <div className="mt-5 rounded-3xl border border-slate-200 bg-slate-950 p-5">
            <pre className="overflow-x-auto whitespace-pre-wrap text-sm leading-7 text-slate-100">
              <code>{schema}</code>
            </pre>
          </div>
        ) : null}
      </motion.section>

      <SuggestionChips
        items={kpis}
        loading={kpiLoading}
        onSelect={submitQuery}
      />

      <section className="glass-panel rounded-[32px] border border-slate-200 p-5 shadow-soft">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
          <DatabaseZap className="h-4 w-4 text-emerald-500" />
          Conversation
        </div>

        <div className="mt-5 grid gap-6">
          {messages.length ? (
            messages.map((item) => <QueryCard key={item.id || item.created_at} item={item} />)
          ) : (
            <div className="rounded-3xl border border-dashed border-slate-200 bg-slate-50 px-5 py-10 text-center text-sm text-slate-500">
              Ask a question or use a KPI suggestion to start the conversation.
            </div>
          )}

          {submitting ? (
            <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-600">
              <LoaderCircle className="h-4 w-4 animate-spin text-indigo-600" />
              Generating SQL and running your query...
            </div>
          ) : null}

          <div ref={bottomRef} />
        </div>
      </section>

      <ChatComposer
        value={prompt}
        onChange={setPrompt}
        onSubmit={handleQuerySubmit}
        disabled={submitting}
      />
    </div>
  );
}
