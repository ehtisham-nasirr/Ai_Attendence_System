import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { getSettings, updateSettings } from "@/api/generated/endpoints";

export function useSettings(enabled = true) {
  return useQuery({ queryKey: ["settings"], queryFn: () => getSettings(), enabled });
}

export function useUpdateSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (values: Record<string, unknown>) => updateSettings({ values }),
    onSuccess: (result) => {
      toast.success(result.message);
      queryClient.setQueryData(["settings"], result);
      void queryClient.invalidateQueries({ queryKey: ["auth", "me"] }); // timezone may have changed
    },
  });
}
