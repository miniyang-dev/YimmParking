export type SymbolKind = "start" | "iparking" | "circle" | "cross";

interface Props {
  kind: SymbolKind;
  size?: number;
  className?: string;
}

/**
 * Orienteering control symbols, drawn in `currentColor` at one stroke weight.
 * start = triangle, iparking = double circle, circle = control, cross = other.
 */
export function Symbol({ kind, size = 26, className }: Props) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 26 26"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {kind === "start" && <path d="M13 3.5 23 21.5H3z" />}
      {kind === "iparking" && (
        <>
          <circle cx="13" cy="13" r="10" />
          <circle cx="13" cy="13" r="5.2" />
        </>
      )}
      {kind === "circle" && <circle cx="13" cy="13" r="10" />}
      {kind === "cross" && <path d="M7 7l12 12M19 7 7 19" />}
    </svg>
  );
}
