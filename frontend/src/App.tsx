import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider, useAuth } from "@/hooks/useAuth";
import { ThemeProvider, useTheme } from "@/hooks/useTheme";
import { LoadingState } from "@/components/common";
import { LogoMark } from "@/components/Logo";
import AppLayout from "@/layouts/AppLayout";
import Landing from "@/pages/Landing";
import { ForgotPassword, Login, ResetPassword, Signup } from "@/pages/AuthPages";
import NotFound from "@/pages/NotFound";

// Module pages are code-split so the landing page and login load fast on mobile.
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const DataManagement = lazy(() => import("@/pages/DataManagement"));
const DatasetDetail = lazy(() => import("@/pages/DatasetDetail"));
const Eda = lazy(() => import("@/pages/Eda"));
const Customers = lazy(() => import("@/pages/Customers"));
const Forecasting = lazy(() => import("@/pages/Forecasting"));
const Inventory = lazy(() => import("@/pages/Inventory"));
const Insights = lazy(() => import("@/pages/Insights"));
const Assistant = lazy(() => import("@/pages/Assistant"));
const Reports = lazy(() => import("@/pages/Reports"));
const Profile = lazy(() => import("@/pages/Profile"));
const AdminUsers = lazy(() => import("@/pages/admin/Users"));
const AdminSettings = lazy(() => import("@/pages/admin/Settings"));

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 30_000 } },
});

function FullScreenLoader() {
  return (
    <div className="flex min-h-[100dvh] items-center justify-center">
      <LogoMark className="h-12 w-12 animate-pulse" />
    </div>
  );
}

function RequireAuth({ children, admin = false }: { children: ReactNode; admin?: boolean }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <FullScreenLoader />;
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  if (admin && user.role !== "admin") return <Navigate to="/app/dashboard" replace />;
  return <>{children}</>;
}

function GuestOnly({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <FullScreenLoader />;
  return user ? <Navigate to="/app/dashboard" replace /> : <>{children}</>;
}

function ThemedToaster() {
  const { resolved } = useTheme();
  return <Toaster richColors closeButton position="top-right" theme={resolved} />;
}

const page = (el: ReactNode) => <Suspense fallback={<LoadingState rows={4} />}>{el}</Suspense>;

export default function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <TooltipProvider delayDuration={200}>
            <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
              <Routes>
                <Route path="/" element={<Landing />} />
                <Route path="/login" element={<GuestOnly><Login /></GuestOnly>} />
                <Route path="/signup" element={<GuestOnly><Signup /></GuestOnly>} />
                <Route path="/forgot-password" element={<ForgotPassword />} />
                <Route path="/reset-password" element={<ResetPassword />} />
                <Route path="/app" element={<RequireAuth><AppLayout /></RequireAuth>}>
                  <Route index element={<Navigate to="dashboard" replace />} />
                  <Route path="dashboard" element={page(<Dashboard />)} />
                  <Route path="data" element={page(<DataManagement />)} />
                  <Route path="data/:id" element={page(<DatasetDetail />)} />
                  <Route path="eda" element={page(<Eda />)} />
                  <Route path="customers" element={page(<Customers />)} />
                  <Route path="forecasting" element={page(<Forecasting />)} />
                  <Route path="inventory" element={page(<Inventory />)} />
                  <Route path="insights" element={page(<Insights />)} />
                  <Route path="assistant" element={page(<Assistant />)} />
                  <Route path="reports" element={page(<Reports />)} />
                  <Route path="profile" element={page(<Profile />)} />
                  <Route path="admin/users" element={<RequireAuth admin>{page(<AdminUsers />)}</RequireAuth>} />
                  <Route path="admin/settings" element={<RequireAuth admin>{page(<AdminSettings />)}</RequireAuth>} />
                </Route>
                <Route path="*" element={<NotFound />} />
              </Routes>
            </BrowserRouter>
            <ThemedToaster />
          </TooltipProvider>
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
