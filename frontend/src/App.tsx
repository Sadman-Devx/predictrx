import { Route, Routes } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import { Placeholder } from "./pages/Placeholder";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Dashboard />} />
        <Route path="login" element={<Login />} />
        {/* TODO (frontend dev): replace each placeholder, following docs/roadmap.md */}
        <Route path="patients" element={<Placeholder titleKey="patients.title" />} />
        <Route path="scan" element={<Placeholder titleKey="scan.title" hintKey="scan.hint" />} />
        <Route path="review" element={<Placeholder titleKey="review.title" />} />
        <Route path="analysis" element={<Placeholder titleKey="analysis.title" />} />
        <Route path="twin" element={<Placeholder titleKey="twin.title" hintKey="twin.note" />} />
        <Route path="family" element={<Placeholder titleKey="family.title" />} />
      </Route>
    </Routes>
  );
}
