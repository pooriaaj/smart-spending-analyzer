import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from "react-router-dom";
import { Suspense, lazy, useEffect, useState } from "react";
import {
  AppShell,
  Box,
  Burger,
  Button,
  Divider,
  Group,
  NavLink,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import {
  IconBuildingBank,
  IconChartPie,
  IconCloudUpload,
  IconLayoutDashboard,
  IconReceipt2,
  IconSettings,
  IconSparkles,
  IconTarget,
} from "@tabler/icons-react";
import ThemeToggle from "./components/ThemeToggle";
import PageSkeleton from "./components/PageSkeleton";
import { LanguageProvider, useLanguage } from "./i18n/LanguageContext";
import api from "./services/api";

const LoginPage = lazy(() => import("./pages/LoginPage"));
const RegisterPage = lazy(() => import("./pages/RegisterPage"));
const TransactionsPage = lazy(() => import("./pages/TransactionsPage"));
const AnalyticsPage = lazy(() => import("./pages/AnalyticsPage"));
const AssistantPage = lazy(() => import("./pages/AssistantPage"));
const ProfilePage = lazy(() => import("./pages/ProfilePage"));
const AccountsPage = lazy(() => import("./pages/AccountsPage"));
const ForgotPasswordPage = lazy(() => import("./pages/ForgotPasswordPage"));
const ResetPasswordPage = lazy(() => import("./pages/ResetPasswordPage"));
const ImportPage = lazy(() => import("./pages/ImportPage"));
const BudgetsPage = lazy(() => import("./pages/BudgetsPage"));
const NotFoundPage = lazy(() => import("./pages/NotFoundPage"));

const APP_NAV_ITEMS = [
  { labelKey: "common.analytics", path: "/analytics", matchPaths: ["/analytics", "/dashboard"], icon: IconLayoutDashboard },
  { labelKey: "common.smartImport", path: "/import", matchPaths: ["/import"], icon: IconCloudUpload },
  { labelKey: "common.transactions", path: "/transactions", matchPaths: ["/transactions"], icon: IconReceipt2 },
  { labelKey: "common.budgets", path: "/budgets", matchPaths: ["/budgets", "/simulator"], icon: IconTarget },
  { labelKey: "common.assistant", path: "/assistant", matchPaths: ["/assistant"], icon: IconSparkles },
  { labelKey: "common.accounts", path: "/accounts", matchPaths: ["/accounts"], icon: IconBuildingBank },
  { labelKey: "common.profileSettings", path: "/profile", matchPaths: ["/profile"], icon: IconSettings },
];

function ProtectedRoute({ children }) {
  const [authState, setAuthState] = useState("checking");

  useEffect(() => {
    let active = true;

    api
      .get("/users/me")
      .then(() => {
        if (active) setAuthState("authenticated");
      })
      .catch(() => {
        if (active) setAuthState("guest");
      });

    return () => {
      active = false;
    };
  }, []);

  if (authState === "checking") return <RouteLoader />;
  return authState === "authenticated" ? children : <Navigate to="/" replace />;
}

function RouteLoader() {
  return <PageSkeleton />;
}

function PublicHomeRoute({ theme, onThemeToggle }) {
  const [authState, setAuthState] = useState("checking");

  useEffect(() => {
    let active = true;

    api
      .get("/users/me")
      .then(() => {
        if (active) setAuthState("authenticated");
      })
      .catch(() => {
        if (active) setAuthState("guest");
      });

    return () => {
      active = false;
    };
  }, []);

  if (authState === "checking") return <RouteLoader />;
  return authState === "authenticated"
    ? <Navigate to="/analytics" replace />
    : <LoginPage theme={theme} onThemeToggle={onThemeToggle} />;
}

function AuthenticatedLayout({ children, theme, onThemeToggle }) {
  const [opened, { toggle, close }] = useDisclosure(false);
  const { t } = useLanguage();
  const navigate = useNavigate();
  const location = useLocation();

  const handleNavigate = (path) => {
    close();
    navigate(path);
  };

  const handleLogout = async () => {
    await api.post("/auth/logout").catch(() => {});
    close();
    navigate("/", { replace: true });
  };

  const activeItem = APP_NAV_ITEMS.find((item) =>
    item.matchPaths.some((path) => location.pathname === path)
  );

  useEffect(() => {
    const pageLabel = activeItem ? t(activeItem.labelKey) : t("common.dashboard");
    document.title = `${pageLabel} — ${t("common.appName")}`;
  }, [activeItem, t]);

  return (
    <AppShell
      className="app-shell"
      header={{ height: 68 }}
      navbar={{
        width: 286,
        breakpoint: "sm",
        collapsed: { mobile: !opened },
      }}
      padding={0}
    >
      <AppShell.Header className="app-shell-header">
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap" className="app-shell-brand-row">
            <Burger
              opened={opened}
              onClick={toggle}
              hiddenFrom="sm"
              size="sm"
              aria-label={t("common.appMenu")}
            />
            <Box className="app-shell-logo" aria-hidden="true">
              <IconChartPie size={22} stroke={1.5} />
            </Box>
            <Box className="app-shell-brand-copy">
              <Title order={2} size="h4">{t("common.appName")}</Title>
              <Text size="xs" c="dimmed">
                {activeItem ? t(activeItem.labelKey) : t("common.dashboard")}
              </Text>
            </Box>
          </Group>

          <Group gap="sm" wrap="nowrap" className="app-shell-header-actions">
            <ThemeToggle
              theme={theme}
              onToggle={onThemeToggle}
            />
            <Button
              type="button"
              color="dark"
              radius="md"
              variant="filled"
              visibleFrom="sm"
              onClick={handleLogout}
            >
              {t("common.logout")}
            </Button>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar className="app-shell-navbar" p="md">
        <Stack h="100%" justify="space-between" gap={0}>
          <Stack gap="md">
            <Box className="app-shell-nav-brand">
              <Group gap="xs" align="center" mb={4}>
                <Box className="app-shell-nav-logo">
                  <IconChartPie size={18} stroke={1.5} />
                </Box>
                <Text className="app-shell-nav-kicker">{t("common.appName")}</Text>
              </Group>
              <Title order={2} size="h3">{t("common.dashboard")}</Title>
            </Box>

            <Divider />

            <Stack gap={4}>
              {APP_NAV_ITEMS.map((item) => (
                <NavLink
                  key={item.path}
                  className="app-shell-nav-link"
                  active={item.matchPaths.some((path) => location.pathname === path)}
                  label={t(item.labelKey)}
                  leftSection={<item.icon size={17} stroke={1.6} />}
                  onClick={() => handleNavigate(item.path)}
                  variant="light"
                />
              ))}
            </Stack>
          </Stack>

          <Stack gap="sm" mt="md">
            <Divider />
            <Button
              type="button"
              radius="md"
              color="dark"
              variant="subtle"
              fullWidth
              onClick={handleLogout}
            >
              {t("common.logout")}
            </Button>
          </Stack>
        </Stack>
      </AppShell.Navbar>

      <AppShell.Main className="app-shell-main">
        {children}
        <Box component="footer" className="app-legal-footer">
          <Text size="xs" c="dimmed">
            {t("common.legalFooter")}
          </Text>
        </Box>
      </AppShell.Main>
    </AppShell>
  );
}

function AppRoutes() {
  const [theme, setTheme] = useState(localStorage.getItem("theme") || "light");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  const toggleTheme = () => setTheme((prev) => (prev === "light" ? "dark" : "light"));
  const protectedPage = (page) => (
    <ProtectedRoute>
      <AuthenticatedLayout theme={theme} onThemeToggle={toggleTheme}>
        {page}
      </AuthenticatedLayout>
    </ProtectedRoute>
  );

  return (
    <BrowserRouter>
      <Suspense fallback={<RouteLoader />}>
        <Routes>
          <Route path="/" element={<PublicHomeRoute theme={theme} onThemeToggle={toggleTheme} />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />

          <Route path="/dashboard" element={<ProtectedRoute><Navigate to="/analytics" replace /></ProtectedRoute>} />
          <Route path="/transactions" element={protectedPage(<TransactionsPage />)} />
          <Route path="/analytics" element={protectedPage(<AnalyticsPage />)} />
          <Route path="/assistant" element={protectedPage(<AssistantPage />)} />
          <Route path="/profile" element={protectedPage(<ProfilePage />)} />
          <Route path="/accounts" element={protectedPage(<AccountsPage />)} />
          <Route path="/import" element={protectedPage(<ImportPage />)} />
          <Route path="/money-map" element={<ProtectedRoute><Navigate to="/analytics" replace /></ProtectedRoute>} />
          <Route path="/budgets" element={protectedPage(<BudgetsPage />)} />
          <Route path="/simulator" element={<ProtectedRoute><Navigate to="/budgets" replace /></ProtectedRoute>} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}

function App() {
  return (
    <LanguageProvider>
      <AppRoutes />
    </LanguageProvider>
  );
}

export default App;
