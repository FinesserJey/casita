"""Walking and driving estimates from Chicago listings to named anchors.

Real travel times via Google Routes API (computeRouteMatrix) when
GOOGLE_MAPS_API_KEY is set; falls back to haversine × 1.3 ÷ 4.5 km/h
when the key is missing or the call fails. Results cached in a dedicated
local DB (~/.casita/routes_cache.sqlite, table `walk_cache`) keyed
by rounded lat/lng — re-runs are free, including the publisher daemon's
read-only renders (issue #4).
"""
import math
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")


@dataclass(frozen=True)
class Anchor:
    name: str
    short: str
    lat: float
    lng: float
    # Google Maps signals — surfaced on the card so the user can judge the
    # anchor at a glance. None for non-business anchors (trailheads, beaches).
    rating: float | None = None
    rating_count: int | None = None
    # Google Places place_id — drives the maps deep-link to the actual place
    # panel (reviews/hours/photos) rather than a generic search.
    place_id: str | None = None


BEACHES: list[Anchor] = [
    Anchor("Ohio Street Beach", "Ohio St Beach", 41.8925, -87.6125),
    Anchor("Oak Street Beach", "Oak St Beach", 41.9013, -87.6233),
    Anchor("12th Street Beach", "12th St Beach", 41.8638, -87.6078),
]

BAKERIES: list[Anchor] = [
    Anchor("Do-Rite Donuts & Chicken (River North)", "Do-Rite", 41.8908, -87.6322),
    Anchor("Lost Larson (West Loop)", "Lost Larson", 41.8846, -87.6474),
    Anchor("Kasama (Ukrainian Village)", "Kasama", 41.9008, -87.6672),
    Anchor("Goddess and the Baker (Loop)", "Goddess and the Baker", 41.8838, -87.6271),
]

CTA_STATIONS: list[Anchor] = [
    Anchor("Chicago Red Line", "Chicago Red", 41.8967, -87.6282),
    Anchor("Grand Red Line", "Grand Red", 41.8917, -87.6280),
    Anchor("Merchandise Mart", "Merchandise Mart", 41.8880, -87.6338),
    Anchor("Clark/Lake", "Clark/Lake", 41.8857, -87.6309),
    Anchor("Morgan", "Morgan", 41.8857, -87.6523),
    Anchor("Clinton Blue Line", "Clinton Blue", 41.8755, -87.6409),
    Anchor("Roosevelt", "Roosevelt", 41.8674, -87.6274),
]

ENTERTAINMENT: list[Anchor] = [
    Anchor("Chicago Theatre", "Chicago Theatre", 41.8854, -87.6278),
    Anchor("AMC River East 21", "AMC River East", 41.8917, -87.6176),
    Anchor("CIBC Theatre", "CIBC Theatre", 41.8796, -87.6278),
]

RESTAURANTS: list[Anchor] = [
    Anchor("Time Out Market Chicago", "Time Out Market", 41.8840, -87.6487),
    Anchor("Eataly Chicago", "Eataly", 41.8940, -87.6264),
    Anchor("Girl & the Goat", "Girl & the Goat", 41.8846, -87.6476),
]

SHOPPING: list[Anchor] = [
    Anchor("Block 37", "Block 37", 41.8837, -87.6280),
    Anchor("900 North Michigan Shops", "900 North Michigan", 41.8997, -87.6234),
]

ACTIVITIES: list[Anchor] = [
    Anchor("Chicago Riverwalk", "Riverwalk", 41.8880, -87.6295),
    Anchor("Art Institute of Chicago", "Art Institute", 41.8796, -87.6237),
    Anchor("Chicago Architecture Center", "Architecture Center", 41.8870, -87.6242),
]

ALL_ANCHORS = (
    BEACHES + BAKERIES + CTA_STATIONS + ENTERTAINMENT + RESTAURANTS + SHOPPING + ACTIVITIES
)

_WALK_SPEED_KMH = 4.5
_GRID_FACTOR = 1.30
_DRIVE_SPEED_KMH = 45.0
_DRIVE_GRID_FACTOR = 1.20
_ROUTES_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"


def _haversine_km(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    R = 6371.0
    dlat = math.radians(b_lat - a_lat)
    dlng = math.radians(b_lng - a_lng)
    s = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(a_lat))
        * math.cos(math.radians(b_lat))
        * math.sin(dlng / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(s))


def _haversine_minutes(lat: float, lng: float, anchor: Anchor) -> int:
    km = _haversine_km(lat, lng, anchor.lat, anchor.lng) * _GRID_FACTOR
    return max(1, round((km / _WALK_SPEED_KMH) * 60))


def _haversine_drive_minutes(lat: float, lng: float, anchor: Anchor) -> int:
    km = _haversine_km(lat, lng, anchor.lat, anchor.lng) * _DRIVE_GRID_FACTOR
    return max(1, round((km / _DRIVE_SPEED_KMH) * 60))


