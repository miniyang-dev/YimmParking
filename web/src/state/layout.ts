import { useEffect, useState } from "react";

/** Wide enough for the sheet and the opened control side by side (see app.css "desktop"). */
export const WIDE_QUERY = "(min-width: 1024px)";

function matches(query: string): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia(query).matches
    : false;
}

/** Whether the desktop layout applies; follows window resizes. */
export function useWide(): boolean {
  const [wide, setWide] = useState(() => matches(WIDE_QUERY));
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const list = window.matchMedia(WIDE_QUERY);
    const update = () => setWide(list.matches);
    update();
    list.addEventListener("change", update);
    return () => list.removeEventListener("change", update);
  }, []);
  return wide;
}
