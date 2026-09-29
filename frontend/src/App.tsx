import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/layout/Layout";
import { Applications } from "./pages/Applications";
import { CV } from "./pages/CV";
import { Dashboard } from "./pages/Dashboard";
import { Discarded } from "./pages/Discarded";
import { JobDetail } from "./pages/JobDetail";
import { Jobs } from "./pages/Jobs";
import { NotFound } from "./pages/NotFound";
import { ProfilePage } from "./pages/Profile";
import { Settings } from "./pages/Settings";

// Recharts es pesado: se carga solo al entrar a /analytics.
const Analytics = lazy(() =>
  import("./pages/Analytics").then((m) => ({ default: m.Analytics })),
);

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/jobs" element={<Jobs />} />
        <Route path="/jobs/:id" element={<JobDetail />} />
        <Route path="/discarded" element={<Discarded />} />
        <Route path="/applications" element={<Applications />} />
        <Route path="/cv" element={<CV />} />
        <Route
          path="/analytics"
          element={
            <Suspense fallback={<div className="content">Cargando gráficos…</div>}>
              <Analytics />
            </Suspense>
          }
        />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
