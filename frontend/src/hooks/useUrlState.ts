import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

export type UrlPatch = Record<string, string | number | boolean | null | undefined>;

/**
 * Filters, page and sort live in the URL so views are shareable (standards/08).
 * Changing anything other than `page` resets to page 1.
 */
export function useUrlState() {
  const [params, setParams] = useSearchParams();

  const get = useCallback((key: string): string | null => params.get(key), [params]);

  const getNumber = useCallback(
    (key: string): number | null => {
      const raw = params.get(key);
      if (raw === null || raw === "") return null;
      const value = Number(raw);
      return Number.isFinite(value) ? value : null;
    },
    [params],
  );

  const set = useCallback(
    (patch: UrlPatch) => {
      setParams(
        (previous) => {
          const next = new URLSearchParams(previous);
          for (const [key, value] of Object.entries(patch)) {
            if (value === null || value === undefined || value === "") next.delete(key);
            else next.set(key, String(value));
          }
          if (!("page" in patch)) next.delete("page");
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  const page = getNumber("page") ?? 1;
  const pageSize = getNumber("page_size") ?? 20;
  const sort = get("sort");
  return { params, get, getNumber, set, page, pageSize, sort };
}
