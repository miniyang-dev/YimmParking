/**
 * The number a `tel:` link should dial, from a lot's free-text phone field, or null when it
 * cannot be read with confidence (the text is then shown without a link).
 *
 * The feeds write things like "2523-5000 #1138", "(02)2754-6661分機18" or "0912-345-678、2655-0818":
 * only the first number is dialled, without its extension, which stays visible in the text. Half
 * the Taipei / New Taipei numbers omit the area code, and a mobile phone cannot reach a landline
 * without it, so an 8-digit local number gets "02".
 */
export function dialable(raw: string): string | null {
  const first = raw.match(/\+?[\d()\-\s]+/)?.[0] ?? "";
  const digits = first.replace(/[^\d+]/g, "");
  if (digits.startsWith("+886")) return digits.length >= 12 && digits.length <= 13 ? digits : null;
  if (digits.startsWith("0")) return digits.length === 9 || digits.length === 10 ? digits : null;
  if (/^\d{8}$/.test(digits)) return `02${digits}`;
  return null;
}
