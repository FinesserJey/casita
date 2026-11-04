"""Rank listings by fit.

Heuristic baseline. Higher score = better.

Inputs are weighted in line with stated priorities, in priority order:
  - Walk-to-CTA stations — primary
  - Covered parking, in-unit laundry, and air conditioning — strong requirements
  - 1 bedroom preferred; a 1-bedroom with den or smaller 2-bedroom is suitable
  - Walk-to-Lake-Michigan beaches — secondary
  - Preferred downtown Chicago neighborhoods and bath count — bonuses

Walking times come from the `walk_map` populated by walk.populate_for().
When None, score is computed without those terms.
"""
from .models import Listing


def _hood_fallback_bonus(listing: Listing) -> int:
    """Small extra credit for the target downtown Chicago neighborhoods."""
    hood = (listing.hood or "").lower()
    if "river north" in hood or "fulton market" in hood:
        return 6
    if "west loop" in hood:
        return 5
    if "south loop" in hood:
        return 4
    return 0


def _walk_bonus(minutes: int | None, *, sweet_spot: int) -> int:
    """Sigmoid-ish: a 5-min walk should clearly beat 20-min, but 20 vs 25 is noise."""
    if minutes is None:
        return 0
    if minutes <= sweet_spot:
        return 15
    if minutes <= sweet_spot + 5:
        return 10
    if minutes <= sweet_spot + 10:
        return 5
    if minutes <= sweet_spot + 20:
        return 1
    return -3


def score(listing: Listing, walk_map: dict | None = None) -> int:
    s = 0

    # Transit is the primary location criterion; beaches are a nice-to-have.
    if walk_map is not None:
        from .walk import BEACHES, CTA_STATIONS, nearest
        nt = nearest(walk_map, listing.key, CTA_STATIONS)
        nb = nearest(walk_map, listing.key, BEACHES)
        if nt:
            s += _walk_bonus(nt[1], sweet_spot=8) * 2
        if nb:
            s += _walk_bonus(nb[1], sweet_spot=12)

    s += _hood_fallback_bonus(listing)

    # One bedroom is preferred; a den is extra useful, and two bedrooms remain
    # acceptable. Studios and larger layouts are poor fits for the desk need.
    if listing.beds == 1:
        s += 8
    elif listing.beds == 2:
        s += 5
    elif listing.beds == 0:
        s -= 20
    elif listing.beds is not None and listing.beds > 2:
        s -= 20
    if listing.has_den:
        s += 4
    if listing.baths and listing.baths >= 1.5:
        s += 5
    elif listing.baths and listing.baths >= 1:
        s += 2

    # Missing must-have facts stay visible for verification; known negatives
    # rank well below confirmed matches.
    if listing.laundry == "in-unit":
        s += 16
    elif listing.laundry:
        s -= 25
    if listing.air_conditioning is True:
        s += 12
    elif listing.air_conditioning is False:
        s -= 30
    covered = listing.covered_parking
    parking = (listing.parking or "").lower()
    if covered is None:
        if any(term in parking for term in ("garage", "covered", "carport")):
            covered = True
        elif any(term in parking for term in ("street", "no parking", "none", "uncovered")):
            covered = False
    if covered is True:
        s += 18
    elif covered is False:
        s -= 30

    # Preserve small legacy amenity signals after the strong requirements.

    return s


ELIMINATED_STATUSES = frozenset({"declined_by_landlord", "declined_by_us", "passed_on"})

# Active CRM pipeline — the listings we're actually pursuing. Higher strength =
# further along; orders within the pipeline bucket after vote weight.
PIPELINE_STRENGTH = {
    "applied": 5,
    "viewing_done": 4,
    "viewing_scheduled": 3,
    "shortlist": 2,
    "contacted": 1,
}


def rank(
    listings: list[Listing],
    walk_map: dict | None = None,
    status_map: dict[str, str] | None = None,
    vote_scores: dict[str, int] | None = None,
) -> list[Listing]:
    """Sort order — six buckets:
     -2. Active pipeline — a live CRM status (contacted → viewing → applied):
         the real to-do list, above everything. Within: more up-voters first,
         then further-along status, then llm_rank.
     -1. Favorites — net-upvoted (and not in pipeline/eliminated). An explicit
         human "yes" beats the ranker. Within: more up-voters first, then rank.
      0. Ranked + not filtered (severity ok / concerns), by llm_rank ascending
      1. New listings without an llm_rank yet (don't punish for being unranked)
      2. Filtered listings (severity=filtered)
      3. Eliminated — landlord-declined / we-passed / out-of-area, at the bottom

    Eliminated is soft-delete: we keep them visible at the end so we don't lose
    track of past leads. An eliminated listing stays down even if it was once
    up-voted or in the pipeline — the explicit pass is the newer, stronger
    signal. Within each bucket, ties break on heuristic score.
    """
    status_map = status_map or {}
    vote_scores = vote_scores or {}
    def sort_key(L: Listing) -> tuple:
        net = vote_scores.get(L.key, 0)
        status = status_map.get(L.key)
        strength = PIPELINE_STRENGTH.get(status, 0)
        if status in ELIMINATED_STATUSES:
            bucket = 3
        elif strength:
            bucket = -2
        elif net > 0:
            bucket = -1
        elif L.llm_severity == "filtered" or (L.llm_rank or 0) >= 9000:
            bucket = 2
        elif L.llm_rank is None:
            bucket = 1
        else:
            bucket = 0
        return (bucket, -net, -strength, L.llm_rank or 0, -score(L, walk_map))
    return sorted(listings, key=sort_key)
