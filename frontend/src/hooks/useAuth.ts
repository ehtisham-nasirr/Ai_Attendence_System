import { createContext, useContext } from "react";

import type { LoginRequest, UserProfile } from "@/api/generated/model";
import type { PermissionName } from "@/lib/permissions";

export interface AuthState {
  status: "loading" | "authenticated" | "anonymous";
  user: UserProfile | null;
  /** Timezone all times are shown in (setting general.timezone). */
  timezone: string;
  login: (credentials: LoginRequest) => Promise<UserProfile>;
  logout: () => Promise<void>;
  can: (permission: PermissionName) => boolean;
}

export const ME_KEY = ["auth", "me"] as const;

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}

/** Shorthand for the display timezone. */
export function useTimezone(): string {
  return useAuth().timezone;
}
