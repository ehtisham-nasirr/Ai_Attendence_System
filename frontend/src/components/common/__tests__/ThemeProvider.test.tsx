import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { THEME_STORAGE_KEY, ThemeProvider } from "@/components/common/ThemeProvider";
import { UserMenu } from "@/components/layout/UserMenu";
import { useTheme } from "@/hooks/useTheme";
import { renderWithProviders } from "@/test/render";

function ThemeProbe() {
  const { choice, theme } = useTheme();
  return (
    <p>
      choice={choice} theme={theme}
    </p>
  );
}

const originalMatchMedia = window.matchMedia;

/** Makes the operating system report dark mode, like the owner's Windows laptop. */
function osPrefersDark() {
  window.matchMedia = (query: string) =>
    ({
      matches: query === "(prefers-color-scheme: dark)",
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }) as unknown as MediaQueryList;
}

const isDark = () => document.documentElement.classList.contains("dark");

afterEach(() => {
  window.matchMedia = originalMatchMedia;
  document.documentElement.classList.remove("dark");
});

describe("ThemeProvider (§13 light and dark themes)", () => {
  it("starts on the light theme by default, even when the OS is in dark mode", () => {
    osPrefersDark();
    render(
      <ThemeProvider>
        <ThemeProbe />
      </ThemeProvider>,
    );
    expect(screen.getByText("choice=light theme=light")).toBeInTheDocument();
    expect(isDark()).toBe(false);
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  });

  it("ignores and removes the old 'system' choice stored by earlier builds", () => {
    osPrefersDark();
    localStorage.setItem("facetrack.theme", "system");
    render(
      <ThemeProvider>
        <ThemeProbe />
      </ThemeProvider>,
    );
    expect(screen.getByText("choice=light theme=light")).toBeInTheDocument();
    expect(isDark()).toBe(false);
    expect(localStorage.getItem("facetrack.theme")).toBeNull();
  });

  it("keeps a dark choice the user made", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    render(
      <ThemeProvider>
        <ThemeProbe />
      </ThemeProvider>,
    );
    expect(screen.getByText("choice=dark theme=dark")).toBeInTheDocument();
    expect(isDark()).toBe(true);
  });

  it("follows the OS when the user picks System", () => {
    osPrefersDark();
    localStorage.setItem(THEME_STORAGE_KEY, "system");
    render(
      <ThemeProvider>
        <ThemeProbe />
      </ThemeProvider>,
    );
    expect(screen.getByText("choice=system theme=dark")).toBeInTheDocument();
    expect(isDark()).toBe(true);
  });

  it("falls back to light for an unknown stored value", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "neon");
    render(
      <ThemeProvider>
        <ThemeProbe />
      </ThemeProvider>,
    );
    expect(screen.getByText("choice=light theme=light")).toBeInTheDocument();
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  });

  it("still offers Light, Dark and System in the user menu, and switching applies at once", async () => {
    renderWithProviders(
      <ThemeProvider>
        <UserMenu />
      </ThemeProvider>,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Account menu" }));
    expect(screen.getByRole("menuitemradio", { name: "Light" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("menuitemradio", { name: "System" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("menuitemradio", { name: "Dark" }));
    await waitFor(() => expect(isDark()).toBe(true));
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
  });
});
