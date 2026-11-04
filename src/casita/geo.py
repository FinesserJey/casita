"""Approximate downtown Chicago neighborhood lookup by latitude/longitude.

Boxes are deliberately scoped to the target rental area, not all of Chicago.
The narrower Fulton Market box is checked before West Loop because the two
neighborhoods meet and source labels are inconsistent.
"""

# (name, lat_min, lat_max, lng_min, lng_max). Order matters — first match wins.
CHICAGO_NEIGHBORHOODS: list[tuple[str, float, float, float, float]] = [
    ("Fulton Market", 41.879, 41.892, -87.657, -87.641),
    ("West Loop",     41.869, 41.892, -87.672, -87.641),
    ("River North",   41.889, 41.908, -87.650, -87.620),
    ("South Loop",    41.847, 41.878, -87.641, -87.610),
]


def resolve_neighborhood(lat: float | None, lng: float | None) -> str | None:
    if lat is None or lng is None:
        return None
    for name, lat_min, lat_max, lng_min, lng_max in CHICAGO_NEIGHBORHOODS:
        if lat_min <= lat <= lat_max and lng_min <= lng <= lng_max:
            return name
    return None
