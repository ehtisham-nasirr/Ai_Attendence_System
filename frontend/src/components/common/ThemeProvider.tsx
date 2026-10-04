import { useEffect, useMemo, useState, type ReactNode } from "react";

import { ThemeContext, type ThemeChoice } from "@/hooks/useTheme";

/**
 * The light theme is the default for everyone. The key carries a version because browsers that used the
 * first portal build already stored "system" under the old key, which showed the dark theme on machines
 * set to dark mode; a new key makes every user start on light once. Dark and System stay selectable.
 */
export const THEME_STORAGE_KEY = "facetrack.theme.v2";
const LEGACY_STORAGE_KEY = "facetrack.theme";
const DEFAULT_CHOICE: ThemeChoice = "light";
const CHOICES: readonly ThemeChoice[] = ["light", "dark", "system"];

function storedChoice(): ThemeChoice {
  const value = localStorage.getItem(THEME_STORAGE_KEY);
  return CHOICES.includes(value as ThemeChoice) ? (value as ThemeChoice) : DEFAULT_CHOICE;
}

function systemPrefersDark(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches === true;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [choice, setChoice] = useState<ThemeChoice>(storedChoice);
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
    localStorage.setItem(THEME_STORAGE_KEY, choice);
    localStorage.removeItem(LEGACY_STORAGE_KEY);
  }, [theme, choice]);

  const value = useMemo(() => ({ choice, theme, setChoice }), [choice, theme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
