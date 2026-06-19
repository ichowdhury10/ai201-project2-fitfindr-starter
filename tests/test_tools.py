"""
tests/test_tools.py

Unit tests for each FitFindr tool, focused on the failure modes documented
in planning.md.

Run with:
    pytest tests/
"""

import pytest
from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    """Impossible query should return [] without raising an exception."""
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    """All results must be at or below max_price."""
    results = search_listings("jacket", size=None, max_price=30)
    assert all(item["price"] <= 30 for item in results)


def test_search_size_filter_case_insensitive():
    """Size filtering should be case-insensitive and handle partial matches."""
    # "M" should match "S/M", "M", "M/L" etc.
    results = search_listings("top", size="m", max_price=None)
    assert all("m" in item["size"].lower() for item in results)


def test_search_no_description_tokens_match():
    """A description with no matching tokens should return empty list."""
    results = search_listings("zzzznonexistentitem", size=None, max_price=500)
    assert results == []


def test_search_results_are_sorted_by_relevance():
    """Better keyword matches should appear before worse matches."""
    results = search_listings("vintage graphic tee", size=None, max_price=None)
    assert len(results) > 1
    # The first result should have "graphic" or "tee" in its title or tags
    first = results[0]
    searchable = (
        first["title"]
        + " ".join(first["style_tags"])
        + first["description"]
    ).lower()
    assert "graphic" in searchable or "tee" in searchable


# ── suggest_outfit ────────────────────────────────────────────────────────────

def test_suggest_outfit_with_wardrobe():
    """Should return a non-empty string when wardrobe is populated."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    suggestion = suggest_outfit(results[0], get_example_wardrobe())
    assert isinstance(suggestion, str)
    assert len(suggestion) > 0


def test_suggest_outfit_empty_wardrobe():
    """Should return a non-empty string (general advice) for an empty wardrobe."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    suggestion = suggest_outfit(results[0], get_empty_wardrobe())
    assert isinstance(suggestion, str)
    assert len(suggestion) > 0


def test_suggest_outfit_does_not_raise_on_empty_wardrobe():
    """Empty wardrobe must not raise an exception."""
    results = search_listings("flannel shirt", size=None, max_price=50)
    assert len(results) > 0
    try:
        suggest_outfit(results[0], get_empty_wardrobe())
    except Exception as exc:
        pytest.fail(f"suggest_outfit raised {exc} with an empty wardrobe")


# ── create_fit_card ───────────────────────────────────────────────────────────

def test_create_fit_card_returns_string():
    """Happy path should return a non-empty string."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    outfit = suggest_outfit(results[0], get_example_wardrobe())
    card = create_fit_card(outfit, results[0])
    assert isinstance(card, str)
    assert len(card) > 0


def test_create_fit_card_empty_outfit_returns_error_string():
    """Empty outfit input should return an error string, not raise."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    result = create_fit_card("", results[0])
    assert isinstance(result, str)
    assert "error" in result.lower() or "no outfit" in result.lower()


def test_create_fit_card_whitespace_outfit_returns_error_string():
    """Whitespace-only outfit input should also return an error string."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    result = create_fit_card("   ", results[0])
    assert isinstance(result, str)
    assert "error" in result.lower() or "no outfit" in result.lower()


def test_create_fit_card_does_not_raise_on_empty_outfit():
    """Empty outfit must not raise an exception."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    try:
        create_fit_card("", results[0])
    except Exception as exc:
        pytest.fail(f"create_fit_card raised {exc} with an empty outfit string")
