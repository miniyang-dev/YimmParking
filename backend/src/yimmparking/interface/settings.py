"""Runtime configuration, read from the environment (and an optional backend/.env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = BACKEND_DIR / "data" / "yimmparking.db"


def _load_dotenv(path: Path) -> None:
    """Minimal KEY=VALUE loader; real environment variables always win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _web_dist(configured: str | None) -> Path | None:
    """The built web client, served by the API itself so one process (and one origin) is enough."""
    path = Path(configured) if configured else BACKEND_DIR.parent / "web" / "dist"
    return path if (path / "index.html").is_file() else None


@dataclass(frozen=True, slots=True)
class Settings:
    db_path: Path
    google_maps_api_key: str | None
    cors_origins: tuple[str, ...]
    user_agent: str
    availability_interval_s: int
    lots_interval_s: int
    geocode_monthly_limit: int
    places_monthly_limit: int
    geocode_endpoint: str | None
    places_endpoint: str | None
    food_min_rating: float
    food_min_reviews: int
    food_cache_ttl_hours: float
    web_dist: Path | None
    routes_monthly_limit: int
    routes_endpoint: str | None
    route_cache_ttl_days: float
    history_days: int
    alert_url: str | None
    backup_dir: Path
    backup_keep: int
    tdx_client_id: str | None
    tdx_client_secret: str | None
    tdx_token_url: str | None
    tdx_api_base: str | None
    tdx_monthly_points: float
    tdx_fallback_minutes: int

    @classmethod
    def from_env(cls) -> Settings:
        _load_dotenv(BACKEND_DIR / ".env")
        env = os.environ
        db_path = Path(env.get("YIMM_DB_PATH", str(DEFAULT_DB_PATH)))
        origins = env.get("YIMM_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
        return cls(
            db_path=db_path,
            google_maps_api_key=env.get("GOOGLE_MAPS_API_KEY") or None,
            cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
            user_agent=env.get("YIMM_USER_AGENT", "YimmParking/0.1"),
            availability_interval_s=int(env.get("YIMM_AVAILABILITY_INTERVAL_S", "120")),
            lots_interval_s=int(env.get("YIMM_LOTS_INTERVAL_S", str(24 * 3600))),
            # Defaults sit 10% under Google's free tier (Geocoding 10,000; Places Nearby Search
            # Enterprise 1,000) to absorb differences in the billing-month boundary.
            geocode_monthly_limit=int(env.get("YIMM_GEOCODE_MONTHLY_LIMIT", "9000")),
            places_monthly_limit=int(env.get("YIMM_PLACES_MONTHLY_LIMIT", "900")),
            # Optional overrides for a local stand-in of the Google endpoints (UI testing).
            geocode_endpoint=env.get("YIMM_GEOCODE_ENDPOINT") or None,
            places_endpoint=env.get("YIMM_PLACES_ENDPOINT") or None,
            # Quality floor for food results; the rating is applied by Google, the count by us.
            food_min_rating=float(env.get("YIMM_FOOD_MIN_RATING", "4.0")),
            food_min_reviews=int(env.get("YIMM_FOOD_MIN_REVIEWS", "100")),
            food_cache_ttl_hours=float(env.get("YIMM_FOOD_CACHE_TTL_HOURS", "24")),
            web_dist=_web_dist(env.get("YIMM_WEB_DIST")),
            # Routes Essentials is 10,000 free elements a month; stay 10% under it.
            routes_monthly_limit=int(env.get("YIMM_ROUTES_MONTHLY_LIMIT", "9000")),
            routes_endpoint=env.get("YIMM_ROUTES_ENDPOINT") or None,
            route_cache_ttl_days=float(env.get("YIMM_ROUTE_CACHE_TTL_DAYS", "30")),
            # Availability history (changes only) kept for a year: enough to see weekly and
            # seasonal patterns, at roughly 1.4 MB a day.
            history_days=int(env.get("YIMM_HISTORY_DAYS", "365")),
            # Where a stopped feed is reported (plain-text POST, e.g. https://ntfy.sh/<topic>).
            alert_url=env.get("YIMM_ALERT_URL") or None,
            # Daily copies sit next to the data folder (…/data/x.db → …/backup/), newest 7 kept.
            backup_dir=Path(env.get("YIMM_BACKUP_DIR") or db_path.parent.parent / "backup"),
            backup_keep=int(env.get("YIMM_BACKUP_KEEP", "7")),
            # TDX (交通部運輸資料流通服務) credentials for on-street parking; without them the
            # curb endpoint answers 503 and the web client hides the section.
            tdx_client_id=env.get("TDX_CLIENT_ID") or None,
            tdx_client_secret=env.get("TDX_CLIENT_SECRET") or None,
            # Optional overrides for a local stand-in of TDX (UI testing).
            tdx_token_url=env.get("YIMM_TDX_TOKEN_URL") or None,
            tdx_api_base=env.get("YIMM_TDX_API_BASE") or None,
            # TDX's free plan is 3 points a month, cut off at 105%; stop at 90% of it.
            tdx_monthly_points=float(env.get("YIMM_TDX_MONTHLY_POINTS", "2.7")),
            # How often Taipei's counts are read from TDX while the city's own feed has stopped.
            # TDX's own data changes about every 35 minutes; much past 30 and counts often expire.
            tdx_fallback_minutes=int(env.get("YIMM_TDX_FALLBACK_MINUTES", "30")),
        )
