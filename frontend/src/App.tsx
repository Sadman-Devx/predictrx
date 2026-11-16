import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import ReviewConfirm from "./components/ReviewConfirm";
import { AppShell } from "./components/layout/AppShell";
import AnalysisRun from "./pages/AnalysisRun";
import Dashboard from "./pages/Dashboard";
import Family from "./pages/Family";
import FamilyPatient from "./pages/FamilyPatient";
import Login from "./pages/Login";
import MedicationEntry from "./pages/MedicationEntry";
import NotFound from "./pages/NotFound";
import PatientDetail from "./pages/PatientDetail";
import Patients from "./pages/Patients";
import { Placeholder } from "./pages/Placeholder";
import ResetPassword from "./pages/ResetPassword";
import Scan from "./pages/Scan";
import type { Role } from "./lib/types";

/** "/" is the staff dashboard; a family member has no dashboard and lands on the shared patients. */
function Home() {
  const { user } = useAuth();
  return user?.role === "family" ? <Navigate to="/family" replace /> : <Dashboard />;
}

const STAFF: Role[] = ["doctor", "pharmacist", "admin"];

export default function App() {
  return (
    <Routes>
      {/* Public: full-screen, no nav */}
      <Route path="login" element={<Login />} />
      <Route path="reset-password" element={<ResetPassword />} />

      {/* Everything else needs a session */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route index element={<Home />} />

          {/* Staff screens. A family member who types one of these addresses is sent back to "/" (and from there to /family). */}
          <Route element={<ProtectedRoute roles={STAFF} />}>
            <Route path="patients" element={<Patients />} />
            <Route path="patients/:id" element={<PatientDetail />} />
            <Route path="medications" element={<MedicationEntry />} />
            {/* Day 8: photo upload. The draft list it reads is checked on /review; manual entry stays one click away. */}
            <Route path="scan" element={<Scan />} />
            <Route path="review" element={<ReviewConfirm />} />
            {/* The analyses list needs a list endpoint that does not exist yet; one run opens at /analysis/:runId (Day 6, results Day 7). */}
            <Route
              path="analysis"
              element={<Placeholder titleKey="analysis.title" hintKey="analysis.list.hint" actionTo="/scan" actionKey="dashboard.cta" />}
            />
            <Route path="analysis/:runId" element={<AnalysisRun />} />
            {/* Day 10: the What-if simulation is a tab of a finished analysis (results screen). This address only explains that. */}
            <Route
              path="twin"
              element={<Placeholder titleKey="twin.title" hintKey="twin.home.hint" actionTo="/scan" actionKey="dashboard.cta" />}
            />
          </Route>

          {/* Day 9: family view (read-only, only for the "family" role). */}
          <Route element={<ProtectedRoute roles={["family"]} />}>
            <Route path="family" element={<Family />} />
            <Route path="family/:patientId" element={<FamilyPatient />} />
          </Route>

          {/* Day 10: any other address gets a clear page with a way back, inside the shell so the menu stays. */}
          <Route path="*" element={<NotFound />} />
        </Route>
      </Route>
    </Routes>
  );
}