import { Navigate, Outlet, useLocation } from "react-router-dom";
import type { Role } from "../lib/types";
import { useAuth } from "./AuthContext";

/** Wrap routes that need a logged-in user. `roles` is a UX convenience only: the server is the real gate. */
export function ProtectedRoute({ roles }: { roles?: Role[] }) {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/" replace />;
  return <Outlet />;
}