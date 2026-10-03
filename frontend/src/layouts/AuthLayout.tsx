import { Outlet } from "react-router-dom";

import { Brand } from "@/components/layout/Brand";

export function AuthLayout() {
  return (
    <div className="bg-muted/40 flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex justify-center">
          <Brand />
        </div>
        <Outlet />
      </div>
    </div>
  );
}
