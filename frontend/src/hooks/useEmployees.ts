import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  createEmployee,
  createLeave,
  deleteEmployee,
  deleteFace,
  deleteLeave,
  eraseBiometrics,
  getEmployee,
  importEmployees,
  listEmployees,
  listFaces,
  listLeaves,
  updateEmployee,
  uploadFaces,
} from "@/api/generated/endpoints";
import type {
  EmployeeCreate,
  EmployeeUpdate,
  LeaveCreate,
  ListEmployeesParams,
  ListLeavesParams,
} from "@/api/generated/model";
import { fetchAllPages } from "@/lib/query";

export function useEmployees(params: ListEmployeesParams) {
  return useQuery({
    queryKey: ["employees", "list", params],
    queryFn: () => listEmployees(params),
    placeholderData: keepPreviousData,
  });
}

export function exportEmployees(params: ListEmployeesParams) {
  return fetchAllPages((page, page_size) => listEmployees({ ...params, page, page_size }));
}

export function useEmployee(id: number | null) {
  return useQuery({
    queryKey: ["employees", "detail", id],
    queryFn: () => getEmployee(id as number),
    enabled: id !== null,
  });
}

/** Searchable employee picker source (assign unknown face, manual entry). */
export function useEmployeeSearch(search: string, enabled = true) {
  return useQuery({
    queryKey: ["employees", "search", search],
    queryFn: () => listEmployees({ search: search || undefined, status: "active", page: 1, page_size: 20 }),
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useEmployeeMutations() {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["employees"] });
  return {
    create: useMutation({
      mutationFn: (body: EmployeeCreate) => createEmployee(body),
      onSuccess: (result) => {
        toast.success(result.message);
        void refresh();
      },
    }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: number; body: EmployeeUpdate }) => updateEmployee(id, body),
      onSuccess: (result) => {
        toast.success(result.message);
        void refresh();
      },
    }),
    remove: useMutation({
      mutationFn: ({ id, code }: { id: number; code: string }) => deleteEmployee(id, { confirm_employee_code: code }),
      onSuccess: () => {
        toast.success("Employee deleted and biometric data erased.");
        void refresh();
      },
    }),
    eraseBiometrics: useMutation({
      mutationFn: ({ id, code }: { id: number; code: string }) => eraseBiometrics(id, { confirm_employee_code: code }),
      onSuccess: () => {
        toast.success("Biometric data erased. The employee record is kept.");
        void refresh();
        void queryClient.invalidateQueries({ queryKey: ["faces"] });
      },
    }),
  };
}

export function useFaces(employeeId: number) {
  return useQuery({ queryKey: ["faces", employeeId], queryFn: () => listFaces(employeeId) });
}

export function useFaceMutations(employeeId: number) {
  const queryClient = useQueryClient();
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["faces", employeeId] });
    void queryClient.invalidateQueries({ queryKey: ["employees"] });
  };
  return {
    upload: useMutation({
      mutationFn: ({ files, source }: { files: File[]; source: "upload" | "webcam" }) =>
        // The spec types binary parts as strings; the generated function appends them to FormData as-is.
        uploadFaces(employeeId, { photos: files as unknown as string[], source }),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (faceId: number) => deleteFace(employeeId, faceId),
      onSuccess: () => {
        toast.success("Photo removed from the gallery.");
        refresh();
      },
    }),
  };
}

export function useImportEmployees() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ sheet, photosZip }: { sheet: File; photosZip: File | null }) =>
      importEmployees({
        sheet: sheet as unknown as string,
        photos_zip: (photosZip ?? undefined) as unknown as string | undefined,
      }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["employees"] }),
  });
}

export function useLeaves(params: ListLeavesParams) {
  return useQuery({ queryKey: ["leaves", params], queryFn: () => listLeaves(params) });
}

export function useLeaveMutations() {
  const queryClient = useQueryClient();
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["leaves"] });
    void queryClient.invalidateQueries({ queryKey: ["attendance"] });
  };
  return {
    create: useMutation({
      mutationFn: (body: LeaveCreate) => createLeave(body),
      onSuccess: (result) => {
        toast.success(result.message);
        refresh();
      },
    }),
    remove: useMutation({
      mutationFn: (leaveId: number) => deleteLeave(leaveId),
      onSuccess: () => {
        toast.success("Leave removed.");
        refresh();
      },
    }),
  };
}
