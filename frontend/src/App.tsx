import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import ReviewConfirm from "./components/ReviewConfirm";
import { AppShell } from "./components/layout/AppShell";
import AnalysisList from "./pages/AnalysisList";
import AnalysisRun from "./pages/AnalysisRun";
import Dashboard from "./pages/Dashboard";
import Family from "./pages/Family";
import FamilyPatient from "./pages/FamilyPatient";
import Login from "./pages/Login";
import MedicationEntry from "./pages/MedicationEntry";
import NotFound from "./pages/NotFound";
import PatientDetail from "./pages/PatientDetail";
import Patients from "./pages/Patients";
import Profile from "./pages/Profile";
import ResetPassword from "./pages/ResetPassword";
import Scan from "./pages/Scan";
import TwinHome from "./pages/TwinHome";
import VerifyEmail from "./pages/VerifyEmail";
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
      <Route path="verify-email" element={<VerifyEmail />} />

      {/* Everything else needs a session */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route index element={<Home />} />
          {/* Every signed-in role: account details, resend verification, change password. */}
          <Route path="profile" element={<Profile />} />

          {/* Staff screens. A family member who types one of these addresses is sent back to "/" (and from there to /family). */}
          <Route element={<ProtectedRoute roles={STAFF} />}>
            <Route path="patients" element={<Patients />} />
            <Route path="patients/:id" element={<PatientDetail />} />
            <Route path="medications" element={<MedicationEntry />} />
            {/* Day 8: photo upload. The draft list it reads is checked on /review; manual entry stays one click away. */}
            <Route path="scan" element={<Scan />} />
            <Route path="review" element={<ReviewConfirm />} />
            {/* Day 6/7: one run opens at /analysis/:runId; /analysis lists the clinician's past runs (GET /api/analysis/runs/). */}
            <Route path="analysis" element={<AnalysisList />} />
            <Route path="analysis/:runId" element={<AnalysisRun />} />
            {/* Day 10: the What-if simulation is a tab of a finished analysis; /twin lists the finished ones and opens that tab. */}
            <Route path="twin" element={<TwinHome />} />
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