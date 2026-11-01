import { useEffect, useRef, useState, type FormEvent } from "react";
import type { SavedPlace } from "../../domain/places";
import type { SortMode } from "../../domain/types";
import { useI18n } from "../../i18n";
import { nextTheme, type Theme } from "../../domain/theme";
import { Symbol } from "../../ui/Symbol";
import { SavedPlaces } from "./SavedPlaces";

interface Props {
  initialText: string;
  mode: SortMode;
  radiusLabel: string | null;
  asOfLabel: string | null;
  /** Where an address search landed, so a wrong guess shows instead of passing as the answer. */
  resolvedLabel?: string | null;
  locating: boolean;
  /** The last search failed: the field says so, and points at the message. */
  invalid?: boolean;
  compact?: boolean;
  theme: Theme;
  onTheme: () => void;
  onSettings: () => void;
  /** The name at the top returns to the empty start. */
  onHome: () => void;
  onSubmit: (text: string) => void;
  onLocate: () => void;
  onMode: (mode: SortMode) => void;
  /** Offer starred and recent places under the field while it has focus. */
  savedPanel: boolean;
  onPickPlace: (place: SavedPlace) => void;
}

export function SearchHeader({
  initialText,
  mode,
  radiusLabel,
  asOfLabel,
  resolvedLabel = null,
  locating,
  invalid = false,
  compact = false,
  theme,
  onTheme,
  onSettings,
  onHome,
  onSubmit,
  onLocate,
  onMode,
  savedPanel,
  onPickPlace,
}: Props) {
  const { t, toggle } = useI18n();
  const [text, setText] = useState(initialText);
  const [panelOpen, setPanelOpen] = useState(false);
  const [emptyHint, setEmptyHint] = useState(false);
  const searchArea = useRef<HTMLDivElement>(null);

  // The panel stays open while the person works in it (star, rename) and closes on a tap
  // elsewhere. Closing on blur instead would swallow taps on mobile, where the panel would
  // disappear between the touch and the click.
  useEffect(() => {
    if (!panelOpen) return;
    const outside = (event: PointerEvent) => {
      if (!searchArea.current?.contains(event.target as Node)) setPanelOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [panelOpen]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const value = text.trim();
    if (!value) {
      setEmptyHint(true);
      return;
    }
    setEmptyHint(false);
    setPanelOpen(false);
    onSubmit(value);
  }

  return (
    <header className="head">
      <div className="head__brand">
        <h1 className="head__name">
          <a
            href="/"
            className="head__home"
            aria-label={`${t("app.name")}, ${t("app.home")}`}
            onClick={(event) => {
              event.preventDefault();
              onHome();
            }}
          >
            {t("app.name")}
          </a>
        </h1>
        <div className="head__actions">
          <button type="button" className="chip" onClick={onSettings}>
            {t("settings.open")}
          </button>
          <button
            type="button"
            className="chip"
            onClick={onTheme}
            aria-label={t("theme.label", {
              mode: t(`theme.${theme}`),
              next: t(`theme.${nextTheme(theme)}`),
            })}
          >
            {t(`theme.${theme}`)}
          </button>
          <button type="button" className="chip" onClick={toggle} aria-label="Language / 語言">
            {t("lang.toggle")}
          </button>
        </div>
      </div>

      <div
        ref={searchArea}
        className="head__search"
        onKeyDown={(event) => {
          if (event.key === "Escape") setPanelOpen(false);
        }}
      >
        <form className="field" role="search" onSubmit={submit}>
          <Symbol kind="start" size={24} className="field__start" />
          <label className="sr-only" htmlFor="address">
            {t("search.label")}
          </label>
          <input
            id="address"
            aria-invalid={invalid || undefined}
            aria-describedby={invalid ? "search-error" : undefined}
            className="field__input"
            type="search"
            inputMode="search"
            enterKeyHint="search"
            autoComplete="street-address"
            placeholder={t("search.placeholder")}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setEmptyHint(false);
            }}
            onFocus={() => setPanelOpen(true)}
          />
          <button type="submit" className="field__go">
            {t("search.submit")}
          </button>
        </form>
        {emptyHint && (
          <p className="head__hint" role="alert">
            {t("search.empty")}
          </p>
        )}
        {panelOpen && savedPanel && !compact && (
          <SavedPlaces
            onPick={(place) => {
              setPanelOpen(false);
              onPickPlace(place);
            }}
          />
        )}
      </div>

      {!compact && (
      <div className="head__tools">
        <button type="button" className="textbtn" onClick={onLocate} disabled={locating}>
          {locating ? t("search.locating") : t("search.locate")}
        </button>
        <div className="seg" role="group" aria-label={t("mode.label")}>
          <button
            type="button"
            className="seg__btn"
            aria-pressed={mode === "tiered"}
            onClick={() => onMode("tiered")}
          >
            {t("mode.tiered")}
          </button>
          <button
            type="button"
            className="seg__btn"
            aria-pressed={mode === "distance"}
            onClick={() => onMode("distance")}
          >
            {t("mode.distance")}
          </button>
        </div>
      </div>
      )}

      {(resolvedLabel || radiusLabel || asOfLabel) && (
        <div className="scale">
          <span className="scale__bar" aria-hidden="true" />
          <span>
            {[resolvedLabel ? t("scale.resolved", { place: resolvedLabel }) : null, radiusLabel, asOfLabel]
              .filter(Boolean)
              .join(" · ")}
          </span>
        </div>
      )}
    </header>
  );
}
