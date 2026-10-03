import { useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, type ReactNode } from "react";

import { ApiError, setUnauthorizedHandler } from "@/api/client";
import { login as loginRequest, logout as logoutRequest, me } from "@/api/generated/endpoints";
import type { LoginRequest, UserProfile } from "@/api/generated/model";
import { AuthContext, ME_KEY, type AuthState } from "@/hooks/useAuth";
import { DEFAULT_TIMEZONE } from "@/lib/format";
import type { PermissionName } from "@/lib/permissions";

async function fetchMe(): Promise<UserProfile | null> {
  try {
    return (await me()).data;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

/**
 * Signs the client out locally: the user becomes null first, then every other cached query is dropped.
 * (`queryClient.clear()` would also remove the /auth/me query under its live observer, which then kept
 * showing the old user.)
 */
function forgetSession(queryClient: QueryClient): void {
  queryClient.setQueryData(ME_KEY, null);
  queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== ME_KEY[0] });
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ME_KEY, queryFn: fetchMe, staleTime: 5 * 60_000, retry: false });
  const user = query.data ?? null;

  useEffect(() => {
    // Any 401 from a protected call means the session ended: forget cached data and show sign-in.
    setUnauthorizedHandler(() => forgetSession(queryClient));
    return () => setUnauthorizedHandler(null);
  }, [queryClient]);

  const login = useCallback(
    async (credentials: LoginRequest) => {
      const profile = (await loginRequest(credentials)).data;
      queryClient.setQueryData(ME_KEY, profile);
      return profile;
    },
    [queryClient],
  );

  const logout = useCallback(async () => {
    try {
      await logoutRequest();
    } finally {
      forgetSession(queryClient);
    }
  }, [queryClient]);

  const value = useMemo<AuthState>(() => {
    const permissions = new Set(user?.permissions ?? []);
    return {
      status: query.isPending ? "loading" : user ? "authenticated" : "anonymous",
      user,
      timezone: user?.timezone ?? DEFAULT_TIMEZONE,
      login,
      logout,
      can: (permission: PermissionName) => permissions.has(permission),
    };
  }, [query.isPending, user, login, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
