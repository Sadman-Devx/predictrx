import { Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { AppShell } from "./components/layout/AppShell";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import MedicationEntry from "./pages/MedicationEntry";
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
          {/* TODO (frontend dev): replace each placeholder, following roadmap.md */}
          <Route path="patients" element={<Placeholder titleKey="patients.title" />} />
          <Route path="medications" element={<MedicationEntry />} />
          <Route path="scan" element={<Placeholder titleKey="scan.title" hintKey="scan.hint" />} />
          <Route path="review" element={<Placeholder titleKey="review.title" />} />
          <Route path="analysis" element={<Placeholder titleKey="analysis.title" />} />
          <Route path="twin" element={<Placeholder titleKey="twin.title" hintKey="twin.note" />} />
          <Route path="family" element={<Placeholder titleKey="family.title" />} />
        </Route>
      </Route>
    </Routes>
  );
}