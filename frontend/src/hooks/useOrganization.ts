import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  createDepartment,
  createHoliday,
  createLocation,
  createShift,
  deleteDepartment,
  deleteHoliday,
  deleteLocation,
  deleteShift,
  listDepartments,
  listHolidays,
  listLocations,
  listShifts,
  updateDepartment,
  updateHoliday,
  updateLocation,
  updateShift,
} from "@/api/generated/endpoints";
import type {
  DepartmentCreate,
  DepartmentUpdate,
  HolidayCreate,
  HolidayUpdate,
  ListHolidaysParams,
  LocationCreate,
  LocationUpdate,
  ShiftCreate,
  ShiftUpdate,
} from "@/api/generated/model";

// Reference lists are small; they are loaded whole (max page size) for selects and settings tabs.
const ALL = { page: 1, page_size: 200 } as const;
const LONG = 5 * 60_000;

export function useLocations(enabled = true) {
  return useQuery({ queryKey: ["locations"], queryFn: () => listLocations(ALL), staleTime: LONG, enabled });
}

export function useDepartments(enabled = true) {
  return useQuery({ queryKey: ["departments"], queryFn: () => listDepartments(ALL), staleTime: LONG, enabled });
}

export function useShifts(enabled = true) {
  return useQuery({ queryKey: ["shifts"], queryFn: () => listShifts(ALL), staleTime: LONG, enabled });
}

export function useHolidays(params: Omit<ListHolidaysParams, "page" | "page_size">) {
  return useQuery({ queryKey: ["holidays", params], queryFn: () => listHolidays({ ...params, ...ALL }) });
}

function useResourceMutations<C, U>(
  key: string,
  label: string,
  api: {
    create: (body: C) => Promise<{ message: string }>;
    update: (id: number, body: U) => Promise<{ message: string }>;
    remove: (id: number) => Promise<unknown>;
  },
) {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: [key] });
  return {
    create: useMutation({
      mutationFn: api.create,
      onSuccess: (result) => {
        toast.success(result.message);
        void refresh();
      },
    }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: number; body: U }) => api.update(id, body),
      onSuccess: (result) => {
        toast.success(result.message);
        void refresh();
      },
    }),
    remove: useMutation({
      mutationFn: api.remove,
      onSuccess: () => {
        toast.success(`${label} deleted.`);
        void refresh();
      },
    }),
  };
}

export const useLocationMutations = () =>
  useResourceMutations<LocationCreate, LocationUpdate>("locations", "Location", {
    create: createLocation,
    update: updateLocation,
    remove: deleteLocation,
  });

export const useDepartmentMutations = () =>
  useResourceMutations<DepartmentCreate, DepartmentUpdate>("departments", "Department", {
    create: createDepartment,
    update: updateDepartment,
    remove: deleteDepartment,
  });

export const useShiftMutations = () =>
  useResourceMutations<ShiftCreate, ShiftUpdate>("shifts", "Shift", {
    create: createShift,
    update: updateShift,
    remove: deleteShift,
  });

export const useHolidayMutations = () =>
  useResourceMutations<HolidayCreate, HolidayUpdate>("holidays", "Holiday", {
    create: createHoliday,
    update: updateHoliday,
    remove: deleteHoliday,
  });
