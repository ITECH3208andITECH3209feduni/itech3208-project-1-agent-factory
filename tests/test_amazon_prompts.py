"""Tests for skills/amazon_prompts.py — PROJ-171."""

import pytest

from skills.amazon_prompts import (
    SEARCH_PROMPT,
    COMPARE_PROMPT,
    RECOMMEND_PROMPT,
    format_prompt,
)


def test_search_prompt_fills_correctly():
    out = format_prompt(SEARCH_PROMPT, query="laptops", results="item1, item2")
    assert "laptops" in out
    assert "item1, item2" in out


def test_compare_prompt_fills_correctly():
    out = format_prompt(COMPARE_PROMPT, products="A vs B")
    assert "A vs B" in out


def test_recommend_prompt_fills_correctly():
    out = format_prompt(RECOMMEND_PROMPT, products="A, B, C", budget="$500")
    assert "A, B, C" in out
    assert "$500" in out


def test_missing_placeholder_raises_key_error():
    with pytest.raises(KeyError):
        format_prompt(SEARCH_PROMPT, query="laptops")  # missing `results`


def test_all_prompts_have_word_limit_instruction():
    for prompt in (SEARCH_PROMPT, COMPARE_PROMPT, RECOMMEND_PROMPT):
        assert "150 words" in prompt


def test_prompts_are_strings():
    assert isinstance(SEARCH_PROMPT, str)
    assert isinstance(COMPARE_PROMPT, str)
    assert isinstance(RECOMMEND_PROMPT, str)