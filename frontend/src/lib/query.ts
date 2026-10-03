import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "@/api/client";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        // Never retry client errors (validation, permission, not found).
        retry: (failureCount, error) =>
          !(error instanceof ApiError && error.status >= 400 && error.status < 500) && failureCount < 2,
      },
      mutations: { retry: false },
    },
  });
}

export interface Page<T> {
  data: T[];
  pagination: { page: number; page_size: number; total: number };
}

/** Fetches every page of a list endpoint (for exports), up to `maxRows`. */
export async function fetchAllPages<T>(
  fetchPage: (page: number, pageSize: number) => Promise<Page<T>>,
  maxRows = 10_000,
  pageSize = 200,
): Promise<T[]> {
  const rows: T[] = [];
  for (let page = 1; ; page += 1) {
    const result = await fetchPage(page, pageSize);
    rows.push(...result.data);
    if (rows.length >= Math.min(result.pagination.total, maxRows) || result.data.length === 0) break;
  }
  return rows.slice(0, maxRows);
}
