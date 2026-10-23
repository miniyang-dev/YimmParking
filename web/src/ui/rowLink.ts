import type { MouseEvent } from "react";

/**
 * Lets a whole table row act as the link inside it: a click anywhere in the row follows the
 * row's link (same href and target), except a click on the link itself, which already does.
 */
export function followRowLink(event: MouseEvent<HTMLElement>): void {
  if (event.target instanceof Element && event.target.closest("a")) return;
  event.currentTarget.querySelector("a")?.click();
}
