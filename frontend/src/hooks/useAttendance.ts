import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  approveCorrection,
  correctAttendance,
  createManualEntry,
  listAttendance,
  listCorrections,
  monthlyRegister,
  rejectCorrection,
} from "@/api/generated/endpoints";
import type {
  CorrectionCreate,
  ListAttendanceParams,
  ListCorrectionsParams,
  ManualAttendanceCreate,
  MonthlyRegisterParams,
} from "@/api/generated/model";
import { fetchAllPages } from "@/lib/query";

export function useAttendance(params: ListAttendanceParams, enabled = true) {
  return useQuery({
    queryKey: ["attendance", "list", params],
    queryFn: () => listAttendance(params),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function exportAttendance(params: ListAttendanceParams) {
  return fetchAllPages((page, page_size) => listAttendance({ ...params, page, page_size }));
}

export function useMonthlyRegister(params: MonthlyRegisterParams) {
  return useQuery({
    queryKey: ["attendance", "register", params],
    queryFn: () => monthlyRegister(params),
    placeholderData: keepPreviousData,
  });
}

export function exportRegister(params: MonthlyRegisterParams) {
  return fetchAllPages((page, page_size) => monthlyRegister({ ...params, page, page_size }));
}

export function useAttendanceMutations() {
  const queryClient = useQueryClient();
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["attendance"] });
    void queryClient.invalidateQueries({ queryKey: ["corrections"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };
  return {
    correct: useMutation({
      mutationFn: ({ dayId, body }: { dayId: number; body: CorrectionCreate }) => correctAttendance(dayId, body),
      onSuccess: (result) => {
        toast.success(result.message);
        refresh();
      },
    }),
    createManual: useMutation({
      mutationFn: (body: ManualAttendanceCreate) => createManualEntry(body),
      onSuccess: (result) => {
        toast.success(result.message);
        refresh();
      },
    }),
  };
}

export function useCorrections(params: ListCorrectionsParams) {
  return useQuery({
    queryKey: ["corrections", params],
    queryFn: () => listCorrections(params),
    placeholderData: keepPreviousData,
  });
}

export function useCorrectionDecision() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, approve, comment }: { id: number; approve: boolean; comment: string | null }) =>
      approve ? approveCorrection(id, { comment }) : rejectCorrection(id, { comment }),
    onSuccess: (result) => {
      toast.success(result.message);
      void queryClient.invalidateQueries({ queryKey: ["corrections"] });
      void queryClient.invalidateQueries({ queryKey: ["attendance"] });
    },
  });
}
