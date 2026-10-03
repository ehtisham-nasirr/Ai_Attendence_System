import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/hooks/useAuth";
import type { PermissionName } from "@/lib/permissions";
import { visibleNavItems } from "@/routes/navigation";
import { ForbiddenPage } from "@/pages/errors/ForbiddenPage";

function FullPageSkeleton() {
  return (
    <div className="flex min-h-screen items-center justify-center" aria-busy="true" aria-label="Loading">
      <Skeleton className="h-8 w-48" />
    </div>
  );
}

/** Signed-in users only; otherwise to /login with a return path. */
export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();
  if (status === "loading") return <FullPageSkeleton />;
  if (status === "anonymous") {
    const next = encodeURIComponent(`${location.pathname}${location.search}`);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <>{children}</>;
}

/** Role guard: hides screens the user's role may not use (the API enforces it as well). */
export function RequirePermission({ anyOf, children }: { anyOf: PermissionName[]; children: ReactNode }) {
  const { can } = useAuth();
  return anyOf.some(can) ? <>{children}</> : <ForbiddenPage />;
}

export function RequireEmployee({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  return user?.employee_id ? <>{children}</> : <ForbiddenPage />;
}

/** `/` goes to the first screen the user may open. */
export function HomeRedirect() {
  const { can, user } = useAuth();
  const first = visibleNavItems(can, user?.role === "employee")[0];
  return <Navigate to={first?.to ?? "/me"} replace />;
}
