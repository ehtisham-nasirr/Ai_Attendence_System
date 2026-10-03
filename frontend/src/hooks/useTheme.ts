import { createContext, useContext } from "react";

export type ThemeChoice = "light" | "dark" | "system";

export interface ThemeState {
  choice: ThemeChoice;
  /** The theme actually applied (system resolved). */
  theme: "light" | "dark";
  setChoice: (choice: ThemeChoice) => void;
}

export const ThemeContext = createContext<ThemeState>({ choice: "system", theme: "light", setChoice: () => {} });

export function useTheme(): ThemeState {
  return useContext(ThemeContext);
}
