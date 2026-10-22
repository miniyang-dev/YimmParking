import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "./api/client";
import { formatDistance } from "./domain/distance";
import { ageMinutes } from "./domain/availability";
import { remember, type SavedPlace } from "./domain/places";
import type { Lot } from "./domain/types";
import { serializePrefs } from "./domain/vendors";
import { LotDetail } from "./features/detail/LotDetail";
import { Legend, ResultSheet, SheetSkeleton } from "./features/results/ResultSheet";
import { CurbSection } from "./features/results/CurbSection";
import { StaleNotice } from "./features/results/StaleNotice";
import { SavedPlaces } from "./features/search/SavedPlaces";
import { SearchHeader } from "./features/search/SearchHeader";
import { SettingsPage } from "./features/settings/SettingsPage";
import { useI18n } from "./i18n";
import type { StringKey } from "./i18n/strings";
import { updatePlaces } from "./state/places";
import { usePrefs } from "./state/prefs";
import { takeLaunchLocate, useRoute } from "./state/route";
import { useParkingSearch } from "./state/queries";
import { useTheme } from "./state/theme";

function errorKey(error: unknown): StringKey {
  if (error instanceof ApiError) {
    switch (error.code) {
      case "address_not_found":
        return "error.address_not_found";
      case "geocoder_unavailable":
        return "error.geocoder_unavailable";
      case "geocoder_error":
        return "error.geocoder_error";
      case "quota_exhausted":
        return "error.quota_exhausted";
      case "network":
        return "error.network";
    }
  }
  return "error.generic";
}

/** Retrying only helps when the failure may be transient. */
function isRetryable(error: unknown): boolean {
  if (!(error instanceof ApiError)) return true;
  if (error.code === "geocoder_unavailable" || error.code === "quota_exhausted") return false;
  return error.code === "network" || error.code === "geocoder_error" || error.status >= 500;
}

