from casita import craigslist, dedup, redfin, zillow, zumper
from casita.locations import CHICAGO_NEIGHBORHOOD_SLUGS


def test_source_priority_keeps_zillow_as_primary_source():
    assert dedup.SOURCE_PRIORITY["zillow"] == 0
    assert dedup.SOURCE_PRIORITY["zillow"] < dedup.SOURCE_PRIORITY["craigslist"]


def test_source_neighborhoods_match_chicago_target_areas():
    expected = set(CHICAGO_NEIGHBORHOOD_SLUGS)
    assert set(zillow.NEIGHBORHOODS) == expected
    assert set(zumper.NEIGHBORHOODS) == expected


def test_craigslist_location_regex_allows_flexible_whitespace():
    assert craigslist.CHICAGO_HOODS_RE.search("river\tnorth")
    assert craigslist.CHICAGO_HOODS_RE.search("fulton   market")
    assert not craigslist.CHICAGO_HOODS_RE.search("inner richmond")


def test_craigslist_search_targets_chicago_without_pet_filter():
    assert len(craigslist.SEARCH_URLS) == 1
    assert "craigslist.org/search/area/chicago" in craigslist.SEARCH_URLS[0]
    assert "min_bedrooms=1&max_bedrooms=2" in craigslist.SEARCH_URLS[0]
    assert "pets" not in craigslist.SEARCH_URLS[0]


def test_address_normalization_preserves_chicago_avenue_streets():
    assert (
        dedup._norm_addr("123 Chicago Ave, Chicago, IL 60601")
        == "123 chicago ave"
    )


def test_redfin_searches_are_chicago_downtown_zip_codes():
    assert len(redfin.SEARCHES) == 4
    assert all("redfin.com/zipcode/606" in url for _, url in redfin.SEARCHES)
    assert all("min-beds=1,max-beds=2" in url for _, url in redfin.SEARCHES)
    assert any("60661" in url for _, url in redfin.SEARCHES)
