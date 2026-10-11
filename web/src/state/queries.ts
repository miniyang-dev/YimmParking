import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../api/client";
import type { Route } from "./route";

/** Do not retry a request the server has already rejected on its merits. */
const retryFree = (count: number, error: unknown) =>
  error instanceof ApiError && error.status >= 400 && error.status < 500 ? false : count < 1;

/**
 * Settings for requests that spend paid quota (address lookup, food).
 *
 * - No retry: a retried request is billed again.
 * - No refetch on reconnect/focus: background refetches are billed too.
 * - Callers must not pass an AbortSignal: aborting after the request is sent saves nothing,
 *   and a remount (React StrictMode, quick back/forward) would then send it a second time.
 */
const PAID = {
  retry: false,
  refetchOnReconnect: false,
  refetchOnWindowFocus: false,
  refetchOnMount: false,
} as const;

/**
 * `vendors` is the user's vendor order and counts. It is part of the key: the list and the
 * walking-time shortlist both depend on it.
 */
export function useParkingSearch(route: Route, vendors: string) {
  const hasCoords = route.lat !== null && route.lng !== null;
  const byAddress = !hasCoords && route.q !== null;
  const enabled = hasCoords || route.q !== null;
  return useQuery({
    queryKey: hasCoords
      ? ["nearby", route.lat, route.lng, route.mode, vendors]
      : ["search", route.q, route.mode, vendors],
    queryFn: ({ signal }) =>
      hasCoords
        ? api.nearby(route.lat as number, route.lng as number, route.mode, vendors, signal)
        : api.searchAddress(route.q as string, route.mode, vendors),
    enabled,
    staleTime: 60_000,
    // Coordinates are free; an address lookup is a paid geocode.
    ...(byAddress ? PAID : { retry: retryFree }),
  });
}

/** Food is Google content: only held in memory briefly, never persisted. */
export function useFood(
  lat: number,
  lng: number,
  origin: { lat: number; lng: number },
  enabled: boolean,
) {
  return useQuery({
    // The origin is part of the key: the walking times in the answer depend on it.
    queryKey: ["food", lat.toFixed(5), lng.toFixed(5), origin.lat.toFixed(4), origin.lng.toFixed(4)],
    queryFn: () => api.food(lat, lng, 1000, origin),
    enabled,
    staleTime: 5 * 60_000,
    gcTime: 5 * 60_000,
    ...PAID,
  });
}
