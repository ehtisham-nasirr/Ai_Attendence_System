import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { createUser, deleteUser, listUsers, updateUser } from "@/api/generated/endpoints";
import type { ListUsersParams, UserCreate, UserUpdate } from "@/api/generated/model";

export function useUsers(params: ListUsersParams, enabled = true) {
  return useQuery({
    queryKey: ["users", params],
    queryFn: () => listUsers(params),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useUserMutations() {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["users"] });
  return {
    create: useMutation({
      mutationFn: (body: UserCreate) => createUser(body),
      onSuccess: (result) => {
        toast.success(result.message);
        void refresh();
      },
    }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: number; body: UserUpdate }) => updateUser(id, body),
      onSuccess: (result) => {
        toast.success(result.message);
        void refresh();
      },
    }),
    remove: useMutation({
      mutationFn: (id: number) => deleteUser(id),
      onSuccess: () => {
        toast.success("User deleted.");
        void refresh();
      },
    }),
  };
}
