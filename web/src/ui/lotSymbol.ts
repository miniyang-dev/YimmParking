import type { Lot } from "../domain/types";
import type { SymbolKind } from "./Symbol";

/** The map symbol for a lot: iParking 嘟嘟房, another configured vendor, or a small operator. */
export function symbolFor(lot: Lot): SymbolKind {
  if (lot.vendor === "iparking_dodohome") return "iparking";
  if (lot.vendor) return "circle";
  return "cross";
}
