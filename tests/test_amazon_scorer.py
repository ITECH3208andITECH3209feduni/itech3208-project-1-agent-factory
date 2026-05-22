"""Tests for skills/amazon_scorer.py — PROJ-169."""

import pytest

from skills.amazon_scorer import score


# ── Helper for building product dicts ────────────────────────

def make_card(rating=4.5, reviews=1000, price=50.0, availability="in_stock"):
    return {
        "rating": rating,
        "reviews": reviews,
        "price": price,
        "availability": availability,
    }


# ── AC #1: score is always between 0 and 100 inclusive ──────

def test_score_returns_int():
    assert isinstance(score(make_card()), int)


def test_score_is_between_0_and_100_for_typical_input():
    s = score(make_card())
    assert 0 <= s <= 100


def test_perfect_card_scores_at_or_near_100():
    s = score({
        "rating": 5.0,
        "reviews": 50_000,        # well above the cap
        "price": 0.01,
        "availability": "in_stock",
    })
    # Allow 99 here: the price normalisation gives 19.9998 for $0.01
    # which truncates via int() to 19, so the true ceiling is 99 unless
    # price is exactly $0. The "near 100" name reflects this.
    assert s >= 99


def test_terrible_card_scores_at_or_near_0():
    s = score({
        "rating": 0.0,
        "reviews": 0,
        "price": 9999,
        "availability": "out_of_stock",
    })
    assert s == 0


def test_score_handles_missing_fields():
    s = score({})
    assert 0 <= s <= 100


def test_score_handles_garbage_input():
    s = score({
        "rating": "n/a",
        "reviews": "many",
        "price": "free",
        "availability": "maybe",
    })
    assert 0 <= s <= 100


# ── AC #2: higher rating + more reviews + lower price = higher score ──

def test_higher_rating_beats_lower_rating():
    high = score(make_card(rating=4.9))
    low  = score(make_card(rating=2.0))
    assert high > low


def test_more_reviews_beats_fewer_reviews():
    many = score(make_card(reviews=5000))
    few  = score(make_card(reviews=10))
    assert many > few


def test_lower_price_beats_higher_price():
    cheap     = score(make_card(price=20))
    expensive = score(make_card(price=900))
    assert cheap > expensive


# ── AC #3: out-of-stock scores ≥10 points lower than in-stock ──

def test_out_of_stock_scores_at_least_10_lower_than_in_stock():
    """Direct test of AC #3.

    The availability dimension carries 10 weight (1.0 in_stock vs 0.0
    out_of_stock = exactly 10 points difference). All other inputs held equal.
    """
    in_stock     = score(make_card(availability="in_stock"))
    out_of_stock = score(make_card(availability="out_of_stock"))
    assert in_stock - out_of_stock >= 10


def test_limited_stock_scores_between_in_and_out():
    in_stock = score(make_card(availability="in_stock"))
    limited  = score(make_card(availability="limited"))
    out      = score(make_card(availability="out_of_stock"))
    assert out <= limited <= in_stock


# ── Robustness: real-world string inputs ─────────────────────

def test_score_parses_rating_string():
    s_str = score(make_card(rating="4.5 / 5"))
    s_num = score(make_card(rating=4.5))
    assert s_str == s_num


def test_score_parses_price_string_with_dollar_sign():
    s_str = score(make_card(price="$49.99"))
    s_num = score(make_card(price=49.99))
    assert s_str == s_num


def test_score_parses_review_count_with_comma():
    s_str = score(make_card(reviews="1,234"))
    s_num = score(make_card(reviews=1234))
    assert s_str == s_num


def test_score_handles_boolean_availability():
    in_stock = score(make_card(availability=True))
    out      = score(make_card(availability=False))
    assert in_stock - out >= 10