from casita import storage, zillow
from casita.geo import resolve_neighborhood
from casita.models import Listing
from casita.rank import score
from casita.walk import CTA_STATIONS


def _listing(**kwargs):
    return Listing(
        source="manual",
        source_id="test",
        url="",
        beds=1,
        **kwargs,
    )


def test_chicago_neighborhoods_resolve_from_coordinates():
    assert resolve_neighborhood(41.895, -87.633) == "River North"
    assert resolve_neighborhood(41.885, -87.650) == "Fulton Market"
    assert resolve_neighborhood(41.770, -122.450) is None


def test_pet_policy_does_not_change_fit_score():
    no_pets = _listing(dog_policy="no_dogs", pets_allowed=False)
    dogs_ok = _listing(dog_policy="large_ok", pets_allowed=True)

    assert score(no_pets) == score(dogs_ok)


def test_confirmed_chicago_requirements_outscore_unknown_or_negative():
    confirmed = _listing(
        covered_parking=True,
        laundry="in-unit",
        air_conditioning=True,
    )
    unknown = _listing()
    negative = _listing(
        covered_parking=False,
        laundry="shared (in building)",
        air_conditioning=False,
    )

    assert score(confirmed) > score(unknown) > score(negative)


def test_cta_station_walkability_affects_fit_score():
    listing = _listing()
    station = CTA_STATIONS[0]
    close = {(listing.key, station.name): 5}
    far = {(listing.key, station.name): 40}

    assert score(listing, close) > score(listing, far)


def test_zillow_details_extract_covered_parking_and_ac():
    listing = Listing(source="zillow", source_id="123", url="https://example.test")
    html = """
    <ul class="Fact-list">
      <li>Parking features: Attached garage</li>
      <li>Laundry: In unit</li>
      <li>Air conditioning: Central air</li>
    </ul>
    """

    zillow._parse_detail_html(html, listing)

    assert listing.covered_parking is True
    assert listing.laundry == "in-unit"
    assert listing.air_conditioning is True


def test_listing_feature_facts_round_trip_through_sqlite(tmp_path, monkeypatch):
    monkeypatch.setenv("CASITA_DB_PATH", str(tmp_path / "chicago.sqlite"))
    listing = Listing(
        source="manual",
        source_id="river-north-1",
        url="",
        neighborhood="River North",
        beds=1,
        has_den=True,
        covered_parking=True,
        laundry="in-unit",
        air_conditioning=True,
    )

    with storage.connect() as conn:
        storage.upsert_run(conn, [listing], succeeded_sources=["manual"])
        actual = storage.active_listings(conn)[0]

    assert actual.covered_parking is True
    assert actual.laundry == "in-unit"
    assert actual.air_conditioning is True
    assert actual.has_den is True
