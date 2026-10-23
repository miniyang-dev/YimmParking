"""The database schema, as an append-only list of migrations."""

from __future__ import annotations

from yimmparking.adapters.store import history

# Migrations are applied by position and recorded in PRAGMA user_version, so this tuple is
# append-only: never insert or reorder. tests/unit/test_migrations.py pins the history.
MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE parking_lot (
        id TEXT PRIMARY KEY,
        city TEXT NOT NULL,
        source_id TEXT NOT NULL,
        name TEXT NOT NULL,
        address TEXT NOT NULL,
        district TEXT NOT NULL,
        lat REAL NOT NULL,
        lng REAL NOT NULL,
        phone TEXT NOT NULL,
        total_car INTEGER,
        fee_text TEXT NOT NULL,
        service_time TEXT NOT NULL,
        kind TEXT NOT NULL,
        ev_charging_spaces INTEGER,
        accessible_spaces INTEGER,
        brand TEXT NOT NULL,
        brand_evidence TEXT NOT NULL,
        iparking_code TEXT
    );
    CREATE INDEX idx_parking_lot_geo ON parking_lot (lat, lng);
    CREATE INDEX idx_parking_lot_city ON parking_lot (city);

    CREATE TABLE availability_latest (
        lot_id TEXT PRIMARY KEY,
        city TEXT NOT NULL,
        count INTEGER,
        observed_at TEXT NOT NULL
    );

    CREATE TABLE availability_observation (
        lot_id TEXT NOT NULL,
        city TEXT NOT NULL,
        count INTEGER,
        observed_at TEXT NOT NULL,
        PRIMARY KEY (lot_id, observed_at)
    );
    CREATE INDEX idx_observation_time ON availability_observation (observed_at);

    CREATE TABLE geocode_cache (
        key TEXT PRIMARY KEY,
        payload TEXT NOT NULL,
        expires_at TEXT NOT NULL
    );
    """,
    # v2: per-period counters for paid external APIs (self-imposed free-tier ceilings).
    """
    CREATE TABLE api_usage (
        meter TEXT NOT NULL,
        period TEXT NOT NULL,
        count INTEGER NOT NULL,
        PRIMARY KEY (meter, period)
    );
    """,
    # v3: provider results held for a bounded time so a repeated lookup is not billed twice.
    """
    CREATE TABLE place_cache (
        key TEXT PRIMARY KEY,
        payload TEXT NOT NULL,
        expires_at TEXT NOT NULL
    );
    """,
    # v4: walking times between fixed points; seconds NULL means "no route".
    """
    CREATE TABLE walk_cache (
        key TEXT PRIMARY KEY,
        seconds INTEGER,
        meters INTEGER,
        expires_at TEXT NOT NULL
    );
    """,
    # v5: availability history as changes only, plus the polls that say when a feed was read.
    # The v1 table it replaces is converted and dropped by `yimmparking convert-history`.
    history.SCHEMA,
    # v6: which source each latest reading came from (NULL for older rows: the city's feed).
    """
    ALTER TABLE availability_latest ADD COLUMN source TEXT;
    """,
)
