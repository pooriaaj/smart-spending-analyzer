import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Suspense, lazy, useEffect, useState } from "react";
import ThemeToggle from "./components/ThemeToggle";

const LoginPage = lazy(() => import("./pages/LoginPage"));
const RegisterPage = lazy(() => import("./pages/RegisterPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const TransactionsPage = lazy(() => import("./pages/TransactionsPage"));
const AnalyticsPage = lazy(() => import("./pages/AnalyticsPage"));
const AssistantPage = lazy(() => import("./pages/AssistantPage"));
const ProfilePage = lazy(() => import("./pages/ProfilePage"));
const ForgotPasswordPage = lazy(() => import("./pages/ForgotPasswordPage"));
const ResetPasswordPage = lazy(() => import("./pages/ResetPasswordPage"));
const AccountsPage = lazy(() => import("./pages/AccountsPage"));
const ImportPage = lazy(() => import("./pages/ImportPage"));
const BudgetsPage = lazy(() => import("./pages/BudgetsPage"));
const SimulatorPage = lazy(() => import("./pages/SimulatorPage"));

function ProtectedRoute({ children }) {
  const token = localStorage.getItem("token");
  return token ? children : <Navigate to="/" replace />;
}

function RouteLoader() {
  return (
    <div className="page-container dashboard-page">
      <div className="dashboard-wrapper">
        <div className="status-card">
          <h2>Loading page...</h2>
          <p>Preparing the next screen for you.</p>
        </div>
      </div>
    </div>
  );
}

function PublicHomeRoute() {
  const token = localStorage.getItem("token");
  return token ? <Navigate to="/dashboard" replace /> : <LoginPage />;
}

function App() {
  const [theme, setTheme] = useState(localStorage.getItem("theme") || "light");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  return (
    <BrowserRouter>
      <ThemeToggle
        theme={theme}
        onToggle={() => setTheme((prev) => (prev === "light" ? "dark" : "light"))}
      />

      <Suspense fallback={<RouteLoader />}>
        <Routes>
          <Route path="/" element={<PublicHomeRoute />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />

          <Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
          <Route path="/transactions" element={<ProtectedRoute><TransactionsPage /></ProtectedRoute>} />
          <Route path="/analytics" element={<ProtectedRoute><AnalyticsPage /></ProtectedRoute>} />
          <Route path="/assistant" element={<ProtectedRoute><AssistantPage /></ProtectedRoute>} />
          <Route path="/profile" element={<ProtectedRoute><ProfilePage /></ProtectedRoute>} />
          <Route path="/accounts" element={<ProtectedRoute><AccountsPage /></ProtectedRoute>} />
          <Route path="/import" element={<ProtectedRoute><ImportPage /></ProtectedRoute>} />
          <Route path="/budgets" element={<ProtectedRoute><BudgetsPage /></ProtectedRoute>} />
          <Route path="/simulator" element={<ProtectedRoute><SimulatorPage /></ProtectedRoute>} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}

export default App;
