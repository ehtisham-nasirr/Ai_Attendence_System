import { useEffect, useMemo, useState, type ReactNode } from "react";

import { LocationFilterContext } from "@/hooks/useLocationFilter";

const STORAGE_KEY = "facetrack.location";

export function LocationFilterProvider({ children }: { children: ReactNode }) {
  const [locationId, setLocationId] = useState<number | null>(() => {
    const stored = Number(localStorage.getItem(STORAGE_KEY));
    return Number.isInteger(stored) && stored > 0 ? stored : null;
  });
  useEffect(() => {
    if (locationId === null) localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, String(locationId));
  }, [locationId]);
  const value = useMemo(() => ({ locationId, setLocationId }), [locationId]);
  return <LocationFilterContext.Provider value={value}>{children}</LocationFilterContext.Provider>;
}
