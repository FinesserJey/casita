import gzip
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_research_page_refuses_non_chicago_listing_data():
    build_pages = _load("research_build_pages", "research/pipeline/build_pages.py")

    with pytest.raises(SystemExit, match="non-Chicago"):
        build_pages.require_chicago_data([{"lat": 37.77, "lon": -122.42}])


def test_research_page_accepts_chicago_listing_data():
    build_pages = _load("research_build_pages", "research/pipeline/build_pages.py")

    build_pages.require_chicago_data([{"lat": 41.88, "lon": -87.64}])


def test_walk_graph_cache_requires_chicago_metadata(tmp_path, monkeypatch):
    graph_builder = _load("research_walk_graph", "research/pipeline/build_walk_graph.py")
    pipeline = tmp_path / "pipeline"
    pipeline.mkdir()
    (tmp_path / "walk_graph.json.gz").write_bytes(b"")
    monkeypatch.chdir(pipeline)

    with gzip.open(tmp_path / "walk_graph.json.gz", "wt", encoding="utf-8") as output:
        json.dump({"city": "chicago"}, output)
    assert graph_builder.is_current_graph()

    with gzip.open(tmp_path / "walk_graph.json.gz", "wt", encoding="utf-8") as output:
        json.dump({"lat0": 3770000, "lon0": -12252500}, output)
    assert not graph_builder.is_current_graph()