export function App() {
  const { t } = useI18n();
  const [route, setRoute] = useRoute();
  const { theme, cycle: cycleTheme } = useTheme();
  const prefs = usePrefs();
  const search = useParkingSearch(route, serializePrefs(prefs));
  const settingsOpen = route.view === "settings";
  const [locating, setLocating] = useState(false);
  const [locateError, setLocateError] = useState(false);
  const now = useNow(30_000);
  // An address search is remembered once it resolves, with the coordinates it resolved to.
  const rememberNextAddress = useRef(false);

  const data = search.data;
  const lots = useMemo(() => data?.results ?? [], [data]);
  const selectedIndex = route.lot ? lots.findIndex((lot) => lot.id === route.lot) : -1;
  const selected = selectedIndex >= 0 ? (lots[selectedIndex] as Lot) : null;

  const newestObservation = useMemo(() => {
    const times = lots
      .map((lot) => lot.availability.observed_at)
      .filter((v): v is string => v !== null)
      .map((v) => new Date(v).getTime());
    return times.length ? new Date(Math.max(...times)).toISOString() : null;
  }, [lots]);

  useEffect(() => {
    if (!rememberNextAddress.current || !data || route.q === null) return;
    rememberNextAddress.current = false;
    const { lat, lng, label } = data.origin;
    updatePlaces((list) => remember(list, { label: label ?? route.q ?? "", lat, lng }, Date.now()));
  }, [data, route.q]);

  function searchFrom(where: { label: string; lat: number; lng: number }, shownAs = where.label) {
    rememberNextAddress.current = false;
    updatePlaces((list) => remember(list, where, Date.now()));
    setRoute({ q: null, lat: where.lat, lng: where.lng, label: shownAs, lot: null });
  }

  function pickPlace(place: SavedPlace) {
    searchFrom(place, place.name ?? place.label);
  }

  const age = ageMinutes(newestObservation, now);
  const asOfLabel = age === null ? null : age === 0 ? t("scale.asofNow") : t("scale.asof", { min: age });
  const radiusLabel = data ? t("scale.within", { radius: formatDistance(data.meta.radius_m) }) : null;
  const showScale = !selected && !settingsOpen;

  function locate() {
    if (!navigator.geolocation) {
      setLocateError(true);
      return;
    }
    setLocating(true);
    setLocateError(false);
    rememberNextAddress.current = false; // "my location" is not a place worth listing
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false);
        setRoute({
          q: null,
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          label: t("search.located"),
          lot: null,
        });
      },
      () => {
        setLocating(false);
        setLocateError(true);
      },
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 30_000 },
    );
  }

  // Opened from the home-screen icon: start from where the phone is.
  useEffect(() => {
    if (takeLaunchLocate()) locate();
    // Once, on first render; `locate` only uses state setters and stable values.
  }, []);

  const initialText = route.q ?? route.label ?? data?.origin.label ?? "";

  return (
    <div className="app">
      <SearchHeader
        key={initialText}
        initialText={initialText}
        mode={route.mode}
        radiusLabel={showScale ? radiusLabel : null}
        asOfLabel={showScale ? asOfLabel : null}
        locating={locating}
        compact={selected !== null || settingsOpen}
        theme={theme}
        onTheme={cycleTheme}
        onSettings={() => setRoute({ view: "settings" })}
        onSubmit={(text) => {
          setLocateError(false);
          rememberNextAddress.current = true;
          setRoute({ q: text, lat: null, lng: null, label: null, lot: null });
        }}
        onLocate={locate}
        onMode={(mode) => setRoute({ mode }, { replace: true })}
        savedPanel={route.q !== null || route.lat !== null}
        onPickPlace={pickPlace}
      />

      <main className="main">
        {locateError && (
          <p className="notice" role="alert">
            {t("error.geolocation")}
          </p>
        )}

        {settingsOpen ? (
          <SettingsPage onDone={() => setRoute({ view: null })} />
        ) : selected ? (
          <LotDetail
            lot={selected}
            number={selectedIndex + 1}
            now={now}
            origin={{ lat: data?.origin.lat ?? selected.lat, lng: data?.origin.lng ?? selected.lng }}
            originLabel={initialText || t("search.origin")}
            onBack={() => setRoute({ lot: null })}
          />
        ) : route.lot && data ? (
          <p className="notice" role="alert">
            {t("detail.notFound")}{" "}
            <button type="button" className="textbtn" onClick={() => setRoute({ lot: null })}>
              {t("detail.back")}
            </button>
          </p>
        ) : search.isPending && search.fetchStatus === "fetching" ? (
          <>
            <p className="sr-only" role="status">
              {t("loading")}
            </p>
            <SheetSkeleton />
          </>
        ) : search.isError ? (
          <div className="notice" role="alert">
            <p>{t(errorKey(search.error))}</p>
            {isRetryable(search.error) && (
              <button type="button" className="textbtn" onClick={() => void search.refetch()}>
                {t("retry")}
              </button>
            )}
          </div>
        ) : data ? (
          <>
            {data.alternatives.length > 0 && (
              <p className="alts">
                {t("alternatives")}{" "}
                {data.alternatives.map((alt) => (
                  <button
                    key={`${alt.lat},${alt.lng}`}
                    type="button"
                    className="textbtn"
                    onClick={() => searchFrom(alt)}
                  >
                    {alt.label}
                  </button>
                ))}
              </p>
            )}
            <StaleNotice stale={data.meta.stale_sources} lots={lots} />
            {lots.length === 0 ? (
              <p className="notice">{t("empty.none")}</p>
            ) : (
              <ResultSheet
                lots={lots}
                mode={data.meta.mode}
                now={now}
                poolSize={data.meta.pool_size}
                walking={data.meta.walking}
                onOpen={(lot) => setRoute({ lot: lot.id })}
              />
            )}
            <CurbSection origin={{ lat: data.origin.lat, lng: data.origin.lng }} />
          </>
        ) : (
          <section className="empty">
            <h2>{t("empty.title")}</h2>
            <p>{t("empty.body")}</p>
            <SavedPlaces onPick={pickPlace} />
          </section>
        )}

        {showScale && <Legend />}
      </main>
    </div>
  );
}

function useNow(intervalMs: number): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return now;
}
