import type { Lot, SortMode } from "./types";

/** A vendor key for a vendor's section, "other", or "distance" in walking-only mode. */
export type SectionKey = string;

export interface Section {
  key: SectionKey;
  lots: Lot[];
}

/**
 * Split the server's already-ordered list into the sections shown on the sheet. The server puts
 * each vendor's section first, in the user's order, then everything else, so consecutive lots with
 * the same section key form one section. This never re-sorts.
 */
export function toSections(lots: Lot[], mode: SortMode): Section[] {
  if (mode === "distance") return lots.length ? [{ key: "distance", lots }] : [];

  const sections: Section[] = [];
  for (const lot of lots) {
    const key = lot.block === "priority" && lot.vendor ? lot.vendor : "other";
    const last = sections[sections.length - 1];
    if (last && last.key === key) last.lots.push(lot);
    else sections.push({ key, lots: [lot] });
  }
  return sections;
}
