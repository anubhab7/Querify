import { Route, Routes } from "react-router-dom";

import { ProtectedRoute, PublicOnlyRoute } from "./components/ProtectedRoute";
import LayoutShell from "./components/LayoutShell";
import ChatPage from "./pages/ChatPage";
import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import NotFoundPage from "./pages/NotFoundPage";
import RegisterPage from "./pages/RegisterPage";
import ReportsDashboard from "./pages/ReportsDashboard";
import ReportDetail from "./pages/ReportDetail";
import ReportFormat from "./pages/ReportFormat";

export default function App() {
  return (
    <Routes>
      <Route
        path="/login"
        element={
          <PublicOnlyRoute>
            <LoginPage />
          </PublicOnlyRoute>
        }
      />
      <Route
        path="/register"
        element={
          <PublicOnlyRoute>
            <RegisterPage />
          </PublicOnlyRoute>
        }
      />
      <Route
        element={
          <ProtectedRoute>
            <LayoutShell />
          </ProtectedRoute>
        }
      >
        <Route index element={<LandingPage />} />
        <Route path="/chat/:chatId" element={<ChatPage />} />
        <Route path="/reports" element={<ReportsDashboard />} />
        <Route path="/reports/:id" element={<ReportDetail />} />
        <Route path="/reports/:id/format" element={<ReportFormat />} />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
