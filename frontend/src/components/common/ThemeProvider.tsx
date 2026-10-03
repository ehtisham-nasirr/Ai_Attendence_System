import { useEffect, useMemo, useState, type ReactNode } from "react";

import { ThemeContext, type ThemeChoice } from "@/hooks/useTheme";

const STORAGE_KEY = "facetrack.theme";

function systemPrefersDark(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches === true;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [choice, setChoice] = useState<ThemeChoice>(
    () => (localStorage.getItem(STORAGE_KEY) as ThemeChoice | null) ?? "system",
  );
  const [systemDark, setSystemDark] = useState(systemPrefersDark);

  useEffect(() => {
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!media) return;
    const listener = (event: MediaQueryListEvent) => setSystemDark(event.matches);
    media.addEventListener("change", listener);
    return () => media.removeEventListener("change", listener);
  }, []);

  const theme = choice === "system" ? (systemDark ? "dark" : "light") : choice;

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem(STORAGE_KEY, choice);
  }, [theme, choice]);

  const value = useMemo(() => ({ choice, theme, setChoice }), [choice, theme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
