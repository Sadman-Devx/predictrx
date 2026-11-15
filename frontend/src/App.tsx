import { Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import ReviewConfirm from "./components/ReviewConfirm";
import { AppShell } from "./components/layout/AppShell";
import AnalysisRun from "./pages/AnalysisRun";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import MedicationEntry from "./pages/MedicationEntry";
import PatientDetail from "./pages/PatientDetail";
import Patients from "./pages/Patients";
import { Placeholder } from "./pages/Placeholder";

export default function App() {
  return (
    <Routes>
      {/* Public: full-screen, no nav */}
      <Route path="login" element={<Login />} />

      {/* Everything else needs a session */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route index element={<Dashboard />} />
          <Route path="patients" element={<Patients />} />
          <Route path="patients/:id" element={<PatientDetail />} />
          <Route path="medications" element={<MedicationEntry />} />
          {/* Day 8 builds the scanner. Until then the screen links to manual entry so the flow is never a dead end. */}
          <Route
            path="scan"
            element={<Placeholder titleKey="scan.title" hintKey="scan.hint" actionTo="/medications" actionKey="scan.manual" />}
          />
          <Route path="review" element={<ReviewConfirm />} />
          {/* The analyses list needs a list endpoint that does not exist yet; one run opens at /analysis/:runId (Day 6). */}
          <Route path="analysis" element={<Placeholder titleKey="analysis.title" />} />
          <Route path="analysis/:runId" element={<AnalysisRun />} />
          <Route path="twin" element={<Placeholder titleKey="twin.title" hintKey="twin.note" />} />
          <Route path="family" element={<Placeholder titleKey="family.title" />} />
        </Route>
      </Route>
    </Routes>
  );
}