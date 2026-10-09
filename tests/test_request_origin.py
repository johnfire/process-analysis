from __future__ import annotations

from web.request_origin import host_of, is_same_origin, needs_origin_check

OWN = {"process-analysis.example.de", "testserver"}


def test_matching_origin_is_accepted():
    assert is_same_origin("https://process-analysis.example.de", None, OWN)


def test_foreign_origin_is_refused():
    assert not is_same_origin("https://evil.example", None, OWN)


def test_lookalike_host_is_refused():
    assert not is_same_origin("https://process-analysis.example.de.evil.example", None, OWN)


def test_missing_origin_and_referer_is_refused():
    assert not is_same_origin(None, None, OWN)


def test_null_origin_falls_back_to_referer():
    assert is_same_origin("null", "https://testserver/login", OWN)
    assert not is_same_origin("null", None, OWN)


def test_origin_wins_over_a_friendly_referer():
    assert not is_same_origin("https://evil.example", "https://testserver/", OWN)


def test_only_unsafe_methods_need_the_check():
    assert needs_origin_check("post") and needs_origin_check("DELETE")
    assert not needs_origin_check("GET") and not needs_origin_check("HEAD")


def test_host_extraction_is_lowercase():
    assert host_of("HTTPS://Example.DE/path") == "example.de"
