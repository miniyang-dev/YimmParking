import { useState } from "react";
import {
  DEFAULT_PREFS,
  MAX_SHOW,
  moveVendor,
  samePrefs,
  setShow,
  VENDOR_LABEL,
  type VendorPrefs,
} from "../../domain/vendors";
import { useI18n } from "../../i18n";
import { savePrefs, usePrefs } from "../../state/prefs";
import { UsagePanel } from "./UsagePanel";

interface Props {
  onDone: () => void;
}

/**
 * Vendor order and counts. Changes stay in a draft until "save", so a half-made choice does not
 * send a billed search with every tap.
 */
export function SettingsPage({ onDone }: Props) {
  const { t } = useI18n();
  const saved = usePrefs();
  const [draft, setDraft] = useState<VendorPrefs>(saved);

  function save() {
    savePrefs(draft);
    onDone();
  }

  return (
    <section className="prefs" aria-labelledby="prefs-title">
      <h2 id="prefs-title" className="prefs__title">
        {t("settings.title")}
      </h2>
      <p className="prefs__intro">{t("settings.intro")}</p>

      <ol className="prefs__list">
        {draft.map((pick, index) => {
          const name = t(VENDOR_LABEL[pick.key]);
          return (
            <li key={pick.key} className="prefs__row">
              <span className="prefs__no">{index + 1}</span>
              <span className="prefs__body">
                <span className="prefs__name">{name}</span>
                <span className="prefs__controls">
                  <span className="prefs__count">
                    <button
                      type="button"
                      className="prefs__step"
                      disabled={pick.show <= 0}
                      aria-label={t("settings.fewer", { name })}
                      onClick={() => setDraft(setShow(draft, pick.key, pick.show - 1))}
                    >
                      −
                    </button>
                    <output className="prefs__value">{t("settings.count", { n: pick.show })}</output>
                    <button
                      type="button"
                      className="prefs__step"
                      disabled={pick.show >= MAX_SHOW}
                      aria-label={t("settings.more", { name })}
                      onClick={() => setDraft(setShow(draft, pick.key, pick.show + 1))}
                    >
                      +
                    </button>
                  </span>
                  <span className="prefs__order">
                    <button
                      type="button"
                      className="prefs__step"
                      disabled={index === 0}
                      aria-label={t("settings.up", { name })}
                      onClick={() => setDraft(moveVendor(draft, index, -1))}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      className="prefs__step"
                      disabled={index === draft.length - 1}
                      aria-label={t("settings.down", { name })}
                      onClick={() => setDraft(moveVendor(draft, index, 1))}
                    >
                      ↓
                    </button>
                  </span>
                </span>
              </span>
            </li>
          );
        })}
      </ol>

      <p className="prefs__note">{t("settings.small")}</p>
      <p className="prefs__note">{t("settings.routed")}</p>

      <div className="prefs__actions">
        <button
          type="button"
          className="textbtn"
          disabled={samePrefs(draft, DEFAULT_PREFS)}
          onClick={() => setDraft(DEFAULT_PREFS)}
        >
          {t("settings.reset")}
        </button>
        <button type="button" className="prefs__save" onClick={save}>
          {t("settings.save")}
        </button>
      </div>

      <UsagePanel />
    </section>
  );
}
