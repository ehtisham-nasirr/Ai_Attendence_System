import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { createApiClient, listApiClients, pushPayroll, revokeApiClient, runHrSync, updateApiClient } from "@/api/generated/endpoints";

export function useApiClients(enabled = true) {
  return useQuery({ queryKey: ["api-clients"], queryFn: () => listApiClients(), enabled });
}

export function useApiClientMutations() {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["api-clients"] });
  return {
    create: useMutation({
      mutationFn: (name: string) => createApiClient({ name, scopes: ["attendance:read"] }),
      onSuccess: () => void refresh(),
    }),
    toggle: useMutation({
      mutationFn: ({ id, active }: { id: number; active: boolean }) => updateApiClient(id, { is_active: active }),
      onSuccess: (result) => {
        toast.success(result.message);
        void refresh();
      },
    }),
    revoke: useMutation({
      mutationFn: (id: number) => revokeApiClient(id),
      onSuccess: () => {
        toast.success("API key revoked.");
        void refresh();
      },
    }),
  };
}

export function useIntegrationActions() {
  return {
    push: useMutation({
      mutationFn: (date: string | null) => pushPayroll(date ? { date } : undefined),
      onSuccess: (result) => toast.success(result.message),
    }),
    sync: useMutation({
      mutationFn: () => runHrSync(),
      onSuccess: (result) => toast.success(result.message),
    }),
  };
}
