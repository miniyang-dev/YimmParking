import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Locale } from "../domain/types";
import { STRINGS, type StringKey } from "./strings";

type Vars = Record<string, string | number>;

export function translate(locale: Locale, key: StringKey, vars?: Vars): string {
  let text: string = STRINGS[locale][key];
  if (vars) {
    for (const [name, value] of Object.entries(vars)) {
      text = text.replaceAll(`{${name}}`, String(value));
    }
  }
  return text;
}

interface I18n {
  locale: Locale;
  t: (key: StringKey, vars?: Vars) => string;
  toggle: () => void;
}

const Ctx = createContext<I18n | null>(null);
const STORAGE_KEY = "yimm.locale";

function initialLocale(): Locale {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved === "zh" || saved === "en") return saved;
  } catch {
    /* storage can be blocked; fall through to the browser language */
  }
  return navigator.language.toLowerCase().startsWith("zh") ? "zh" : "en";
}

export function I18nProvider({ children, initial }: { children: ReactNode; initial?: Locale }) {
  const [locale, setLocale] = useState<Locale>(initial ?? initialLocale);

  useEffect(() => {
    document.documentElement.lang = locale === "zh" ? "zh-Hant" : "en";
  }, [locale]);

  const toggle = useCallback(() => {
    setLocale((current) => {
      const next: Locale = current === "zh" ? "en" : "zh";
      try {
        window.localStorage.setItem(STORAGE_KEY, next);
      } catch {
        /* a preference that cannot be saved is still applied for this visit */
      }
      return next;
    });
  }, []);

  const value = useMemo<I18n>(
    () => ({ locale, t: (key, vars) => translate(locale, key, vars), toggle }),
    [locale, toggle],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n(): I18n {
  const value = useContext(Ctx);
  if (!value) throw new Error("useI18n must be used inside I18nProvider");
  return value;
}
