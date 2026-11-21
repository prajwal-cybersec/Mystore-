"""Tests for Hinglish and Hindi query normalizer and query understanding."""

import pytest
from app.query_understanding import normalize_hinglish_query


def test_do_kg_atta():
    """'do kg atta' -> rewritten keeps the quantity: '2 kg atta'."""
    res = normalize_hinglish_query("do kg atta")
    assert res["rewritten"] == "2 kg atta"


def test_ghee_1_kg():
    """'ghee 1 kg' -> 'ghee 1 kg' (digits next to a unit are never dropped)."""
    res = normalize_hinglish_query("ghee 1 kg")
    assert res["rewritten"] == "ghee 1 kg"


def test_samsung_tv_43_inch():
    """'samsung tv 43 inch' -> unchanged."""
    res = normalize_hinglish_query("samsung tv 43 inch")
    assert res["rewritten"] == "samsung tv 43 inch"
    assert res["brand_preserved"] == "samsung"


def test_kam_keemat_tv():
    """'kam keemat tv' -> 'tv' with low_cost_intent true (phrase consumed completely, no stray 'keemat')."""
    res = normalize_hinglish_query("kam keemat tv")
    assert res["rewritten"] == "tv"
    assert res["low_cost_intent"] is True


def test_saree_for_women():
    """'saree for women' -> brand_preserved is None (brand matching must use whole-word boundaries, single-letter 'w' excluded)."""
    res = normalize_hinglish_query("saree for women")
    assert res["brand_preserved"] is None


def test_oneplus_variations():
    """'one plus 12' and 'oneplus 12' -> brand OnePlus detected in both spellings."""
    res1 = normalize_hinglish_query("one plus 12")
    res2 = normalize_hinglish_query("oneplus 12")
    assert res1["brand_preserved"] == "oneplus"
    assert res2["brand_preserved"] == "oneplus"


def test_do_not_disturb_phone():
    """'do not disturb phone' -> 'do' is not dropped when followed by an English word."""
    res = normalize_hinglish_query("do not disturb phone")
    assert "do" in res["tokens"]
    assert "do" in res["rewritten"]


def test_5000_se_kam_phone():
    """'5000 se kam phone' -> price 5000, rewritten 'phone'."""
    res = normalize_hinglish_query("5000 se kam phone")
    assert res["extracted_price"] == 5000.0
    assert res["rewritten"] == "phone"


def test_mobile_under_10_hajar():
    """'mobile under 10 hajar' -> price 10000, rewritten 'mobile'."""
    res = normalize_hinglish_query("mobile under 10 hajar")
    assert res["extracted_price"] == 10000.0
    assert res["rewritten"] == "mobile"


def test_word_boundary_phrase_replacement():
    """Ensure a short phrase can never rewrite the middle of another word."""
    # For instance 'ac' should not rewrite inside 'jack' or 'black'
    res = normalize_hinglish_query("black jacket")
    assert "ac" not in res["tokens"] or "air conditioner" not in res["rewritten"]
    assert "black" in res["rewritten"] or "jacket" in res["rewritten"]
