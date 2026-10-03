import { useQuery } from "@tanstack/react-query";

import { authOptions } from "@/api/generated/endpoints";

export function useAuthOptions() {
  return useQuery({ queryKey: ["auth", "options"], queryFn: () => authOptions(), staleTime: 10 * 60_000 });
}