# ---------- cache (rounded coords as key) ----------
#
# Lives in a dedicated local DB, NOT the canonical GCS DB. The
# publisher daemon renders via with_db(read_only=True) — anything written
# to the pulled temp copy is discarded, so an in-DB cache re-paid the full
# Routes matrix on every publish (issue #4, ~$200 in 3 days). Route times
# are derived, location-keyed data; local runs are the only Routes consumer.

_DEFAULT_CACHE_DB = Path.home() / ".casita" / "routes_cache.sqlite"
_cache_connection: sqlite3.Connection | None = None
_cache_connection_path: Path | None = None


def _cache_db_path() -> Path:
    return Path(os.environ.get("CASITA_ROUTE_CACHE_DB", str(_DEFAULT_CACHE_DB)))


def _cache_conn() -> sqlite3.Connection:
    global _cache_connection, _cache_connection_path
    path = _cache_db_path()
    if _cache_connection is None or _cache_connection_path != path:
        if _cache_connection is not None:
            _cache_connection.close()
        path.parent.mkdir(parents=True, exist_ok=True)
        _cache_connection = sqlite3.connect(path)
        _cache_connection_path = path
        _ensure_cache(_cache_connection)
    return _cache_connection


def _ensure_cache(conn: sqlite3.Connection) -> None:
    create_sql = """CREATE TABLE IF NOT EXISTS walk_cache (
            from_lat REAL, from_lng REAL,
            to_lat REAL, to_lng REAL,
            mode TEXT NOT NULL DEFAULT 'walk',  -- 'walk' or 'drive'
            minutes INTEGER NOT NULL,
            source TEXT NOT NULL,   -- 'api' or 'haversine'
            ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (from_lat, from_lng, to_lat, to_lng, mode)
        )"""
    conn.execute(create_sql)
    # If table was created before the mode column existed, add it.
    info = conn.execute("PRAGMA table_info(walk_cache)").fetchall()
    cols = [r[1] for r in info]
    if "mode" not in cols:
        conn.execute("ALTER TABLE walk_cache ADD COLUMN mode TEXT NOT NULL DEFAULT 'walk'")
        info = conn.execute("PRAGMA table_info(walk_cache)").fetchall()

    # Older caches may have `mode` as a column but not as part of the primary
    # key, which lets walk and drive rows overwrite each other for the same
    # coordinate pair. Rebuild once into the current schema.
    pk_cols = {r[1] for r in info if r[5]}
    if "mode" not in pk_cols:
        conn.execute("ALTER TABLE walk_cache RENAME TO walk_cache_old")
        conn.execute(create_sql)
        conn.execute(
            """INSERT OR REPLACE INTO walk_cache
               (from_lat, from_lng, to_lat, to_lng, mode, minutes, source, ts)
               SELECT from_lat, from_lng, to_lat, to_lng,
                      COALESCE(mode, 'walk'), minutes, source, ts
               FROM walk_cache_old"""
        )
        conn.execute("DROP TABLE walk_cache_old")
    conn.commit()


def _rnd(x: float) -> float:
    # ~10m grid — good enough to dedupe API calls without losing accuracy.
    return round(x, 4)


def _cache_get(
    fl: float, fn: float, tl: float, tn: float,
    mode: str = "walk",
) -> int | None:
    row = _cache_conn().execute(
        "SELECT minutes FROM walk_cache "
        "WHERE from_lat=? AND from_lng=? AND to_lat=? AND to_lng=? AND mode=?",
        (_rnd(fl), _rnd(fn), _rnd(tl), _rnd(tn), mode),
    ).fetchone()
    return row[0] if row else None


def _cache_put(fl, fn, tl, tn, minutes: int, source: str, mode: str = "walk") -> None:
    _cache_conn().execute(
        "INSERT OR REPLACE INTO walk_cache "
        "(from_lat,from_lng,to_lat,to_lng,mode,minutes,source) VALUES (?,?,?,?,?,?,?)",
        (_rnd(fl), _rnd(fn), _rnd(tl), _rnd(tn), mode, minutes, source),
    )
    _cache_conn().commit()


# ---------- Routes API ----------


def _routes_api_enabled() -> bool:
    return os.environ.get("CASITA_ROUTES_OFFLINE") != "1" and bool(os.environ.get("GOOGLE_MAPS_API_KEY"))


