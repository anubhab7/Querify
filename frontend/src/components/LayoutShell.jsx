import { useEffect, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { LogOut, Plus } from "lucide-react";

import Sidebar from "./Sidebar";
import Breadcrumbs from "./Breadcrumbs";
import { useAuth } from "../hooks/useAuth";

export default function LayoutShell() {
  const { logout, user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    return localStorage.getItem("querify_sidebar_collapsed") === "true";
  });
  const activeChatId = location.pathname.startsWith("/chat/")
    ? location.pathname.split("/")[2]
    : null;

  useEffect(() => {
    localStorage.setItem("querify_sidebar_collapsed", String(sidebarCollapsed));
  }, [sidebarCollapsed]);

  const onLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="flex min-h-screen bg-brand-background text-slate-900">
      <Sidebar
        activeChatId={activeChatId}
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((current) => !current)}
      />
      <div
        className={`flex min-h-screen flex-1 flex-col transition-[padding] duration-300 ${
          sidebarCollapsed ? "lg:pl-20" : "lg:pl-56"
        }`}
      >
        <header className="sticky top-0 z-20 border-b border-slate-200/70 bg-white/80 backdrop-blur-xl">
          <div className="flex flex-col gap-4 px-6 py-5 md:flex-row md:items-center md:justify-between">
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-indigo-600">
                Querify Workspace
              </p>
              <Breadcrumbs pathname={location.pathname} />
            </div>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => navigate("/")}
                className="inline-flex items-center gap-2 rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-indigo-300 hover:text-indigo-700"
              >
                <Plus className="h-4 w-4" />
                New Chat
              </button>
              <div className="hidden rounded-full border border-slate-200 bg-slate-50 px-4 py-2 text-sm text-slate-600 sm:block">
                {user?.email}
              </div>
              <button
                type="button"
                onClick={onLogout}
                className="inline-flex items-center gap-2 rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-rose-300 hover:text-rose-600"
              >
                <LogOut className="h-4 w-4" />
                Logout
              </button>
            </div>
          </div>
        </header>
        <main className="flex-1 px-4 py-5 md:px-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
