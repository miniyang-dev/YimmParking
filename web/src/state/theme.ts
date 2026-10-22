import { useCallback, useEffect, useState } from "react";
import { nextTheme, parseTheme, themeColor, type Theme } from "../domain/theme";

const STORAGE_KEY = "yimm.theme";

function stored(): Theme {
  try {
    return parseTheme(window.localStorage.getItem(STORAGE_KEY));
  } catch {
    return "light";
  }
}

function systemPrefersDark(): boolean {
  return (
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
  );
}

export function useTheme(): { theme: Theme; cycle: () => void } {
  const [theme, setTheme] = useState<Theme>(stored);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    const paint = () =>
      document
        .querySelector('meta[name="theme-color"]')
        ?.setAttribute("content", themeColor(theme, systemPrefersDark()));
    paint();
    // "Auto" follows the system: repaint the browser chrome when the system switches.
    if (theme !== "auto" || typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    query.addEventListener("change", paint);
    return () => query.removeEventListener("change", paint);
  }, [theme]);

  const cycle = useCallback(() => {
    setTheme((current) => {
      const next = nextTheme(current);
      try {
        window.localStorage.setItem(STORAGE_KEY, next);
      } catch {
        /* the choice still applies for this visit */
      }
      return next;
    });
  }, []);

  return { theme, cycle };
}
