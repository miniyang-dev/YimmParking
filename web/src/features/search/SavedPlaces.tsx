import { useState, type FormEvent } from "react";
import {
  MAX_NAME,
  displayName,
  forget,
  ordered,
  rename,
  toggleFavorite,
  type SavedPlace,
} from "../../domain/places";
import { useI18n } from "../../i18n";
import { updatePlaces, usePlaces } from "../../state/places";

interface Props {
  /** Search from this place (by its saved coordinates: no address lookup). */
  onPick: (place: SavedPlace) => void;
}

/** Starred places, then recent ones. A star is a shape, not a colour, so it reads in glare. */
export function SavedPlaces({ onPick }: Props) {
  const { t } = useI18n();
  const places = ordered(usePlaces());
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  if (places.length === 0) return null;

  function startRename(place: SavedPlace) {
    setEditing(place.id);
    setDraft(place.name ?? "");
  }

  function saveRename(event: FormEvent, place: SavedPlace) {
    event.preventDefault();
    updatePlaces((list) => rename(list, place.id, draft));
    setEditing(null);
  }

  const groups: { key: string; title: string; list: SavedPlace[] }[] = [
    { key: "fav", title: t("places.favorites"), list: places.filter((p) => p.favorite) },
    { key: "recent", title: t("places.recent"), list: places.filter((p) => !p.favorite) },
  ];

  return (
    <div className="saved">
      {groups
        .filter((group) => group.list.length > 0)
        .map((group) => (
          <section key={group.key} aria-labelledby={`saved-${group.key}`}>
            <h2 id={`saved-${group.key}`} className="saved__title">
              {group.title}
            </h2>
            <ul className="saved__list">
              {group.list.map((place) => {
                const name = displayName(place);
                return (
                  <li key={place.id} className="saved__row">
                    <button
                      type="button"
                      className="saved__icon saved__star"
                      aria-pressed={place.favorite}
                      aria-label={t(place.favorite ? "places.unstar" : "places.star", { name })}
                      onClick={() => updatePlaces((list) => toggleFavorite(list, place.id))}
                    >
                      {place.favorite ? "★" : "☆"}
                    </button>
                    {editing === place.id ? (
                      <form className="saved__edit" onSubmit={(e) => saveRename(e, place)}>
                        <label className="sr-only" htmlFor={`rename-${place.id}`}>
                          {t("places.nameLabel", { label: place.label })}
                        </label>
                        <input
                          id={`rename-${place.id}`}
                          className="saved__input"
                          value={draft}
                          maxLength={MAX_NAME}
                          placeholder={t("places.namePlaceholder")}
                          autoFocus
                          onChange={(e) => setDraft(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Escape") setEditing(null);
                          }}
                        />
                        <button type="submit" className="textbtn">
                          {t("places.save")}
                        </button>
                        <button type="button" className="textbtn" onClick={() => setEditing(null)}>
                          {t("places.cancel")}
                        </button>
                      </form>
                    ) : (
                      <>
                        <button type="button" className="saved__pick" onClick={() => onPick(place)}>
                          <span className="saved__name">{name}</span>
                          {place.name && <span className="saved__label">{place.label}</span>}
                        </button>
                        {place.favorite && (
                          <button
                            type="button"
                            className="saved__icon"
                            aria-label={t("places.rename", { name })}
                            onClick={() => startRename(place)}
                          >
                            ✎
                          </button>
                        )}
                        <button
                          type="button"
                          className="saved__icon"
                          aria-label={t("places.remove", { name })}
                          onClick={() => updatePlaces((list) => forget(list, place.id))}
                        >
                          ×
                        </button>
                      </>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      <p className="saved__note">{t("places.note")}</p>
    </div>
  );
}