def _call_routes_api(
    origins: list[tuple[float, float]], destinations: list[tuple[float, float]],
    *, mode: str = "walk",
) -> list[list[int | None]]:
    """Returns matrix[i][j] = travel minutes from origins[i] to destinations[j]."""
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not _routes_api_enabled() or not api_key:
        return [[None] * len(destinations) for _ in origins]
    travel_mode = "DRIVE" if mode == "drive" else "WALK"
    body = {
        "origins": [{"waypoint": {"location": {"latLng": {"latitude": la, "longitude": ln}}}} for la, ln in origins],
        "destinations": [{"waypoint": {"location": {"latLng": {"latitude": la, "longitude": ln}}}} for la, ln in destinations],
        "travelMode": travel_mode,
    }
    # No routingPreference: omitting it bills the Essentials SKU instead of
    # traffic-aware Pro — static drive context doesn't need live traffic (#4).
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "originIndex,destinationIndex,duration,condition",
    }
    try:
        r = httpx.post(_ROUTES_URL, json=body, headers=headers, timeout=15)
        r.raise_for_status()
        rows = r.json()
    except Exception as e:
        print(f"  routes api err: {e}")
        return [[None] * len(destinations) for _ in origins]

    out: list[list[int | None]] = [[None] * len(destinations) for _ in origins]
    for entry in rows:
        i = entry.get("originIndex")
        j = entry.get("destinationIndex")
        if i is None or j is None or entry.get("condition") != "ROUTE_EXISTS":
            continue
        dur = entry.get("duration", "")  # e.g. "1234s"
        if dur.endswith("s"):
            try:
                seconds = int(dur[:-1])
                out[i][j] = max(1, round(seconds / 60))
            except ValueError:
                pass
    return out


# ---------- public ----------


def _populate_for_mode(listings, mode: str) -> dict[tuple[str, str], int]:
    result: dict[tuple[str, str], int] = {}
    pending_pairs: list[tuple[str, str, float, float, float, float]] = []
    for L in listings:
        if L.lat is None or L.lng is None:
            continue
        for a in ALL_ANCHORS:
            cached = _cache_get(L.lat, L.lng, a.lat, a.lng, mode=mode)
            if cached is not None:
                result[(L.key, a.name)] = cached
            else:
                pending_pairs.append((L.key, a.name, L.lat, L.lng, a.lat, a.lng))

    if not pending_pairs:
        return result

    unique_origins: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()
    for _, _, fl, fn, _, _ in pending_pairs:
        key = (_rnd(fl), _rnd(fn))
        if key not in seen:
            seen.add(key)
            unique_origins.append((fl, fn))

    destinations = [(a.lat, a.lng) for a in ALL_ANCHORS]
    label = f"routes api ({mode})" if _routes_api_enabled() else f"routes fallback ({mode})"
    print(f"  {label}: {len(unique_origins)} origins × {len(destinations)} anchors")
    for chunk_start in range(0, len(unique_origins), 25):
        chunk = unique_origins[chunk_start:chunk_start + 25]
        matrix = _call_routes_api(chunk, destinations, mode=mode)
        for i, (fl, fn) in enumerate(chunk):
            for j, (tl, tn) in enumerate(destinations):
                mins = matrix[i][j]
                if mins is None:
                    fallback = (
                        _haversine_drive_minutes(fl, fn, ALL_ANCHORS[j])
                        if mode == "drive"
                        else _haversine_minutes(fl, fn, ALL_ANCHORS[j])
                    )
                    _cache_put(fl, fn, tl, tn, fallback, "haversine", mode=mode)
                else:
                    _cache_put(fl, fn, tl, tn, mins, "api", mode=mode)

    for listing_key, anchor_name, fl, fn, tl, tn in pending_pairs:
        minutes = _cache_get(fl, fn, tl, tn, mode=mode)
        if minutes is not None:
            result[(listing_key, anchor_name)] = minutes
    return result


def populate_drive_for_chicago(listings) -> dict[tuple[str, str], int]:
    """Return driving minutes from each geocoded Chicago listing to all anchors."""
    return _populate_for_mode(listings, "drive")


def populate_drive_for_marin(listings) -> dict[tuple[str, str], int]:
    """Compatibility wrapper for older callers; all supported listings are now Chicago."""
    return populate_drive_for_chicago(listings)


def populate_drive_for_bakeries(listings):
    """Return the nearest bakery by driving from each Chicago listing."""
    drive_map = populate_drive_for_chicago(listings)
    out: dict[str, tuple[Anchor, int]] = {}
    for L in listings:
        if L.lat is None or L.lng is None:
            continue
        best: tuple[Anchor, int] | None = None
        for a in BAKERIES:
            minutes = drive_map.get((L.key, a.name))
            if minutes is not None and (best is None or minutes < best[1]):
                best = (a, minutes)
        if best:
            out[L.key] = best
    return out


def populate_for(listings) -> dict[tuple[str, str], int]:
    """Ensure every (listing, anchor) pair has a cached minutes value.

    Returns a dict keyed by (listing.key, anchor.name) → minutes.
    """
    return _populate_for_mode(listings, "walk")


def minutes_to(walk_map: dict[tuple[str, str], int], listing_key: str, anchor: Anchor) -> int | None:
    return walk_map.get((listing_key, anchor.name))


def nearest(walk_map: dict[tuple[str, str], int], listing_key: str, anchors: list[Anchor]) -> tuple[Anchor, int] | None:
    best: tuple[Anchor, int] | None = None
    for a in anchors:
        m = walk_map.get((listing_key, a.name))
        if m is None:
            continue
        if best is None or m < best[1]:
            best = (a, m)
    return best
