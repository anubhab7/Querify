import { AnimatePresence, motion } from "framer-motion";
import { Database, MessageSquareMore, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { useToast } from "../hooks/useToast";
import { deleteChat, getChats } from "../services/chats";
import { getErrorMessage } from "../services/api";

function formatDate(value) {
  return new Date(value).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default function Sidebar({ activeChatId }) {
  const [chats, setChats] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState(null);
  const { showToast } = useToast();
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    let mounted = true;

    async function loadChats() {
      try {
        const data = await getChats();
        if (mounted) {
          setChats(data);
          const titleMap = Object.fromEntries(
            data.map((chat) => [chat.id, chat.title]),
          );
          localStorage.setItem("querify_chat_titles", JSON.stringify(titleMap));
          window.dispatchEvent(new Event("querify:chat-titles"));
        }
      } catch (error) {
        showToast({
          variant: "error",
          title: "Could not load chats",
          description: getErrorMessage(error),
        });
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }

    loadChats();

    return () => {
      mounted = false;
    };
  }, [location.pathname, showToast]);

  async function handleDelete(chatId) {
    try {
      setDeletingId(chatId);
      await deleteChat(chatId);
      setChats((current) => current.filter((chat) => chat.id !== chatId));

      if (chatId === activeChatId) {
        navigate("/");
      }

      showToast({
        variant: "success",
        title: "Chat deleted",
      });
    } catch (error) {
      showToast({
        variant: "error",
        title: "Delete failed",
        description: getErrorMessage(error),
      });
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <aside className="hidden w-[320px] border-r border-slate-200/80 bg-slate-950 text-slate-100 lg:flex lg:flex-col">
      <div className="border-b border-slate-800 p-5">
        <div className="flex items-center gap-3">
          <div className="rounded-2xl bg-white/10 p-3">
            <Database className="h-5 w-5 text-emerald-400" />
          </div>
          <div>
            <p className="text-lg font-semibold">Querify</p>
            <p className="text-sm text-slate-400">Natural language to PostgreSQL</p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => navigate("/")}
          className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-slate-700 bg-slate-900 px-4 py-3 text-sm font-medium text-slate-100 transition hover:border-indigo-500 hover:bg-slate-800"
        >
          <Plus className="h-4 w-4" />
          New Chat
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        <div className="mb-4 flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
            Chat History
          </p>
        </div>

        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="animate-pulse rounded-2xl border border-slate-800 bg-slate-900 p-4">
                <div className="h-4 w-2/3 rounded bg-slate-700" />
                <div className="mt-3 h-3 w-1/3 rounded bg-slate-800" />
              </div>
            ))}
          </div>
        ) : (
          <AnimatePresence>
            <div className="space-y-3">
              {chats.map((chat) => (
                <motion.div
                  key={chat.id}
                  layout
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, x: -10 }}
                  className={`group rounded-2xl border p-4 transition ${
                    activeChatId === chat.id
                      ? "border-indigo-500 bg-slate-900 shadow-soft"
                      : "border-slate-800 bg-slate-950/70 hover:border-slate-700"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 rounded-xl bg-white/5 p-2">
                      <MessageSquareMore className="h-4 w-4 text-slate-300" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <Link
                        to={`/chat/${chat.id}`}
                        className="block text-sm font-semibold text-slate-100"
                      >
                        {chat.title}
                      </Link>
                      <p className="mt-1 text-xs text-slate-500">
                        Created {formatDate(chat.created_at)}
                      </p>
                    </div>
                    <button
                      type="button"
                      disabled={deletingId === chat.id}
                      onClick={() => handleDelete(chat.id)}
                      className="rounded-full p-2 text-slate-500 transition hover:bg-white/5 hover:text-rose-400"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </motion.div>
              ))}

              {!chats.length ? (
                <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-900/70 p-5 text-sm text-slate-400">
                  No chats yet. Start a fresh database connection to begin.
                </div>
              ) : null}
            </div>
          </AnimatePresence>
        )}
      </div>
    </aside>
  );
}
