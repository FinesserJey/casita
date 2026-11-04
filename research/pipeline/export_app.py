"""Trim the merged apartments into a browser payload, adding block context."""
import json, math, re, collections
apts = json.load(open("apartments.json"))

def unit_sqft(v):
    """Apartments.com sometimes returns the whole building's floor area.
    Anything over ~5,000 sq ft is not one apartment."""
    m = re.search(r"[\d,]+", str(v or ""))
    if not m: return None
    n = int(m.group(0).replace(",", ""))
    return v if 80 <= n <= 5000 else None

def street_only(s):
    """Remove the city and postal suffix from a published address."""
    s = (s or "").split(",")[0].strip()
    return re.sub(r"\s+", " ", s)

def best_addr(a):
    """Craigslist gives a neighbourhood blurb, not an address. If the source
    string isn't street-like, keep the source's location text."""
    src = street_only(a.get("addr"))
    if re.match(r"^\d+\s+\S", src):
        return src
    return src or ""

out = []
for a in apts:
    if not a.get("rent") or a["rent"] < 400 or a["rent"] > 25000:
        continue          # drop obvious junk prices

    out.append({
      "id": a["id"],
      "addr": best_addr(a) or "", "name": a.get("name"), "unit": a.get("unit"),
      "hood": a.get("hood"), "lat": round(float(a["lat"]), 6), "lon": round(float(a["lon"]), 6),
      "beds": a.get("beds"), "baths": a.get("baths"), "sqft": unit_sqft(a.get("sqft")),
      "rent": a["rent"], "act": [a["rent"], a["rent"]], "est": "rent_only",
      "rating": a.get("rating"),
      "photo": (a.get("photos") or [None])[0],
      # Five was thin everywhere and plainly wrong on Redfin, which publishes a
      # median of 19 photographs and up to 91 -- the gallery was showing a
      # fourteenth of the advert. A renter's first question about a flat is what
      # it looks like, and five pictures, one of them usually the building from
      # the pavement and another a floor plan, does not answer it. Fourteen
      # costs about 2.4 MB across the whole payload.
      "photos": (a.get("photos") or [])[:14],
      # True when the photo count is a limit of our scraping, not of the advert.
      #
      # Zillow's search feed returns exactly one preview image per row, and the
      # gallery lives on the listing page, which is behind a bot wall for
      # /homedetails/. So every one of our Zillow rows carries a single photo
      # while the real advert may carry twenty -- 140 S Van Ness #743 publishes
      # twenty-three.
      #
      # Without this flag the verification factor docked those listings for
      # being thin and the fraud auditor raised "Only one photograph" on 100%
      # of Zillow, which is a check that is always true, applied to a third of
      # the inventory, for something the listing did not do. "The advert
      # published one photo" and "we could only retrieve one photo" are
      # different facts and only the first says anything about the listing.
      "photos_partial": any(s["n"] == "Zillow" for s in a.get("sources", []))
                        and len(a.get("photos") or []) <= 1,
      "src": [{"n": s["n"], "u": s.get("u"), "c": s.get("c", 1)} for s in a.get("sources", [])],
      # Epoch seconds, from the source that published one. Craigslist gives a
      # real posting time; Apartments.com gives prose we parse; Zillow's search
      # results carry no date at all, so this stays null there rather than
      # being quietly backfilled with the scrape time.
      "posted": a.get("posted"),
      # Contact, concessions and the listing's own words. The description is
      # what lets the scam auditor read more than a truncated title.
      "phone": a.get("phone"), "site": a.get("site"),
      "special": a.get("special"), "tours": a.get("tours") or 0,
      "desc": (a.get("desc") or "")[:1200] or None,
      "multi": a.get("multi"), "fuzzy": a.get("fuzzy_pin"),
      "yr": a.get("yr"), "units": a.get("units"),
      "wd": a.get("wd"), "ac": a.get("ac"),
      "covered_parking": a.get("covered_parking"),
      "unit_amen": a.get("unit_amen") or [],
      "has_den": a.get("has_den"),
      "street": {}, "street_pct": {},
    })

def score(a):
    """Recommended order: complete, plausible listings first."""
    s = 0
    if a["photo"]: s += 3
    if a["rating"]: s += 2
    if a["beds"] is not None: s += 1
    if a.get("sqft"): s += 1
    return -s

out.sort(key=lambda a: (score(a), a["rent"]))
for i, a in enumerate(out):
    a["rank"] = i

json.dump(out, open("app_data.json", "w"), separators=(",", ":"))

print(f"apartments exported: {len(out):,}")
print(f"  with photo:        {sum(1 for a in out if a['photo']):,}")
print(f"  with rating:       {sum(1 for a in out if a['rating']):,}")
print(f"  multi-source:      {sum(1 for a in out if a['multi']):,}")
import os
print(f"  payload: {os.path.getsize('app_data.json')/1e6:.2f} MB")
print("\nprice range:", min(a['rent'] for a in out), "-", max(a['rent'] for a in out))
print("hoods:", collections.Counter(a['hood'] for a in out if a['hood']).most_common(8))
