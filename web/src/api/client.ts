import type { components } from "./schema";
import type { BikeResponse, FoodResponse, SearchResponse, SortMode } from "../domain/types";

export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function getJson<T>(
  path: string,
  params: Record<string, string | number>,
  signal?: AbortSignal,
): Promise<T> {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, String(value));

  let response: Response;
  try {
    response = await fetch(url, { signal, headers: { Accept: "application/json" } });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError("network", "network error", 0);
  }

  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error = (body as { error?: { code?: string; message?: string } } | null)?.error;
    throw new ApiError(
      error?.code ?? "http_error",
      error?.message ?? response.statusText,
      response.status,
    );
  }
  return body as T;
}

export const api = {
  health: () => getJson<components["schemas"]["HealthResponse"]>("/api/v1/health", {}),

  searchAddress: (q: string, mode: SortMode, vendors: string, signal?: AbortSignal) =>
    getJson<SearchResponse>("/api/v1/search", { q, mode, vendors }, signal),

  nearby: (lat: number, lng: number, mode: SortMode, vendors: string, signal?: AbortSignal) =>
    getJson<SearchResponse>("/api/v1/parking/nearby", { lat, lng, mode, vendors }, signal),

  bikes: (lat: number, lng: number, signal?: AbortSignal) =>
    getJson<BikeResponse>("/api/v1/bikes/nearby", { lat, lng }, signal),

  food: (
    lat: number,
    lng: number,
    radius: number,
    origin?: { lat: number; lng: number },
    signal?: AbortSignal,
  ) =>
    getJson<FoodResponse>(
      "/api/v1/food/nearby",
      {
        lat,
        lng,
        radius,
        ...(origin ? { origin_lat: origin.lat, origin_lng: origin.lng } : {}),
      },
      signal,
    ),
};
