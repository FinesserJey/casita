#!/usr/bin/env python3
"""Rebuild the demo pages from the current data.

Replaces the inline heredoc at the end of refresh.sh, and adds two things it
did not have: the prototype layout, and a build stamp. The stamp is why this
exists as a file rather than staying inline -- the page could say when its
data was scraped only if something told it, and nothing did.

    python3 research/pipeline/build_pages.py            Chicago review page
    python3 research/pipeline/build_pages.py --public   sanitised public page

Casita (casita.html) is a separate page rather than an edit to the old
dashboard (huntly.html) because it is a different product, not a different
stylesheet: the quiz is the front door, the score exists to hide information
rather than to rank a list, and the right-hand panel stops being a map whenever
the question stops being geographic. The old build still builds, so the two can
be compared side by side until one of them is deleted.
"""
import datetime
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
RESEARCH = HERE.parent


def read(name):
    return open(HERE / name, encoding="utf-8").read()


def build(data_json, data_src="app_data.json"):
    html = read("casita.html")
    html = html.replace("/*__DATA__*/", data_json)
    html = html.replace("/*__GRID__*/", read("street_grid.json"))
    html = html.replace("/*__PLACES__*/", read("places.json"))
    # Order matters: each of these reads the ones above it at load time.
    for slot, src in (("ICONS", "icons.js"), ("MAPKIT", "mapkit.js"), ("GEO", "geo.js"),
                      ("HOODS", "hoods.js"),
                      ("ROUTER", "router.js"), ("FACTORS", "factors.js"), ("DEAL", "deal.js"),
                      ("QUIZ", "quiz.js"), ("CANVAS", "canvas.js")):
        html = html.replace(f"/*__{slot}__*/", read(src))

    # When the listing data was last written, not when this ran: rebuilding the
    # page without re-scraping must not make stale listings look fresh.
    #
    # casita.html is a fragment -- no <html>, <head> or <body>, the browser
    # supplies them -- so this anchors on the charset meta. Anchoring on
    # </head> looked right and silently did nothing.
    # Cache-bust the routing graph on its own content, not on the page build:
    # rebuilding the page must not re-download 1.5MB, and rebuilding the graph
    # must not leave clients on yesterday's roads.
    gz = RESEARCH / "walk_graph.json.gz"
    if gz.exists():
        stamp = hashlib.sha1(gz.read_bytes()).hexdigest()[:10]
        html = html.replace('"walk_graph.json"', f'"walk_graph.json?v={stamp}"')

    scraped = datetime.datetime.fromtimestamp(
        (HERE / data_src).stat().st_mtime)
    anchor = '<meta charset="utf-8">'
    assert anchor in html, "casita.html no longer opens with the charset meta"
    html = html.replace(
        anchor,
        anchor + f'\n<meta name="casita:scraped" '
                 f'content="{scraped.isoformat(timespec="seconds")}">', 1)
    return html, scraped


def require_chicago_data(data):
    """Do not label the checked-in San Francisco sample as a Chicago build."""
    if not data:
        sys.exit("no listings to build; refusing to publish an empty Chicago page")
    for listing in data:
        try:
            lat, lon = float(listing["lat"]), float(listing["lon"])
        except (KeyError, TypeError, ValueError):
            sys.exit("listing data is missing Chicago coordinates; refusing to build")
        if not (41.64 <= lat <= 42.03 and -87.95 <= lon <= -87.52):
            sys.exit("listing data contains non-Chicago coordinates; refresh Chicago data first")


def main():
    # --public builds from the sanitised corpus instead of the raw one. It is a
    # separate flag rather than the default because the local page is allowed
    # to show the owner name and the phone number -- that is the whole point of
    # a personal tool. A public URL is not.
    public = "--public" in sys.argv
    src = "app_data.public.json" if public else "app_data.json"
    if public and not (HERE / src).exists():
        sys.exit("run sanitize_public.py first -- refusing to publish raw data")

    # A fresh clone has no Chicago scrape. The checked-in public sample is
    # still San Francisco data, so it must not be rendered under Chicago labels.
    if not public and not (HERE / src).exists():
        sys.exit("no local Chicago scrape found; run the Chicago research pipeline first")
    data = json.load(open(HERE / src))
    require_chicago_data(data)
    data_json = json.dumps(data, separators=(",", ":"))

    if public:
        out = RESEARCH / "public" / "index.html"
        out.parent.mkdir(exist_ok=True)
        html, scraped = build(data_json, data_src=src)
        # The page checks this before offering anything that needs a server.
        html = html.replace('<meta charset="utf-8">',
                            '<meta charset="utf-8">\n'
                            '<script>window.CASITA_PUBLIC=true;</script>', 1)
        out.write_text(html, encoding="utf-8")
        print(f"   {len(data):,} apartments -> public/{out.name}"
              f"  (data scraped {scraped:%Y-%m-%d %H:%M})")
        return

    path = RESEARCH / "casita-demo.html"
    html, scraped = build(data_json, data_src=src)
    path.write_text(html, encoding="utf-8")
    print(f"   {len(data):,} apartments -> {path.name}"
          f"  (data scraped {scraped:%Y-%m-%d %H:%M})")


if __name__ == "__main__":
    main()
