import { useState } from "react";
import { useI18n } from "../../i18n";

/**
 * Sends this view's link (it already names the lot and the search origin) through the phone's
 * share sheet, or copies it where there is none.
 */
export function ShareButton({ title, text }: { title: string; text: string }) {
  const { t } = useI18n();
  const [said, setSaid] = useState<string | null>(null);

  async function share() {
    const url = window.location.href;
    try {
      if (navigator.share) {
        await navigator.share({ title, text, url });
        return;
      }
      await navigator.clipboard.writeText(url);
      setSaid(t("share.copied"));
    } catch (error) {
      // Closing the share sheet is not a failure.
      if (error instanceof DOMException && error.name === "AbortError") return;
      setSaid(t("share.failed"));
    }
  }

  return (
    <p className="share">
      <button type="button" className="textbtn" onClick={() => void share()}>
        {t("share.button")}
      </button>
      <span className="share__said" role="status">
        {said}
      </span>
    </p>
  );
}
