import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-6 text-center">
      <p className="text-sm font-semibold uppercase tracking-[0.3em] text-indigo-600">404</p>
      <h1 className="mt-4 text-4xl font-semibold text-slate-900">Page not found</h1>
      <p className="mt-4 max-w-md text-slate-600">
        The page you requested does not exist in this Querify workspace.
      </p>
      <Link
        to="/"
        className="mt-8 rounded-full bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-indigo-600"
      >
        Return Home
      </Link>
    </div>
  );
}
