import { useCallback, useSyncExternalStore } from "react";
import type { SortMode } from "../domain/types";

/** Everything the screen shows is derived from the URL, so a view can be shared and refreshed. */
export interface Route {
  q: string | null;
  lat: number | null;
  lng: number | null;
  label: string | null;
  mode: SortMode;
  lot: string | null;
  view: "settings" | null;
}

function number(value: string | null): number | null {
  if (value === null || value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function parseRoute(search: string): Route {
  const p = new URLSearchParams(search);
  const lat = number(p.get("lat"));
  const lng = number(p.get("lng"));
  const hasCoords = lat !== null && lng !== null;
  return {
    q: p.get("q")?.trim() || null,
    lat: hasCoords ? lat : null,
    lng: hasCoords ? lng : null,
    label: p.get("label"),
    mode: p.get("mode") === "distance" ? "distance" : "tiered",
    lot: p.get("lot"),
    view: p.get("view") === "settings" ? "settings" : null,
  };
}

export function serializeRoute(route: Route): string {
  const p = new URLSearchParams();
  if (route.lat !== null && route.lng !== null) {
    p.set("lat", route.lat.toFixed(6));
    p.set("lng", route.lng.toFixed(6));
    if (route.label) p.set("label", route.label);
  } else if (route.q) {
    p.set("q", route.q);
  }
  if (route.mode === "distance") p.set("mode", "distance");
  if (route.lot) p.set("lot", route.lot);
  if (route.view) p.set("view", route.view);
  const text = p.toString();
  return text ? `?${text}` : window.location.pathname;
}

/**
 * True once when the page was opened to locate the phone (`?locate=1`, the installed app's start
 * URL). The flag is removed from the address at once, so a reload or a later visit to this
 * history entry does not ask for the location again.
 */
export function takeLaunchLocate(): boolean {
  const params = new URLSearchParams(window.location.search);
  if (params.get("locate") !== "1") return false;
  window.history.replaceState(null, "", serializeRoute(parseRoute(window.location.search)));
  return true;
}

const EVENT = "yimm:route";

function subscribe(onChange: () => void): () => void {
  window.addEventListener("popstate", onChange);
  window.addEventListener(EVENT, onChange);
  return () => {
    window.removeEventListener("popstate", onChange);
    window.removeEventListener(EVENT, onChange);
  };
}

const snapshot = () => window.location.search;

export function useRoute(): [Route, (patch: Partial<Route>, options?: { replace?: boolean }) => void] {
  const search = useSyncExternalStore(subscribe, snapshot, () => "");
  const route = parseRoute(search);

  const update = useCallback((patch: Partial<Route>, options?: { replace?: boolean }) => {
    const next = { ...parseRoute(window.location.search), ...patch };
    const url = serializeRoute(next);
    if (options?.replace) window.history.replaceState(null, "", url);
    else window.history.pushState(null, "", url);
    window.dispatchEvent(new Event(EVENT));
  }, []);

  return [route, update];
}
