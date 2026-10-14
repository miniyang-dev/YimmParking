import type { components } from "../api/schema";

export type Lot = components["schemas"]["ParkingLotDTO"];
export type SearchResponse = components["schemas"]["ParkingSearchResponse"];
export type FoodPlace = components["schemas"]["FoodDTO"];
export type FoodResponse = components["schemas"]["FoodSearchResponse"];
export type BikeStation = components["schemas"]["BikeStationDTO"];
export type BikeResponse = components["schemas"]["BikeSearchResponse"];
export type Availability = Lot["availability"];
export type SortMode = "tiered" | "distance";
export type Locale = "zh" | "en";
