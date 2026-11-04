"""Build separate Chicago public-report layers for the research map.

CPD crime coordinates are block-level and approximate. The export keeps only
coarse, aggregated counts; it never emits addresses or individual incidents.
"""
import csv
import datetime as dt
import io
import sqlite3
import sys
import time
import urllib.parse
import urllib.request

SOC = "https://data.cityofchicago.org/resource"
UA = {"User-Agent": "casita/1.0", "Accept-Encoding": "gzip"}
SINCE = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=365)).strftime(
    "%Y-%m-%dT%H:%M:%S"
)
FAILED: list[str] = []


def fetch(dataset: str, select: str, where: str, page: int = 50000) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        params = {
            "$limit": str(page),
            "$offset": str(offset),
            "$select": select,
            "$where": where,
            "$order": ":id",
        }
        url = f"{SOC}/{dataset}.csv?" + urllib.parse.urlencode(params)
        for attempt in range(4):
            try:
                request = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(request, timeout=300) as response:
                    raw = response.read()
                    if response.headers.get("Content-Encoding") == "gzip":
                        import gzip

                        raw = gzip.decompress(raw)
                    text = raw.decode("utf-8", "replace")
                break
            except Exception as error:
                if attempt == 3:
                    FAILED.append(f"{dataset} offset {offset}: {str(error)[:100]}")
                    return rows
                time.sleep(2 * (attempt + 1))

        chunk = list(csv.DictReader(io.StringIO(text)))
        rows.extend(chunk)
        sys.stdout.write(f"\r  {dataset}: {len(rows):,}")
        sys.stdout.flush()
        if len(chunk) < page:
            break
        offset += page
    print()
    return rows


def _coordinates(rows: list[dict], kind: str) -> list[tuple[str, float, float]]:
    points = []
    for row in rows:
        try:
            lat = float(row["latitude"])
            lon = float(row["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if 41.5 < lat < 42.1 and -88.0 < lon < -87.4:
            points.append((kind, lat, lon))
    return points


jobs = [
    (
        "graffiti",
        "v6vf-nfxy",
        "latitude,longitude",
        f"sr_type='Graffiti Removal Request' and created_date > '{SINCE}' "
        "and latitude is not null and duplicate=false",
    ),
    (
        "vehicle_theft",
        "ijzp-q8t2",
        "latitude,longitude",
        f"primary_type='MOTOR VEHICLE THEFT' and date > '{SINCE}' "
        "and latitude is not null",
    ),
    (
        "violent",
        "ijzp-q8t2",
        "latitude,longitude",
        f"primary_type in ('HOMICIDE','CRIMINAL SEXUAL ASSAULT','ROBBERY',"
        f"'ASSAULT','BATTERY') and date > '{SINCE}' and latitude is not null",
    ),
]

con = sqlite3.connect("city.sqlite")
con.executescript("""
DROP TABLE IF EXISTS street_new;
CREATE TABLE street_new(kind TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL);
""")

for kind, dataset, select, where in jobs:
    print(f"[{kind}]")
    rows = fetch(dataset, select, where)
    points = _coordinates(rows, kind)
    if not points:
        FAILED.append(f"{kind}: no coordinate records returned")
    con.executemany("INSERT INTO street_new VALUES(?,?,?)", points)
    con.commit()
    print(f"  stored {len(points):,} approximate reports")

if FAILED:
    con.execute("DROP TABLE IF EXISTS street_new")
    con.close()
    print("\nIncomplete city-data fetch; keeping the existing street table.", file=sys.stderr)
    for failure in FAILED:
        print(f"  {failure}", file=sys.stderr)
    sys.exit(1)

con.executescript("""
DROP INDEX IF EXISTS ix_street;
DROP TABLE IF EXISTS street;
ALTER TABLE street_new RENAME TO street;
CREATE INDEX ix_street ON street(lat,lon);
""")
con.commit()
for kind, count in con.execute("SELECT kind, COUNT(*) FROM street GROUP BY kind"):
    print(f"  {kind:<14} {count:>8,}")
con.close()
