import { ChevronRight } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

function formatSegment(segment) {
  if (segment === "chat") {
    return "Chat";
  }
  return segment
    .split("-")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export default function Breadcrumbs({ pathname }) {
  const params = useParams();
  const [titleVersion, setTitleVersion] = useState(0);

  useEffect(() => {
    function refreshTitles() {
      setTitleVersion((current) => current + 1);
    }

    window.addEventListener("querify:chat-titles", refreshTitles);
    window.addEventListener("querify:report-titles", refreshTitles);
    return () => {
      window.removeEventListener("querify:chat-titles", refreshTitles);
      window.removeEventListener("querify:report-titles", refreshTitles);
    };
  }, []);

  const segments = useMemo(() => {
    const rawSegments = pathname.split("/").filter(Boolean);
    const savedTitles = JSON.parse(localStorage.getItem("querify_chat_titles") || "{}");
    const savedReportTitles = JSON.parse(localStorage.getItem("querify_report_titles") || "{}");

    if (rawSegments.length === 0) {
      return [{ label: "Home", to: "/" }];
    }

    const crumbs = [{ label: "Home", to: "/" }];
    let current = "";
    rawSegments.forEach((segment) => {
      current += `/${segment}`;
      
      let label = formatSegment(segment);
      if (segment === params.chatId) {
        label = savedTitles[segment] || params.chatId;
      } else if (segment === params.id) {
        label = savedReportTitles[segment] || params.id;
      }

      crumbs.push({
        label,
        to: current,
      });
    });
    return crumbs;
  }, [params.chatId, params.id, pathname, titleVersion]);

  return (
    <nav className="flex flex-wrap items-center gap-2 text-sm text-slate-500">
      {segments.map((segment, index) => (
        <div key={segment.to} className="flex items-center gap-2">
          {index > 0 ? <ChevronRight className="h-4 w-4 text-slate-300" /> : null}
          {index === segments.length - 1 ? (
            <span className="font-medium text-slate-900">{segment.label}</span>
          ) : (
            <Link
              to={segment.to}
              className="transition hover:text-indigo-600"
            >
              {segment.label}
            </Link>
          )}
        </div>
      ))}
    </nav>
  );
}
