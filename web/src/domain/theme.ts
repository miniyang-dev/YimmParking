export type Theme = "light" | "dark" | "auto";

export const THEME_ORDER: readonly Theme[] = ["light", "dark", "auto"];

/** Anything unrecognised (including nothing saved) falls back to light. */
export function parseTheme(raw: string | null | undefined): Theme {
  return raw === "dark" || raw === "auto" ? raw : "light";
}

export function nextTheme(current: Theme): Theme {
  const index = THEME_ORDER.indexOf(current);
  return THEME_ORDER[(index + 1) % THEME_ORDER.length] as Theme;
}

/** The colour of the browser's own chrome (address bar) on mobile. */
export function themeColor(theme: Theme, systemPrefersDark: boolean): string {
  const dark = theme === "dark" || (theme === "auto" && systemPrefersDark);
  return dark ? "#14171a" : "#ffffff";
}
