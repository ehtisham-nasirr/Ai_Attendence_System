import { createContext, useContext } from "react";

export interface LocationFilterState {
  /** Selected office location, or null for all locations (FR-36). */
  locationId: number | null;
  setLocationId: (id: number | null) => void;
}

export const LocationFilterContext = createContext<LocationFilterState>({ locationId: null, setLocationId: () => {} });

export function useLocationFilter(): LocationFilterState {
  return useContext(LocationFilterContext);
}
